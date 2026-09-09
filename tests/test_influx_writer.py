import base64
import io
import urllib.error
from dataclasses import replace
from email.message import Message

import pytest

from collectors.csv_writer import MeasurementRecord
from collectors.influx_writer import InfluxConfig, InfluxWriteError, InfluxWriter
from simulators.enums import ParsedQuality
from simulators.parser import GP350Reading


def make_config() -> InfluxConfig:
    return InfluxConfig(
        url="http://localhost:8086",
        org="lab org",
        bucket="gp350 bucket",
        token="secret",
        measurement="gp350 reading",
        timeout=2.0,
        retries=0,
        device_type="gp350",
        module_type="digital",
        command="#01RD",
    )


def make_record() -> MeasurementRecord:
    return MeasurementRecord(
        timestamp="2026-06-24T12:00:00+00:00",
        device="GP 350,=A",
        channel="IG1",
        latency_ms=12.3456,
        reading=GP350Reading(
            pressure_torr=1.23e-6,
            unit="Torr",
            gauge_status=None,
            quality=ParsedQuality.GOOD,
            raw_response='* 1.23E-06 "ok"',
            adc_voltage=0.815,
            signal_voltage=3.334,
            adc_raw=6520,
        ),
    )


def test_influx_line_protocol_escapes_values() -> None:
    writer = InfluxWriter(make_config())

    line = writer.to_line_protocol(make_record())

    assert line.startswith(
        "gp350\\ reading,"
        "device=GP\\ 350\\,\\=A,"
        "channel=IG1,"
        "quality=good,"
        "device_type=gp350,"
        "module_type=digital,"
        "command=#01RD "
    )
    assert "pressure_torr=1.23e-06" in line
    assert "latency_ms=12.346" in line
    assert 'raw_response="* 1.23E-06 \\"ok\\""' in line
    assert "adc_voltage=0.815" in line
    assert "signal_voltage=3.334" in line
    assert "adc_raw=6520i" in line
    assert 'unit="Torr"' in line
    assert line.endswith("1782302400000000000")


def test_gauge_status_is_bounded_prometheus_label() -> None:
    record = make_record()
    record = replace(
        record,
        reading=replace(
            record.reading,
            pressure_torr=None,
            gauge_status="sensor_off",
            quality=ParsedQuality.ERROR,
        ),
    )

    line = InfluxWriter(make_config()).to_line_protocol(record)

    tags = line[: line.index(" latency_ms=")]
    assert "gauge_status=sensor_off" in tags


def test_arbitrary_gauge_status_is_not_prometheus_label() -> None:
    record = make_record()
    record = replace(
        record,
        reading=replace(
            record.reading,
            gauge_status="device said 3.1 V at 2026-06-24",
        ),
    )

    line = InfluxWriter(make_config()).to_line_protocol(record)

    tags = line[: line.index(" pressure_torr=")]
    assert "gauge_status=" not in tags
    assert 'gauge_status="device said 3.1 V at 2026-06-24"' in line


def test_influx_writer_posts_line_protocol(monkeypatch) -> None:
    calls: list[tuple[str, bytes, dict[str, str], float]] = []

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            pass

        def getcode(self) -> int:
            return 204

    def fake_urlopen(request, timeout):
        calls.append(
            (
                request.full_url,
                request.data,
                dict(request.header_items()),
                timeout,
            )
        )
        return FakeResponse()

    monkeypatch.setattr("collectors.influx_writer.urllib.request.urlopen", fake_urlopen)

    writer = InfluxWriter(make_config())
    writer.write(make_record())

    url, payload, headers, timeout = calls[0]
    assert url == (
        "http://localhost:8086/api/v2/write?"
        "org=lab+org&bucket=gp350+bucket&precision=ns"
    )
    assert payload.decode("utf-8").startswith("gp350\\ reading,")
    assert headers["Authorization"] == "Token secret"
    assert headers["Content-type"] == "text/plain; charset=utf-8"
    assert timeout == 2.0


def test_influx_writer_raises_on_http_error(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=401,
            msg="Unauthorized",
            hdrs=Message(),
            fp=io.BytesIO(b"bad token"),
        )

    monkeypatch.setattr("collectors.influx_writer.urllib.request.urlopen", fake_urlopen)

    writer = InfluxWriter(make_config())

    with pytest.raises(InfluxWriteError):
        writer.write(make_record())


def test_grafana_cloud_posts_with_basic_auth_and_no_influx_query(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            pass

        def getcode(self) -> int:
            return 204

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr("collectors.influx_writer.urllib.request.urlopen", fake_urlopen)
    config = replace(
        make_config(),
        url="https://prometheus-prod.example.grafana.net",
        org="",
        bucket="",
        username="123456",
        write_path="/api/v1/push/influx/write",
    )

    InfluxWriter(config).write(make_record())

    request, timeout = calls[0]
    expected = base64.b64encode(b"123456:secret").decode("ascii")
    assert request.full_url == (
        "https://prometheus-prod.example.grafana.net/api/v1/push/influx/write"
    )
    assert "?" not in request.full_url
    assert request.get_header("Authorization") == f"Basic {expected}"
    assert request.data.decode("utf-8").startswith("gp350\\ reading,")
    assert timeout == 2.0


def test_grafana_cloud_does_not_retry_unauthorized(monkeypatch) -> None:
    attempts = 0

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=401,
            msg="Unauthorized",
            hdrs=Message(),
            fp=io.BytesIO(b"bad credentials"),
        )

    monkeypatch.setattr("collectors.influx_writer.urllib.request.urlopen", fake_urlopen)
    config = replace(make_config(), retries=2)

    with pytest.raises(InfluxWriteError, match="HTTP 401"):
        InfluxWriter(config).write(make_record())

    assert attempts == 1


@pytest.mark.parametrize("status", [429, 500])
def test_influx_writer_retries_transient_http_errors(monkeypatch, status) -> None:
    attempts = 0

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            pass

        def getcode(self) -> int:
            return 204

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise urllib.error.HTTPError(
                url=request.full_url,
                code=status,
                msg="temporary failure",
                hdrs=Message(),
                fp=io.BytesIO(b"retry later"),
            )
        return FakeResponse()

    monkeypatch.setattr("collectors.influx_writer.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("collectors.influx_writer.time.sleep", lambda _: None)
    config = replace(make_config(), retries=2)

    InfluxWriter(config).write(make_record())

    assert attempts == 3

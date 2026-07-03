import io
import urllib.error
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
    assert 'pressure_torr=1.23e-06' in line
    assert 'latency_ms=12.346' in line
    assert 'raw_response="* 1.23E-06 \\"ok\\""' in line
    assert 'unit="Torr"' in line
    assert line.endswith("1782302400000000000")


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

"""Hot reload must be transactional: a bad new config cannot kill a running
collector, and old resources stay usable until the new ones are proven open.
"""

from dataclasses import replace
from types import SimpleNamespace

import pytest
import serial

from collectors import gp350_collector as collector
from collectors.config import AppConfig, ConfigValidationError


class FakeClient:
    def __init__(self, name: str):
        self.name = name
        self.closed = False
        self.close_order: list[str] = []

    def send_command(self, command: str) -> str:
        if self.closed:
            raise serial.SerialException("port is closed")
        return "1.23E-06"

    def close(self) -> None:
        self.closed = True


class FakeWriter:
    def __init__(self, path: str):
        self.path = path
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeInfluxWriter:
    def __init__(self, url: str):
        self.url = url
        self.closed = False
        self.writes: list[object] = []

    def write(self, record: object) -> None:
        if self.closed:
            raise OSError("writer is closed")
        self.writes.append(record)

    def close(self) -> None:
        self.closed = True


def base_config(**overrides) -> AppConfig:
    cfg = AppConfig(
        serial_port="/dev/ttyUSB0",
        device_type="gp350",
        module_type="digital",
        command="RD",
        csv_filepath="data/a.csv",
    )
    return replace(cfg, **overrides) if overrides else cfg


def test_failed_client_open_leaves_old_client_usable(monkeypatch):
    """A new config whose port cannot be opened must not close the live one."""
    old_client = FakeClient("old")
    cfg = base_config()
    new_cfg = base_config(serial_port="/dev/does-not-exist")

    def failing_open(_cfg):
        raise serial.SerialException("could not open port")

    monkeypatch.setattr(collector, "open_client", failing_open)

    with pytest.raises(serial.SerialException):
        collector.apply_new_config(cfg, new_cfg, old_client, None, None)  # type: ignore[bad-argument-type]

    assert not old_client.closed, "live client was closed before the new one opened"
    assert old_client.send_command("RD") == "1.23E-06", (
        "collector can no longer measure"
    )


def test_new_client_is_open_before_old_one_is_closed(monkeypatch):
    """Ordering contract: open new, swap, only then close old."""
    events: list[str] = []
    old_client = FakeClient("old")
    new_client = FakeClient("new")

    def tracking_close():
        events.append("close-old")
        old_client.closed = True

    old_client.close = tracking_close  # type: ignore[method-assign]

    def opening(_cfg):
        events.append("open-new")
        return new_client

    monkeypatch.setattr(collector, "open_client", opening)
    monkeypatch.setattr(collector, "resolve_runtime_config", lambda c, _client: c)

    cfg = base_config()
    new_cfg = base_config(serial_port="/dev/ttyUSB9")

    result_cfg, result_client, _, _ = collector.apply_new_config(
        cfg,
        new_cfg,
        old_client,  # type: ignore[bad-argument-type]
        None,
        None,
    )

    assert events == ["open-new", "close-old"], f"wrong order: {events}"
    assert result_client is new_client
    assert result_cfg.serial_port == "/dev/ttyUSB9"


def test_failed_csv_open_leaves_old_writer_usable(monkeypatch):
    """Same guarantee for the CSV writer."""
    old_writer = FakeWriter("data/a.csv")
    cfg = base_config()
    new_cfg = base_config(csv_filepath="/nonexistent-dir/b.csv")

    def failing_writer(*_args, **_kwargs):
        raise OSError("cannot create file")

    monkeypatch.setattr(collector, "CsvWriter", failing_writer)
    monkeypatch.setattr(collector, "resolve_runtime_config", lambda c, _client: c)

    with pytest.raises(OSError):
        collector.apply_new_config(
            cfg,
            new_cfg,
            FakeClient("c"),  # type: ignore[bad-argument-type]
            old_writer,  # type: ignore[bad-argument-type]
            None,
        )

    assert not old_writer.closed, "live CSV writer was closed before the new one opened"


def test_failed_influx_open_leaves_old_influx_writer_usable(monkeypatch):
    """Same guarantee for the InfluxDB writer: a new config whose InfluxDB
    endpoint cannot be opened must not close the live writer, and the running
    config/client/CSV writer stay untouched.
    """
    old_influx = FakeInfluxWriter("http://old:8086")
    client = FakeClient("c")
    writer = FakeWriter("data/a.csv")
    cfg = base_config(influx_enabled=True, influx_url="http://old:8086")
    new_cfg = base_config(influx_enabled=True, influx_url="http://new:8086")

    def failing_open(new):
        raise OSError(f"cannot reach {new.influx_url}")

    monkeypatch.setattr(collector, "open_influx_writer", failing_open)
    monkeypatch.setattr(collector, "resolve_runtime_config", lambda c, _client: c)

    with pytest.raises(OSError):
        collector.apply_new_config(
            cfg,
            new_cfg,
            client,  # type: ignore[bad-argument-type]
            writer,  # type: ignore[bad-argument-type]
            old_influx,  # type: ignore[bad-argument-type]
        )

    assert not old_influx.closed, (
        "live InfluxDB writer was closed before the new one opened"
    )
    assert not client.closed, "live client was touched by the failed influx swap"
    assert not writer.closed, "live CSV writer was touched by the failed influx swap"
    old_influx.write(object())
    assert len(old_influx.writes) == 1, "collector can no longer write to InfluxDB"


def test_new_influx_writer_is_open_before_old_one_is_closed(monkeypatch):
    """Ordering contract for InfluxDB: open new, swap, only then close old."""
    events: list[str] = []
    old_influx = FakeInfluxWriter("http://old:8086")
    new_influx = FakeInfluxWriter("http://new:8086")

    def tracking_close():
        events.append("close-old")
        old_influx.closed = True

    old_influx.close = tracking_close  # type: ignore[method-assign]

    def opening(new):
        events.append("open-new")
        assert new.influx_url == "http://new:8086"
        return new_influx

    monkeypatch.setattr(collector, "open_influx_writer", opening)
    monkeypatch.setattr(collector, "resolve_runtime_config", lambda c, _client: c)

    cfg = base_config(influx_enabled=True, influx_url="http://old:8086")
    new_cfg = base_config(influx_enabled=True, influx_url="http://new:8086")

    result_cfg, _, _, result_influx = collector.apply_new_config(
        cfg,
        new_cfg,
        FakeClient("c"),  # type: ignore[bad-argument-type]
        FakeWriter("data/a.csv"),  # type: ignore[bad-argument-type]
        old_influx,  # type: ignore[bad-argument-type]
    )

    assert events == ["open-new", "close-old"], f"wrong order: {events}"
    assert result_influx is new_influx
    assert result_cfg.influx_url == "http://new:8086"


def test_failed_reload_does_not_count_toward_consecutive_errors(monkeypatch, tmp_path):
    """A failed config reload is not a measurement error: the collector must
    still tolerate MAX_CONSECUTIVE_ERRORS measurement failures before stopping.
    """
    cfg = base_config(path=str(tmp_path / "config.ini"))

    monkeypatch.setattr(
        collector,
        "parse_args",
        lambda: SimpleNamespace(
            config=cfg.path,
            port=None,
            discover=False,
            auto_device_index=None,
            scan_rs485=False,
        ),
    )
    monkeypatch.setattr(collector, "load_config_or_exit", lambda *_args: cfg)
    monkeypatch.setattr(collector, "setup_logging", lambda _cfg: None)
    monkeypatch.setattr(collector, "resolve_detected_config", lambda c, **_kw: c)
    monkeypatch.setattr(collector, "open_client", lambda _cfg: FakeClient("main"))
    monkeypatch.setattr(collector, "resolve_runtime_config", lambda c, _client: c)
    monkeypatch.setattr(
        collector,
        "CsvWriter",
        lambda *_args, **_kw: FakeWriter("data/a.csv"),
    )
    monkeypatch.setattr(collector, "open_influx_writer", lambda _cfg: None)
    monkeypatch.setattr(collector.time, "sleep", lambda _seconds: None)

    reload_pending = {"value": True}

    def fake_has_changed(_self, last_modified):
        if reload_pending["value"]:
            reload_pending["value"] = False
            return True, last_modified + 1
        return False, last_modified + 1

    monkeypatch.setattr(AppConfig, "has_changed", fake_has_changed)

    def bad_config_file(*_args, **_kwargs):
        raise ConfigValidationError("broken new config")

    monkeypatch.setattr(AppConfig, "from_file", bad_config_file)

    read_calls = 0

    def failing_read(_client, _cfg):
        nonlocal read_calls
        read_calls += 1
        raise serial.SerialException("no device")

    monkeypatch.setattr(collector, "read_device_response", failing_read)

    collector.main()

    assert read_calls == collector.MAX_CONSECUTIVE_ERRORS, (
        "failed reload consumed part of the measurement error budget: "
        f"only {read_calls} measurement attempts before stop"
    )

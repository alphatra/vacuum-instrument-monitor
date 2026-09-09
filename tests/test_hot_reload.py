"""Hot reload must be transactional: a bad new config cannot kill a running
collector, and old resources stay usable until the new ones are proven open.
"""

from dataclasses import replace

import pytest
import serial

from collectors import gp350_collector as collector
from collectors.config import AppConfig


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

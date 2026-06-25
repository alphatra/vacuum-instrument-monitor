import csv

import pytest

from collectors.config import AppConfig, ConfigValidationError
from collectors.csv_writer import CSV_HEADER, CsvWriter, MeasurementRecord
from collectors.gp350_collector import build_serial_command
from collectors.serial_client import SerialClient
from simulators.enums import ParsedQuality
from simulators.parser import GP350Reading


def test_config_loads_all_collector_fields(tmp_path) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        """
[General]
debug = true
log_level = debug

[Connection]
module_type = digital
serial_port = /dev/tty.test
baudrate = 9600
bytesize = 8
parity = none
stopbits = 1
rs485_address = 3
timeout = 2.5
write_timeout = 3.5

[Collector]
command = DS IG
interval_seconds = 0.5

[Device]
device_name = GP350_TEST
channel = IG2

[File]
csv_filepath = data/test.csv
csv_mode = append
log_file = logs/test.log

[InfluxDB]
enabled = true
url = http://localhost:8086
org = lab
bucket = gp350
token = secret
measurement = gp350_pressure
timeout = 4.5
retries = 2
fail_on_error = true
""",
        encoding="utf-8",
    )

    cfg = AppConfig.from_file(str(config_path))

    assert cfg.debug is True
    assert cfg.log_level == "debug"
    assert cfg.module_type == "digital"
    assert cfg.serial_port == "/dev/tty.test"
    assert cfg.baudrate == 9600
    assert cfg.bytesize == 8
    assert cfg.parity == "none"
    assert cfg.stopbits == 1
    assert cfg.line_terminator == "\r"
    assert cfg.rs485_address == 3
    assert cfg.timeout == 2.5
    assert cfg.write_timeout == 3.5
    assert cfg.command == "DS IG"
    assert cfg.interval_seconds == 0.5
    assert cfg.device_name == "GP350_TEST"
    assert cfg.channel == "IG2"
    assert cfg.csv_filepath == "data/test.csv"
    assert cfg.csv_mode == "append"
    assert cfg.log_file == "logs/test.log"
    assert cfg.influx_enabled is True
    assert cfg.influx_url == "http://localhost:8086"
    assert cfg.influx_org == "lab"
    assert cfg.influx_bucket == "gp350"
    assert cfg.resolved_influx_token == "secret"
    assert cfg.influx_measurement == "gp350_pressure"
    assert cfg.influx_timeout == 4.5
    assert cfg.influx_retries == 2
    assert cfg.influx_fail_on_error is True


def test_config_reads_influx_token_from_env(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        """
[Connection]
serial_port = /dev/tty.test

[InfluxDB]
enabled = true
url = http://localhost:8086
org = lab
bucket = gp350
token_env = TEST_INFLUX_TOKEN
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_INFLUX_TOKEN", "from-env")

    cfg = AppConfig.from_file(str(config_path))

    assert cfg.resolved_influx_token == "from-env"


def test_config_rejects_enabled_influx_without_token(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        """
[Connection]
serial_port = /dev/tty.test

[InfluxDB]
enabled = true
url = http://localhost:8086
org = lab
bucket = gp350
token_env = MISSING_INFLUX_TOKEN
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("MISSING_INFLUX_TOKEN", raising=False)

    with pytest.raises(ConfigValidationError):
        AppConfig.from_file(str(config_path))


def test_config_uses_rs232_module_defaults(tmp_path) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        """
[Connection]
module_type = rs232
serial_port = /dev/tty.test
""",
        encoding="utf-8",
    )

    cfg = AppConfig.from_file(str(config_path))

    assert cfg.baudrate == 300
    assert cfg.bytesize == 7
    assert cfg.parity == "none"
    assert cfg.stopbits == 2
    assert cfg.line_terminator == "\r\n"
    assert cfg.command == "DS IG"


def test_config_uses_digital_module_defaults(tmp_path) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        """
[Connection]
module_type = digital
serial_port = /dev/tty.test
""",
        encoding="utf-8",
    )

    cfg = AppConfig.from_file(str(config_path))

    assert cfg.baudrate == 9600
    assert cfg.bytesize == 8
    assert cfg.parity == "none"
    assert cfg.stopbits == 1
    assert cfg.line_terminator == "\r"
    assert cfg.command == "RD"


def test_config_rejects_rs485_address_for_rs232(tmp_path) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        """
[Connection]
module_type = rs232
serial_port = /dev/tty.test
rs485_address = 1
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError):
        AppConfig.from_file(str(config_path))


def test_config_rejects_rs485_address_out_of_range(tmp_path) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        """
[Connection]
module_type = digital
serial_port = /dev/tty.test
rs485_address = 32
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError):
        AppConfig.from_file(str(config_path))


def test_build_serial_command_adds_rs485_address() -> None:
    cfg = AppConfig(
        module_type="digital",
        serial_port="/dev/tty.test",
        command="RD",
        rs485_address=1,
    )

    assert build_serial_command(cfg) == "#01RD"


def test_config_port_override_allows_missing_port(tmp_path) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text("[Connection]\nbaudrate = 9600\n", encoding="utf-8")

    cfg = AppConfig.from_file(
        str(config_path),
        serial_port_override="/dev/override",
    )

    assert cfg.serial_port == "/dev/override"


def test_config_rejects_missing_port(tmp_path) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text("[Connection]\nbaudrate = 9600\n", encoding="utf-8")

    with pytest.raises(ConfigValidationError):
        AppConfig.from_file(str(config_path))


def test_csv_writer_uses_documented_columns(tmp_path) -> None:
    csv_path = tmp_path / "readings.csv"
    reading = GP350Reading(
        pressure_torr=1.23e-6,
        unit="Torr",
        gauge_status=None,
        quality=ParsedQuality.GOOD,
        raw_response="1.23E-06",
    )
    record = MeasurementRecord(
        timestamp="2026-06-24T12:00:00+00:00",
        device="GP350_1",
        channel="IG1",
        latency_ms=12.3456,
        reading=reading,
    )

    with CsvWriter(str(csv_path)) as writer:
        writer.write(record)

    rows = list(csv.reader(csv_path.open(encoding="utf-8")))

    assert rows[0] == CSV_HEADER
    assert rows[1] == [
        "2026-06-24T12:00:00+00:00",
        "GP350_1",
        "IG1",
        "1.23e-06",
        "Torr",
        "good",
        "1.23E-06",
        "12.346",
    ]


def test_csv_writer_overwrites_and_creates_header_immediately(tmp_path) -> None:
    csv_path = tmp_path / "readings.csv"
    csv_path.write_text("old,data\n", encoding="utf-8")

    writer = CsvWriter(str(csv_path), mode="overwrite")

    rows = list(csv.reader(csv_path.open(encoding="utf-8")))
    writer.close()

    assert rows == [CSV_HEADER]


def test_csv_writer_append_keeps_existing_rows(tmp_path) -> None:
    csv_path = tmp_path / "readings.csv"
    csv_path.write_text("old,data\n", encoding="utf-8")

    writer = CsvWriter(str(csv_path), mode="append")
    writer.close()

    rows = list(csv.reader(csv_path.open(encoding="utf-8")))

    assert rows == [["old", "data"]]


def test_serial_client_flushes_buffers_and_replaces_decode_errors(monkeypatch) -> None:
    calls: list[str] = []

    class FakeSerial:
        is_open = True

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def reset_input_buffer(self) -> None:
            calls.append("reset_input")

        def reset_output_buffer(self) -> None:
            calls.append("reset_output")

        def write(self, data: bytes) -> None:
            calls.append(data.decode("ascii"))

        def flush(self) -> None:
            calls.append("flush")

        def readline(self) -> bytes:
            return b"1.23E-06\xff"

        def close(self) -> None:
            calls.append("close")
            self.is_open = False

    monkeypatch.setattr("collectors.serial_client.time.sleep", lambda _: None)
    monkeypatch.setattr("collectors.serial_client.serial.Serial", FakeSerial)

    client = SerialClient("/dev/fake", 9600, timeout=2.0, write_timeout=3.0)
    response = client.send_command("DS IG")
    client.close()

    assert calls.count("reset_input") == 2
    assert calls.count("reset_output") == 2
    assert "DS IG\r\n" in calls
    assert response == "1.23E-06�"
    assert "close" in calls


def test_serial_client_reads_cr_terminated_response(monkeypatch) -> None:
    calls: list[str] = []

    class FakeSerial:
        is_open = True

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.buffer = iter(b"* 1.23E-06\r")

        def reset_input_buffer(self) -> None:
            pass

        def reset_output_buffer(self) -> None:
            pass

        def write(self, data: bytes) -> None:
            calls.append(data.decode("ascii"))

        def flush(self) -> None:
            pass

        def read(self, size: int = 1) -> bytes:
            try:
                return bytes([next(self.buffer)])
            except StopIteration:
                return b""

        def readline(self) -> bytes:
            raise AssertionError("CR mode must not use readline")

        def close(self) -> None:
            self.is_open = False

    monkeypatch.setattr("collectors.serial_client.time.sleep", lambda _: None)
    monkeypatch.setattr("collectors.serial_client.serial.Serial", FakeSerial)

    client = SerialClient("/dev/fake", 9600, line_terminator="\r")
    response = client.send_command("RD")
    client.close()

    assert calls == ["RD\r"]
    assert response == "* 1.23E-06"


def test_serial_client_reports_closed_port(monkeypatch) -> None:
    class FakeSerial:
        is_open = False

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

        def reset_input_buffer(self) -> None:
            pass

        def reset_output_buffer(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr("collectors.serial_client.time.sleep", lambda _: None)
    monkeypatch.setattr("collectors.serial_client.serial.Serial", FakeSerial)

    client = SerialClient("/dev/fake", 9600)

    with pytest.raises(Exception, match="serial port is closed"):
        client.send_command("DS IG")

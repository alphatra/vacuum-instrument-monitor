import csv
from typing import cast

import pytest

from collectors.config import AppConfig, ConfigValidationError
from collectors.csv_writer import CSV_HEADER, CsvWriter, MeasurementRecord
from collectors.device_discovery import DetectedDevice
from collectors.gp350_collector import (
    build_measurement_records,
    build_serial_command,
    parse_device_response,
    resolve_detected_config,
    resolve_runtime_config,
)
from collectors.serial_client import SerialClient
from collectors.vgc402 import ACK, ENQ
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

[Detection]
device_index = 1
probe_timeout = 0.25
scan_rs485 = true
rs485_addresses = 1,3-4

[Device]
device_type = gp350
device_name = GP350_TEST
channel = IG2
pressure_unit = Torr

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
    assert cfg.device_type == "gp350"
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
    assert cfg.auto_device_index == 1
    assert cfg.auto_probe_timeout == 0.25
    assert cfg.auto_scan_rs485 is True
    assert cfg.auto_rs485_addresses == (1, 3, 4)
    assert cfg.interval_seconds == 0.5
    assert cfg.device_name == "GP350_TEST"
    assert cfg.channel == "IG2"
    assert cfg.pressure_unit == "Torr"
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


def test_config_uses_inficon_vgc402_defaults(tmp_path) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        """
[Connection]
module_type = auto
serial_port = /dev/tty.test

[Device]
device_type = inficon_vgc402
pressure_unit = mbar
""",
        encoding="utf-8",
    )

    cfg = AppConfig.from_file(str(config_path))

    assert cfg.device_type == "inficon_vgc402"
    assert cfg.module_type == "auto"
    assert cfg.baudrate == 9600
    assert cfg.bytesize == 8
    assert cfg.parity == "none"
    assert cfg.stopbits == 1
    assert cfg.line_terminator == "\r\n"
    assert cfg.command == "PR1"
    assert cfg.pressure_unit == "mbar"


def test_config_allows_inficon_vgc402_38400_prx_and_auto_unit(tmp_path) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        """
[Connection]
module_type = serial
serial_port = /dev/tty.test
baudrate = 38400

[Collector]
command = PRX

[Device]
device_type = inficon_vgc402
pressure_unit = auto
""",
        encoding="utf-8",
    )

    cfg = AppConfig.from_file(str(config_path))

    assert cfg.device_type == "inficon_vgc402"
    assert cfg.baudrate == 38400
    assert cfg.command == "PRX"
    assert cfg.pressure_unit == "auto"


def test_config_allows_auto_detection(tmp_path) -> None:
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        """
[Connection]
module_type = auto
serial_port = auto
""",
        encoding="utf-8",
    )

    cfg = AppConfig.from_file(str(config_path))

    assert cfg.module_type == "auto"
    assert cfg.serial_port == "auto"
    assert cfg.needs_device_detection is True


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


def test_resolve_detected_config_copies_probe_settings(monkeypatch) -> None:
    detected = DetectedDevice(
        device_type="gp350",
        port="/dev/cu.usbserial-A",
        module_type="rs232",
        baudrate=300,
        bytesize=7,
        parity="none",
        stopbits=2.0,
        line_terminator="\r\n",
        command="DS IG",
        rs485_address=None,
        raw_response="1.23E-06",
        confidence=1.0,
    )

    monkeypatch.setattr(
        "collectors.gp350_collector.discover_serial_devices",
        lambda **_: [detected],
    )

    cfg = AppConfig(module_type="auto", serial_port="auto")
    resolved = resolve_detected_config(cfg)

    assert resolved.module_type == "rs232"
    assert resolved.serial_port == "/dev/cu.usbserial-A"
    assert resolved.baudrate == 300
    assert resolved.bytesize == 7
    assert resolved.command == "DS IG"


def test_resolve_detected_config_copies_vgc402_settings(monkeypatch) -> None:
    detected = DetectedDevice(
        device_type="inficon_vgc402",
        port="/dev/cu.usbserial-VGC",
        module_type="serial",
        baudrate=9600,
        bytesize=8,
        parity="none",
        stopbits=1.0,
        line_terminator="\r\n",
        command="PR2",
        rs485_address=None,
        raw_response="0,1.23E-06",
        confidence=1.0,
    )

    monkeypatch.setattr(
        "collectors.gp350_collector.discover_serial_devices",
        lambda **_: [detected],
    )

    cfg = AppConfig(device_type="auto", module_type="auto", serial_port="auto")
    resolved = resolve_detected_config(cfg)

    assert resolved.device_type == "inficon_vgc402"
    assert resolved.module_type == "serial"
    assert resolved.serial_port == "/dev/cu.usbserial-VGC"
    assert resolved.command == "PR2"
    assert resolved.device_name == "VGC402_1"
    assert resolved.channel == "CH2"


def test_resolve_detected_config_preserves_requested_vgc402_prx(monkeypatch) -> None:
    detected = DetectedDevice(
        device_type="inficon_vgc402",
        port="/dev/cu.usbserial-VGC",
        module_type="serial",
        baudrate=38400,
        bytesize=8,
        parity="none",
        stopbits=1.0,
        line_terminator="\r\n",
        command="PR1",
        rs485_address=None,
        raw_response="0,1.23E-06",
        confidence=1.0,
    )

    monkeypatch.setattr(
        "collectors.gp350_collector.discover_serial_devices",
        lambda **_: [detected],
    )

    cfg = AppConfig(
        device_type="inficon_vgc402",
        module_type="auto",
        serial_port="auto",
        command="PRX",
    )
    resolved = resolve_detected_config(cfg)

    assert resolved.baudrate == 38400
    assert resolved.command == "PRX"
    assert resolved.channel == "ALL"


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
        "",
        "1.23E-06",
        "12.346",
    ]


def test_vgc402_parser_converts_mbar_to_torr() -> None:
    cfg = AppConfig(
        device_type="inficon_vgc402",
        module_type="serial",
        serial_port="/dev/tty.test",
        pressure_unit="mbar",
        command="PR1",
    )

    reading = parse_device_response("0,1.0000E-03", cfg)

    assert reading.quality == ParsedQuality.GOOD
    assert reading.pressure_torr == pytest.approx(7.50061683e-4)
    assert reading.unit == "Torr"
    assert reading.gauge_status == "ok"


def test_vgc402_parser_converts_micron_to_torr() -> None:
    cfg = AppConfig(
        device_type="inficon_vgc402",
        module_type="serial",
        serial_port="/dev/tty.test",
        pressure_unit="micron",
        command="PR1",
    )

    reading = parse_device_response("0,1.0000E+03", cfg)

    assert reading.quality == ParsedQuality.GOOD
    assert reading.pressure_torr == pytest.approx(1.0)
    assert reading.unit == "Torr"


def test_vgc402_parser_marks_nonzero_status_as_error() -> None:
    cfg = AppConfig(
        device_type="inficon_vgc402",
        module_type="serial",
        serial_port="/dev/tty.test",
        pressure_unit="Torr",
        command="PR2",
    )

    reading = parse_device_response("4,0.0000E+00", cfg)

    assert reading.quality == ParsedQuality.ERROR
    assert reading.pressure_torr is None
    assert reading.gauge_status == "sensor_off"


def test_vgc402_parser_marks_status_7_as_sensor_error() -> None:
    cfg = AppConfig(
        device_type="inficon_vgc402",
        module_type="serial",
        serial_port="/dev/tty.test",
        pressure_unit="Torr",
        command="PR1",
    )

    reading = parse_device_response("7,0.0000E+00", cfg)

    assert reading.quality == ParsedQuality.ERROR
    assert reading.pressure_torr is None
    assert reading.gauge_status == "bpg_bcg_hpg_error"


def test_vgc402_auto_unit_reads_uni_before_measurements() -> None:
    calls: list[str] = []

    class FakeClient:
        def send_ack_enq_command(self, command: str) -> str:
            calls.append(command)
            return "3"

    cfg = AppConfig(
        device_type="inficon_vgc402",
        module_type="serial",
        serial_port="/dev/tty.test",
        pressure_unit="auto",
    )

    resolved = resolve_runtime_config(cfg, cast(SerialClient, FakeClient()))

    assert calls == ["UNI"]
    assert resolved.pressure_unit == "micron"


def test_vgc402_prx_builds_one_record_per_channel() -> None:
    cfg = AppConfig(
        device_type="inficon_vgc402",
        module_type="serial",
        serial_port="/dev/tty.test",
        device_name="VGC402_1",
        channel="IGNORED_FOR_PRX",
        pressure_unit="mbar",
        command="PRX",
    )
    raw_response = "0,1.0000E-03,7,0.0000E+00"

    records = build_measurement_records(
        raw_response=raw_response,
        cfg=cfg,
        timestamp="2026-06-24T12:00:00+00:00",
        latency_ms=12.345,
    )

    assert [record.channel for record in records] == ["CH1", "CH2"]
    assert records[0].reading.quality == ParsedQuality.GOOD
    assert records[0].reading.pressure_torr == pytest.approx(7.50061683e-4)
    assert records[0].reading.raw_response == raw_response
    assert records[1].reading.quality == ParsedQuality.ERROR
    assert records[1].reading.gauge_status == "bpg_bcg_hpg_error"
    assert records[1].reading.raw_response == raw_response


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


def test_serial_client_supports_inficon_ack_enq_handshake(monkeypatch) -> None:
    calls: list[bytes] = []

    class FakeSerial:
        is_open = True

        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.buffer = b""

        def reset_input_buffer(self) -> None:
            pass

        def reset_output_buffer(self) -> None:
            pass

        def write(self, data: bytes) -> None:
            calls.append(data)
            if data == b"PR1\r\n":
                self.buffer = f"{ACK}\r\n".encode("ascii")
            elif data == ENQ:
                self.buffer = b"0,1.2345E-06\r\n"

        def flush(self) -> None:
            pass

        def readline(self) -> bytes:
            data = self.buffer
            self.buffer = b""
            return data

        def close(self) -> None:
            self.is_open = False

    monkeypatch.setattr("collectors.serial_client.time.sleep", lambda _: None)
    monkeypatch.setattr("collectors.serial_client.serial.Serial", FakeSerial)

    client = SerialClient("/dev/fake", 9600)
    response = client.send_ack_enq_command("PR1")
    client.close()

    assert calls == [b"PR1\r\n", ENQ]
    assert response == "0,1.2345E-06"

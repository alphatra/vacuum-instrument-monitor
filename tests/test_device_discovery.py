from dataclasses import dataclass
from typing import Any

import pytest

from collectors.device_discovery import (
    DeviceDiscoveryError,
    discover_gp350_devices,
    discover_inficon_vgc402_devices,
    discover_serial_devices,
    select_gp350_device,
)
from collectors.vgc402 import ACK, ENQ


@dataclass(frozen=True)
class FakePortInfo:
    device: str
    description: str = "USB serial"
    hwid: str = ""
    manufacturer: str = ""
    product: str = ""
    serial_number: str = ""


class FakeSerial:
    responses: dict[tuple[str, int, bytes], bytes] = {}

    def __init__(self, **kwargs: Any) -> None:
        self.port = kwargs["port"]
        self.baudrate = kwargs["baudrate"]
        self.buffer = b""

    def __enter__(self) -> "FakeSerial":
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def reset_input_buffer(self) -> None:
        pass

    def reset_output_buffer(self) -> None:
        pass

    def write(self, data: bytes) -> None:
        self.buffer = self.responses.get((self.port, self.baudrate, data), b"")

    def flush(self) -> None:
        pass

    def read(self, size: int = 1) -> bytes:
        if not self.buffer:
            return b""

        data = self.buffer[:size]
        self.buffer = self.buffer[size:]
        return data

    def readline(self) -> bytes:
        data = self.buffer
        self.buffer = b""
        return data


def test_discover_gp350_devices_detects_digital_and_rs232() -> None:
    FakeSerial.responses = {
        ("/dev/cu.usbserial-A", 9600, b"RD\r"): b"1.23E-06\r",
        ("/dev/cu.usbserial-B", 300, b"DS IG\r\n"): b"4.56E-06\r\n",
    }
    ports = [
        FakePortInfo("/dev/tty.usbserial-A"),
        FakePortInfo("/dev/cu.usbserial-A"),
        FakePortInfo("/dev/cu.usbserial-B"),
        FakePortInfo("/dev/cu.Bluetooth-Incoming-Port", description="Bluetooth"),
    ]

    devices = discover_gp350_devices(
        ports=ports,
        serial_factory=FakeSerial,
        settle_delay=0,
    )

    assert [device.port for device in devices] == [
        "/dev/cu.usbserial-A",
        "/dev/cu.usbserial-B",
    ]
    assert devices[0].module_type == "digital"
    assert devices[0].command == "RD"
    assert devices[1].module_type == "rs232"
    assert devices[1].baudrate == 300


def test_discover_gp350_devices_detects_addressed_rs485() -> None:
    FakeSerial.responses = {
        ("/dev/cu.usbserial-RS485", 9600, b"#01RD\r"): b"* 1.23E-06\r",
    }

    devices = discover_gp350_devices(
        port_names=["/dev/cu.usbserial-RS485"],
        include_module_types=("digital",),
        rs485_addresses=(0, 1),
        serial_factory=FakeSerial,
        settle_delay=0,
    )

    assert len(devices) == 1
    assert devices[0].rs485_address == 1
    assert devices[0].module_type == "digital"
    assert devices[0].confidence == 0.98


def test_discover_gp350_devices_ignores_unknown_responses() -> None:
    FakeSerial.responses = {
        ("/dev/cu.usbserial-X", 9600, b"RD\r"): b"READY\r",
    }

    devices = discover_gp350_devices(
        port_names=["/dev/cu.usbserial-X"],
        serial_factory=FakeSerial,
        settle_delay=0,
    )

    assert devices == []


def test_discover_inficon_vgc402_devices_detects_ack_enq_protocol() -> None:
    FakeSerial.responses = {
        ("/dev/cu.usbserial-VGC", 9600, b"PR1\r\n"): f"{ACK}\r\n".encode("ascii"),
        ("/dev/cu.usbserial-VGC", 9600, ENQ): b"0,1.23E-06\r\n",
    }

    devices = discover_inficon_vgc402_devices(
        port_names=["/dev/cu.usbserial-VGC"],
        serial_factory=FakeSerial,
        settle_delay=0,
    )

    assert len(devices) == 1
    assert devices[0].device_type == "inficon_vgc402"
    assert devices[0].module_type == "serial"
    assert devices[0].command == "PR1"
    assert devices[0].raw_response == "0,1.23E-06"


def test_discover_inficon_vgc402_devices_scans_all_manual_baudrates() -> None:
    FakeSerial.responses = {
        ("/dev/cu.usbserial-VGC", 38400, b"PR1\r\n"): f"{ACK}\r\n".encode(
            "ascii"
        ),
        ("/dev/cu.usbserial-VGC", 38400, ENQ): b"0,3.84E-06\r\n",
    }

    devices = discover_inficon_vgc402_devices(
        port_names=["/dev/cu.usbserial-VGC"],
        serial_factory=FakeSerial,
        settle_delay=0,
    )

    assert len(devices) == 1
    assert devices[0].baudrate == 38400
    assert devices[0].raw_response == "0,3.84E-06"


def test_discover_serial_devices_can_find_gp350_and_vgc402() -> None:
    FakeSerial.responses = {
        ("/dev/cu.usbserial-GP", 9600, b"RD\r"): b"1.23E-06\r",
        ("/dev/cu.usbserial-VGC", 9600, b"PR1\r\n"): f"{ACK}\r\n".encode("ascii"),
        ("/dev/cu.usbserial-VGC", 9600, ENQ): b"0,4.56E-06\r\n",
    }

    devices = discover_serial_devices(
        port_names=["/dev/cu.usbserial-GP", "/dev/cu.usbserial-VGC"],
        serial_factory=FakeSerial,
        settle_delay=0,
    )

    assert [device.device_type for device in devices] == ["gp350", "inficon_vgc402"]


def test_select_gp350_device_reports_missing_index() -> None:
    with pytest.raises(DeviceDiscoveryError):
        select_gp350_device([], 0)

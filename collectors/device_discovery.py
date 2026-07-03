import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

import serial
from serial.tools import list_ports

from collectors.vgc402 import ACK, ENQ, NAK, VGC402_BAUDRATES, VGC402Parser
from simulators import GP350Parser, ParsedQuality


class DeviceDiscoveryError(Exception):
    """Raised when automatic device discovery cannot select a device."""


@dataclass(frozen=True)
class DetectionProbe:
    # One safe read-only serial attempt used during discovery.
    device_type: str
    module_type: str
    baudrate: int
    bytesize: int
    parity: str
    stopbits: float
    line_terminator: str
    command: str
    rs485_address: int | None = None
    protocol: str = "plain"

    @property
    def serial_command(self) -> str:
        if self.rs485_address is None:
            return self.command

        return f"#{self.rs485_address:02d}{self.command}"


@dataclass(frozen=True)
class DetectedDevice:
    # Stable result that can be copied into AppConfig.
    device_type: str
    port: str
    module_type: str
    baudrate: int
    bytesize: int
    parity: str
    stopbits: float
    line_terminator: str
    command: str
    rs485_address: int | None
    raw_response: str
    confidence: float
    description: str = ""
    hwid: str = ""
    serial_number: str = ""


GP350_DIRECT_PROBES = (
    DetectionProbe(
        device_type="gp350",
        module_type="digital",
        baudrate=9600,
        bytesize=8,
        parity="none",
        stopbits=1.0,
        line_terminator="\r",
        command="RD",
    ),
    DetectionProbe(
        device_type="gp350",
        module_type="rs232",
        baudrate=300,
        bytesize=7,
        parity="none",
        stopbits=2.0,
        line_terminator="\r\n",
        command="DS IG",
    ),
)
VGC402_DIRECT_PROBES = tuple(
    DetectionProbe(
        device_type="inficon_vgc402",
        module_type="serial",
        baudrate=baudrate,
        bytesize=8,
        parity="none",
        stopbits=1.0,
        line_terminator="\r\n",
        command=command,
        protocol="ack_enq",
    )
    for baudrate in VGC402_BAUDRATES
    for command in ("PR1", "PR2")
)

PARITY_MAP = {
    "none": serial.PARITY_NONE,
    "even": serial.PARITY_EVEN,
    "odd": serial.PARITY_ODD,
}

GP350_NOT_READY_RESPONSES = {"9.90E+09", "9.90E+9", "9.9E+09", "9.9E+9"}
IGNORED_PORT_KEYWORDS = {"bluetooth", "debug-console"}


def discover_serial_devices(
    *,
    ports: Iterable[Any] | None = None,
    port_names: Iterable[str] | None = None,
    include_device_types: Iterable[str] = ("gp350", "inficon_vgc402"),
    include_module_types: Iterable[str] = ("digital", "rs232", "serial"),
    rs485_addresses: Iterable[int] = (),
    timeout: float = 0.35,
    write_timeout: float | None = None,
    settle_delay: float = 0.05,
    serial_factory: Callable[..., Any] = serial.Serial,
) -> list[DetectedDevice]:
    """Scan serial ports and return supported vacuum instruments."""
    candidates = _candidate_ports(ports=ports, port_names=port_names)
    detected: list[DetectedDevice] = []

    for port_info in candidates:
        device = probe_serial_port(
            _port_device(port_info),
            port_info=port_info,
            include_device_types=include_device_types,
            include_module_types=include_module_types,
            rs485_addresses=rs485_addresses,
            timeout=timeout,
            write_timeout=write_timeout,
            settle_delay=settle_delay,
            serial_factory=serial_factory,
        )
        if device is not None:
            detected.append(device)

    return sorted(detected, key=lambda item: item.port)


def discover_gp350_devices(
    *,
    ports: Iterable[Any] | None = None,
    port_names: Iterable[str] | None = None,
    include_module_types: Iterable[str] = ("digital", "rs232"),
    rs485_addresses: Iterable[int] = (),
    timeout: float = 0.35,
    write_timeout: float | None = None,
    settle_delay: float = 0.05,
    serial_factory: Callable[..., Any] = serial.Serial,
) -> list[DetectedDevice]:
    """Scan serial ports and return GP350-like devices."""
    return discover_serial_devices(
        ports=ports,
        port_names=port_names,
        include_device_types=("gp350",),
        include_module_types=include_module_types,
        rs485_addresses=rs485_addresses,
        timeout=timeout,
        write_timeout=write_timeout,
        settle_delay=settle_delay,
        serial_factory=serial_factory,
    )


def discover_inficon_vgc402_devices(
    *,
    ports: Iterable[Any] | None = None,
    port_names: Iterable[str] | None = None,
    timeout: float = 0.35,
    write_timeout: float | None = None,
    settle_delay: float = 0.05,
    serial_factory: Callable[..., Any] = serial.Serial,
) -> list[DetectedDevice]:
    """Scan serial ports and return INFICON VGC402-like devices."""
    return discover_serial_devices(
        ports=ports,
        port_names=port_names,
        include_device_types=("inficon_vgc402",),
        include_module_types=("serial",),
        timeout=timeout,
        write_timeout=write_timeout,
        settle_delay=settle_delay,
        serial_factory=serial_factory,
    )


def probe_serial_port(
    port: str,
    *,
    port_info: Any | None = None,
    include_device_types: Iterable[str] = ("gp350", "inficon_vgc402"),
    include_module_types: Iterable[str] = ("digital", "rs232", "serial"),
    rs485_addresses: Iterable[int] = (),
    timeout: float = 0.35,
    write_timeout: float | None = None,
    settle_delay: float = 0.05,
    serial_factory: Callable[..., Any] = serial.Serial,
) -> DetectedDevice | None:
    """Try safe read-only commands on one port."""
    best_match: DetectedDevice | None = None
    device_types = set(include_device_types)
    module_types = set(include_module_types)

    for probe in _build_probes(device_types, module_types, rs485_addresses):
        detected = _try_probe(
            port,
            probe,
            port_info=port_info,
            timeout=timeout,
            write_timeout=write_timeout if write_timeout is not None else timeout,
            settle_delay=settle_delay,
            serial_factory=serial_factory,
        )
        if detected is None:
            continue

        if best_match is None or detected.confidence > best_match.confidence:
            best_match = detected

        if detected.confidence >= 0.95:
            return detected

    return best_match


def probe_gp350_port(
    port: str,
    *,
    port_info: Any | None = None,
    include_module_types: Iterable[str] = ("digital", "rs232"),
    rs485_addresses: Iterable[int] = (),
    timeout: float = 0.35,
    write_timeout: float | None = None,
    settle_delay: float = 0.05,
    serial_factory: Callable[..., Any] = serial.Serial,
) -> DetectedDevice | None:
    """Try safe GP350 read commands on one port."""
    return probe_serial_port(
        port,
        port_info=port_info,
        include_device_types=("gp350",),
        include_module_types=include_module_types,
        rs485_addresses=rs485_addresses,
        timeout=timeout,
        write_timeout=write_timeout,
        settle_delay=settle_delay,
        serial_factory=serial_factory,
    )


def select_device(
    devices: list[DetectedDevice],
    index: int = 0,
) -> DetectedDevice:
    if not devices:
        raise DeviceDiscoveryError(
            "Nie wykryto obsługiwanego urządzenia na dostępnych portach serial"
        )

    if index < 0 or index >= len(devices):
        raise DeviceDiscoveryError(
            f"Nie ma urządzenia o indeksie {index}; wykryto {len(devices)}"
        )

    return devices[index]


def select_gp350_device(
    devices: list[DetectedDevice],
    index: int = 0,
) -> DetectedDevice:
    return select_device(devices, index)


def _candidate_ports(
    *,
    ports: Iterable[Any] | None,
    port_names: Iterable[str] | None,
) -> list[Any]:
    if port_names is not None:
        return [_ManualPortInfo(port_name) for port_name in port_names]

    raw_ports = list(ports if ports is not None else list_ports.comports())
    return _dedupe_and_sort_ports(
        port_info for port_info in raw_ports if not _is_ignored_port(port_info)
    )


def _dedupe_and_sort_ports(ports: Iterable[Any]) -> list[Any]:
    port_list = list(ports)
    device_names = {_port_device(port_info) for port_info in port_list}
    result: list[Any] = []

    for port_info in port_list:
        device = _port_device(port_info)
        if device.startswith("/dev/tty."):
            cu_twin = "/dev/cu." + device.removeprefix("/dev/tty.")
            if cu_twin in device_names:
                continue
        result.append(port_info)

    return sorted(result, key=lambda port_info: _port_sort_key(_port_device(port_info)))


def _port_sort_key(device: str) -> tuple[int, str]:
    if device.startswith("/dev/cu."):
        return (0, device)
    if device.startswith("/dev/ttyUSB") or device.startswith("/dev/ttyACM"):
        return (1, device)
    if device.startswith("COM"):
        return (2, device)
    return (3, device)


def _is_ignored_port(port_info: Any) -> bool:
    text = " ".join(
        str(getattr(port_info, name, "") or "")
        for name in ("device", "name", "description", "hwid", "manufacturer", "product")
    ).lower()
    return any(keyword in text for keyword in IGNORED_PORT_KEYWORDS)


def _build_probes(
    device_types: set[str],
    module_types: set[str],
    rs485_addresses: Iterable[int],
) -> list[DetectionProbe]:
    probes = []

    if "gp350" in device_types:
        probes.extend(
            probe for probe in GP350_DIRECT_PROBES if probe.module_type in module_types
        )

    if "inficon_vgc402" in device_types and "serial" in module_types:
        probes.extend(VGC402_DIRECT_PROBES)

    if "gp350" in device_types and "digital" in module_types:
        probes.extend(
            DetectionProbe(
                device_type="gp350",
                module_type="digital",
                baudrate=9600,
                bytesize=8,
                parity="none",
                stopbits=1.0,
                line_terminator="\r",
                command="RD",
                rs485_address=address,
            )
            for address in rs485_addresses
        )

    return probes


def _try_probe(
    port: str,
    probe: DetectionProbe,
    *,
    port_info: Any | None,
    timeout: float,
    write_timeout: float,
    settle_delay: float,
    serial_factory: Callable[..., Any],
) -> DetectedDevice | None:
    try:
        with serial_factory(
            port=port,
            baudrate=probe.baudrate,
            bytesize=probe.bytesize,
            parity=PARITY_MAP[probe.parity],
            stopbits=probe.stopbits,
            timeout=timeout,
            write_timeout=write_timeout,
        ) as serial_port:
            if settle_delay > 0:
                time.sleep(settle_delay)

            serial_port.reset_input_buffer()
            serial_port.reset_output_buffer()
            serial_port.write(
                f"{probe.serial_command}{probe.line_terminator}".encode("ascii")
            )
            serial_port.flush()
            raw_response = _read_probe_response(serial_port, probe)
    except (OSError, serial.SerialException):
        return None

    response_text = raw_response.decode("ascii", errors="replace").strip()
    confidence = _score_probe_response(probe, response_text)
    if confidence <= 0:
        return None

    return DetectedDevice(
        device_type=probe.device_type,
        port=port,
        module_type=probe.module_type,
        baudrate=probe.baudrate,
        bytesize=probe.bytesize,
        parity=probe.parity,
        stopbits=probe.stopbits,
        line_terminator=probe.line_terminator,
        command=probe.command,
        rs485_address=probe.rs485_address,
        raw_response=response_text,
        confidence=confidence,
        description=str(getattr(port_info, "description", "") or ""),
        hwid=str(getattr(port_info, "hwid", "") or ""),
        serial_number=str(getattr(port_info, "serial_number", "") or ""),
    )


def _read_probe_response(serial_port: Any, probe: DetectionProbe) -> bytes:
    if probe.protocol == "ack_enq":
        handshake = serial_port.readline()
        if handshake.startswith(NAK.encode("ascii")):
            serial_port.write(ENQ)
            serial_port.flush()
            return b"NAK:" + serial_port.readline()

        if not handshake.startswith(ACK.encode("ascii")):
            return handshake

        serial_port.write(ENQ)
        serial_port.flush()
        return serial_port.readline()

    return _read_response(serial_port, probe.line_terminator)


def _read_response(serial_port: Any, line_terminator: str) -> bytes:
    if line_terminator == "\r":
        data = b""
        while True:
            byte = serial_port.read(1)
            if not byte:
                break
            data += byte
            if byte == b"\r":
                break
        return data

    return serial_port.readline()


def _score_gp350_response(raw_response: str) -> float:
    if not raw_response:
        return 0.0

    cleaned = raw_response.strip()
    normalized = cleaned.upper()
    reading = GP350Parser.parse(cleaned)
    if reading.quality is ParsedQuality.GOOD:
        return 1.0 if not normalized.startswith("*") else 0.98

    if normalized.startswith("*"):
        normalized = normalized[1:].strip()

    if normalized in GP350_NOT_READY_RESPONSES:
        return 0.75

    return 0.0


def _score_probe_response(probe: DetectionProbe, raw_response: str) -> float:
    if probe.device_type == "gp350":
        return _score_gp350_response(raw_response)

    if probe.device_type == "inficon_vgc402":
        return _score_vgc402_response(raw_response)

    return 0.0


def _score_vgc402_response(raw_response: str) -> float:
    if not raw_response:
        return 0.0

    reading = VGC402Parser.parse(raw_response)
    if reading.quality is ParsedQuality.GOOD:
        return 1.0

    if reading.gauge_status is not None:
        return 0.75

    return 0.0


def _port_device(port_info: Any) -> str:
    return str(getattr(port_info, "device", port_info))


@dataclass(frozen=True)
class _ManualPortInfo:
    device: str
    description: str = "manual port"
    hwid: str = ""
    serial_number: str = ""

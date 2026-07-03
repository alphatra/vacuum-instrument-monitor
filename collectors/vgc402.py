import re
from dataclasses import replace

from collectors.measurements import MeasurementReading
from simulators.enums import ParsedQuality

ACK = "\x06"
NAK = "\x15"
ENQ = b"\x05"

VGC402_DEVICE_TYPE = "inficon_vgc402"
VGC402_COMMANDS = {"PR1", "PR2", "PRX"}
VGC402_BAUDRATES = (9600, 19200, 38400)
VGC402_AUTO_PRESSURE_UNIT = "auto"

PRESSURE_UNIT_FACTORS_TO_TORR = {
    "bar": 750.061683,
    "torr": 1.0,
    "mbar": 0.750061683,
    "pa": 0.00750061683,
    "pascal": 0.00750061683,
    "micron": 0.001,
    "microns": 0.001,
}
VGC402_UNIT_CODES = {
    "0": "mbar",
    "1": "Torr",
    "2": "Pa",
    "3": "micron",
}

VGC402_STATUS = {
    0: "ok",
    1: "underrange",
    2: "overrange",
    3: "sensor_error",
    4: "sensor_off",
    5: "no_sensor",
    6: "identification_error",
    7: "bpg_bcg_hpg_error",
}

# Manual §6.3.9 ERR: 4-bit status, combinable with OR (e.g. "1001" = device
# error + syntax error). Bit positions, MSB to LSB:
VGC402_ERR_BITS = (
    (8, "device_error"),
    (4, "hardware_not_installed"),
    (2, "parameter_invalid"),
    (1, "syntax_error"),
)

VGC402_PRESSURE_PATTERN = re.compile(
    r"^\s*(?P<status>[+-]?\d+)\s*,\s*(?P<pressure>[+-]?\d(?:\.\d+)?E[+-]\d+)\s*$",
    re.IGNORECASE,
)


class VGC402Parser:
    @staticmethod
    def parse(
        raw_response: str,
        *,
        pressure_unit: str = "Torr",
    ) -> MeasurementReading:
        cleaned_response = raw_response.strip()

        if cleaned_response == "":
            return MeasurementReading(
                pressure_torr=None,
                unit=None,
                gauge_status=None,
                quality=ParsedQuality.TIMEOUT,
                raw_response=raw_response,
            )

        if cleaned_response.upper().startswith("NAK:"):
            return MeasurementReading(
                pressure_torr=None,
                unit=None,
                gauge_status=_parse_nak_status(cleaned_response),
                quality=ParsedQuality.ERROR,
                raw_response=raw_response,
            )

        match = VGC402_PRESSURE_PATTERN.match(cleaned_response)
        if not match:
            return MeasurementReading(
                pressure_torr=None,
                unit=None,
                gauge_status=None,
                quality=ParsedQuality.BAD_FORMAT,
                raw_response=raw_response,
            )

        status_code = int(match.group("status"))
        gauge_status = VGC402_STATUS.get(status_code, f"status_{status_code}")
        if status_code != 0:
            return MeasurementReading(
                pressure_torr=None,
                unit=None,
                gauge_status=gauge_status,
                quality=ParsedQuality.ERROR,
                raw_response=raw_response,
            )

        try:
            pressure_torr = _convert_pressure_to_torr(
                float(match.group("pressure")),
                pressure_unit,
            )
        except ValueError:
            return MeasurementReading(
                pressure_torr=None,
                unit=None,
                gauge_status=gauge_status,
                quality=ParsedQuality.BAD_FORMAT,
                raw_response=raw_response,
            )

        return MeasurementReading(
            pressure_torr=pressure_torr,
            unit="Torr",
            gauge_status=gauge_status,
            quality=ParsedQuality.GOOD,
            raw_response=raw_response,
        )

    @staticmethod
    def parse_many(
        raw_response: str,
        *,
        command: str,
        pressure_unit: str = "Torr",
    ) -> list[MeasurementReading]:
        if command.upper() != "PRX":
            return [VGC402Parser.parse(raw_response, pressure_unit=pressure_unit)]

        cleaned_response = raw_response.strip()
        if cleaned_response == "" or cleaned_response.upper().startswith("NAK:"):
            return [VGC402Parser.parse(raw_response, pressure_unit=pressure_unit)]

        parts = [part.strip() for part in cleaned_response.split(",")]
        if len(parts) < 2 or len(parts) % 2 != 0:
            return [
                MeasurementReading(
                    pressure_torr=None,
                    unit=None,
                    gauge_status=None,
                    quality=ParsedQuality.BAD_FORMAT,
                    raw_response=raw_response,
                )
            ]

        readings = []
        for index in range(0, len(parts), 2):
            channel_response = f"{parts[index]},{parts[index + 1]}"
            reading = VGC402Parser.parse(
                channel_response,
                pressure_unit=pressure_unit,
            )
            readings.append(replace(reading, raw_response=raw_response))

        return readings


def _parse_nak_status(raw_response: str) -> str:
    _, _, raw_code = raw_response.partition(":")
    code = raw_code.strip()
    if not code:
        return "nak"

    try:
        mask = int(code, 2)
    except ValueError:
        return f"nak_{code}"

    if mask == 0:
        return "no_error"

    names = [name for bit, name in VGC402_ERR_BITS if mask & bit]
    if not names:
        return f"nak_{code}"

    return "+".join(names)


def parse_unit_response(raw_response: str) -> str:
    cleaned_response = raw_response.strip()
    if cleaned_response.upper().startswith("NAK:"):
        raise ValueError(f"VGC402 rejected UNI command: {cleaned_response}")

    if cleaned_response not in VGC402_UNIT_CODES:
        raise ValueError(f"Unsupported VGC402 UNI response: {raw_response!r}")

    return VGC402_UNIT_CODES[cleaned_response]


def normalize_pressure_unit(pressure_unit: str) -> str:
    normalized = pressure_unit.strip().lower()
    if normalized in {"pascal", "pascals"}:
        normalized = "pa"
    if normalized in {"micron", "microns"}:
        normalized = "micron"

    if normalized not in PRESSURE_UNIT_FACTORS_TO_TORR:
        raise ValueError(f"Unsupported pressure unit: {pressure_unit}")

    return normalized


def _convert_pressure_to_torr(value: float, pressure_unit: str) -> float:
    unit = normalize_pressure_unit(pressure_unit)
    return value * PRESSURE_UNIT_FACTORS_TO_TORR[unit]

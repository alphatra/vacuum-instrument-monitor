import re
from dataclasses import dataclass

from .enums import GaugeStatus, ParsedQuality

PRESSURE_PATTERN = re.compile(r"^[+-]?\d\.\d{2}E[+-]\d{2}$", re.IGNORECASE)
IG_NOT_READY_VALUES = {"9.90E+09", "9.90E+9", "9.9E+09", "9.9E+9"}
RS232_ERROR_MESSAGES = {
    "OVERRUN ERROR",
    "PARITY ERROR",
    "SYNTAX ERROR",
    "INVALID",
}
DIGITAL_ERROR_PREFIXES = ("? OVERR", "? PRITY", "? SYNTX", "? RAM", "? INVALID")


@dataclass(frozen=True)
class GP350Reading:
    # Parsed response with quality flag for downstream logic.
    pressure_torr: float | None
    unit: str | None
    gauge_status: GaugeStatus | None
    quality: ParsedQuality
    raw_response: str


class GP350Parser:
    @staticmethod
    def parse(raw_response: str) -> GP350Reading:
        cleaned_response = raw_response.strip()

        if cleaned_response == "":
            return GP350Reading(
                pressure_torr=None,
                unit=None,
                gauge_status=None,
                quality=ParsedQuality.TIMEOUT,
                raw_response=raw_response,
            )

        if cleaned_response == "???":
            return GP350Reading(
                pressure_torr=None,
                unit=None,
                gauge_status=None,
                quality=ParsedQuality.BAD_FORMAT,
                raw_response=raw_response,
            )

        normalized = cleaned_response.upper()
        if (
            normalized in RS232_ERROR_MESSAGES
            or normalized in IG_NOT_READY_VALUES
            or normalized.startswith(DIGITAL_ERROR_PREFIXES)
        ):
            return GP350Reading(
                pressure_torr=None,
                unit=None,
                gauge_status=None,
                quality=ParsedQuality.ERROR,
                raw_response=raw_response,
            )

        if normalized.startswith("*"):
            cleaned_response = cleaned_response[1:].strip()

        try:
            pressure_torr, unit = GP350Parser._parse_pressure(cleaned_response)

            return GP350Reading(
                pressure_torr=pressure_torr,
                unit=unit,
                gauge_status=None,
                quality=ParsedQuality.GOOD,
                raw_response=raw_response,
            )

        except (ValueError, IndexError):
            return GP350Reading(
                pressure_torr=None,
                unit=None,
                gauge_status=None,
                quality=ParsedQuality.BAD_FORMAT,
                raw_response=raw_response,
            )

    @staticmethod
    def _parse_pressure(text: str) -> tuple[float, str]:
        cleaned_text = text.strip()

        if not PRESSURE_PATTERN.match(cleaned_text):
            raise ValueError("Expected GP350 pressure format X.XXE+XX")

        return float(cleaned_text), "Torr"

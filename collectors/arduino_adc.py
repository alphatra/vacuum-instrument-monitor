"""Parser for the Arduino analog bridge.

The sketch in ``firmware/gp350_adc`` answers ``READ`` with ``V=<volts>``,
where <volts> is the voltage measured on its A0 pin - already averaged on
the board. The divider maths is done here, on the Pi, so recalibrating
never means reflashing the Arduino.
"""

from __future__ import annotations

import re
from typing import Any

from collectors.analog import (
    divider_ratio,
    emission_voltage_offset,
    reading_from_adc_voltage,
)
from collectors.measurements import MeasurementReading
from simulators.enums import ParsedQuality

ARDUINO_ADC_DEVICE_TYPE = "arduino_adc"
ARDUINO_ADC_COMMANDS = {"READ"}
ARDUINO_ADC_BAUDRATES = (9600, 19200, 57600, 115200)

VOLTAGE_PATTERN = re.compile(r"^V=\s*(?P<volts>[+-]?\d+(?:\.\d+)?)$", re.IGNORECASE)
IDENTITY_PATTERN = re.compile(r"^ID=(?P<identity>\S+)$", re.IGNORECASE)


def _failed(quality: ParsedQuality, raw_response: str) -> MeasurementReading:
    return MeasurementReading(
        pressure_torr=None,
        unit=None,
        gauge_status=None,
        quality=quality,
        raw_response=raw_response,
    )


class ArduinoAdcParser:
    @staticmethod
    def parse(raw_response: str, cfg: Any) -> MeasurementReading:
        cleaned = raw_response.strip()

        if cleaned == "":
            return _failed(ParsedQuality.TIMEOUT, raw_response)

        if cleaned.upper() == "ERR":
            # Board rejected the command; not a measurement problem.
            return _failed(ParsedQuality.ERROR, raw_response)

        match = VOLTAGE_PATTERN.match(cleaned)
        if not match:
            return _failed(ParsedQuality.BAD_FORMAT, raw_response)

        adc_voltage = float(match.group("volts"))

        return reading_from_adc_voltage(
            adc_voltage,
            ratio=divider_ratio(cfg.divider_top_ohms, cfg.divider_bottom_ohms),
            signal_voltage_offset=cfg.signal_voltage_offset,
            emission_offset=emission_voltage_offset(cfg.emission_current_ma),
            fault_voltage_threshold=cfg.fault_voltage_threshold,
            raw_response=raw_response,
        )


def is_arduino_adc_response(raw_response: str) -> bool:
    """True when a probe reply looks like this firmware."""
    cleaned = raw_response.strip()
    return bool(VOLTAGE_PATTERN.match(cleaned) or IDENTITY_PATTERN.match(cleaned))

"""Shared conversion from a GP350 analog output voltage to pressure.

Two collectors read the same 0-10 V signal through different hardware:
an ADS1115 over I2C, and an Arduino sending voltages over USB serial.
Only the way the voltage is acquired differs, so the divider maths, the
fault thresholds and the GP350 decade formula live here.
"""

from __future__ import annotations

import math

from collectors.measurements import MeasurementReading
from simulators.enums import ParsedQuality

# GP350 analog output is offset by the configured emission current range.
GP350_ANALOG_EMISSION_OFFSETS = {10.0: 12.0, 1.0: 11.0, 0.1: 10.0}


def divider_ratio(top_ohms: float, bottom_ohms: float) -> float:
    """Factor that turns the divided voltage back into the GP350 output."""
    return (top_ohms + bottom_ohms) / bottom_ohms


def emission_voltage_offset(emission_current_ma: float) -> float:
    try:
        return GP350_ANALOG_EMISSION_OFFSETS[emission_current_ma]
    except KeyError as error:
        raise ValueError("emission_current_ma must be 0.1, 1 or 10") from error


def reading_from_adc_voltage(
    adc_voltage: float,
    *,
    ratio: float,
    signal_voltage_offset: float,
    emission_offset: float,
    fault_voltage_threshold: float,
    raw_response: str,
    adc_raw: int | None = None,
) -> MeasurementReading:
    """Turn one measured ADC voltage into a pressure reading."""
    signal_voltage = adc_voltage * ratio
    calibrated_voltage = signal_voltage + signal_voltage_offset

    def failed(status: str) -> MeasurementReading:
        return MeasurementReading(
            pressure_torr=None,
            unit=None,
            gauge_status=status,
            quality=ParsedQuality.ERROR,
            raw_response=raw_response,
            adc_voltage=adc_voltage,
            signal_voltage=signal_voltage,
            adc_raw=adc_raw,
        )

    if adc_voltage < 0:
        return failed("adc_underrange")

    if calibrated_voltage >= fault_voltage_threshold:
        # GP350 parks slightly above 10 V when the ion gauge is off.
        return failed("gauge_off_or_overrange")

    return MeasurementReading(
        pressure_torr=math.pow(10.0, calibrated_voltage - emission_offset),
        unit="Torr",
        gauge_status="ok",
        quality=ParsedQuality.GOOD,
        raw_response=raw_response,
        adc_voltage=adc_voltage,
        signal_voltage=signal_voltage,
        adc_raw=adc_raw,
    )

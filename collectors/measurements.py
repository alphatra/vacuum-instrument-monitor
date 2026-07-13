from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulators.enums import ParsedQuality


@dataclass(frozen=True)
class MeasurementReading:
    # Common parsed reading used by all supported vacuum instruments.
    pressure_torr: float | None
    unit: str | None
    gauge_status: str | None
    quality: ParsedQuality
    raw_response: str
    adc_voltage: float | None = None
    signal_voltage: float | None = None
    adc_raw: int | None = None

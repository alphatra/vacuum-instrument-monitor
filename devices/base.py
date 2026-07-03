from typing import Any, Protocol

from collectors.measurements import MeasurementReading


class DeviceProfile(Protocol):
    device_type: str

    def read_response(self, client: Any, command: str) -> str:
        """Read one raw response from a configured serial client."""

    def resolve_runtime_config(self, cfg: Any, client: Any) -> Any:
        """Return config adjusted with values read from the instrument."""

    def parse_response(self, raw_response: str, cfg: Any) -> MeasurementReading:
        """Parse one raw response for backward-compatible single-reading paths."""

    def parse_readings(self, raw_response: str, cfg: Any) -> list[MeasurementReading]:
        """Parse one raw response into one or more channel readings."""

    def channels_for_readings(self, cfg: Any, reading_count: int) -> list[str]:
        """Return CSV/Influx channel labels for parsed readings."""

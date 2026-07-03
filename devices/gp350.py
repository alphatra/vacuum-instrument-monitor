from typing import Any

from collectors.measurements import MeasurementReading
from simulators import GP350Parser


class GP350DeviceProfile:
    device_type = "gp350"

    def read_response(self, client: Any, command: str) -> str:
        return client.send_command(command)

    def resolve_runtime_config(self, cfg: Any, client: Any) -> Any:
        return cfg

    def parse_response(self, raw_response: str, cfg: Any) -> MeasurementReading:
        return GP350Parser.parse(raw_response)

    def parse_readings(self, raw_response: str, cfg: Any) -> list[MeasurementReading]:
        return [self.parse_response(raw_response, cfg)]

    def channels_for_readings(self, cfg: Any, reading_count: int) -> list[str]:
        return [cfg.channel] * reading_count


GP350_PROFILE = GP350DeviceProfile()

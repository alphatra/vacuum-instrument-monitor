from typing import Any

from collectors.arduino_adc import ARDUINO_ADC_DEVICE_TYPE, ArduinoAdcParser
from collectors.measurements import MeasurementReading


class ArduinoAdcDeviceProfile:
    device_type = ARDUINO_ADC_DEVICE_TYPE

    def read_response(self, client: Any, command: str) -> str:
        return client.send_command(command)

    def resolve_runtime_config(self, cfg: Any, client: Any) -> Any:
        return cfg

    def parse_response(self, raw_response: str, cfg: Any) -> MeasurementReading:
        return ArduinoAdcParser.parse(raw_response, cfg)

    def parse_readings(self, raw_response: str, cfg: Any) -> list[MeasurementReading]:
        return [self.parse_response(raw_response, cfg)]

    def channels_for_readings(self, cfg: Any, reading_count: int) -> list[str]:
        return [cfg.channel] * reading_count


ARDUINO_ADC_PROFILE = ArduinoAdcDeviceProfile()

import logging
from dataclasses import replace
from typing import Any

from collectors.measurements import MeasurementReading
from collectors.vgc402 import (
    VGC402_AUTO_PRESSURE_UNIT,
    VGC402_DEVICE_TYPE,
    VGC402Parser,
    parse_unit_response,
)


class VGC402DeviceProfile:
    device_type = VGC402_DEVICE_TYPE

    def read_response(self, client: Any, command: str) -> str:
        return client.send_ack_enq_command(command)

    def resolve_runtime_config(self, cfg: Any, client: Any) -> Any:
        if cfg.pressure_unit.lower() != VGC402_AUTO_PRESSURE_UNIT:
            return cfg

        raw_unit = client.send_ack_enq_command("UNI")
        pressure_unit = parse_unit_response(raw_unit)
        logging.info(
            "VGC402 pressure_unit auto resolved to %s from UNI raw=%r",
            pressure_unit,
            raw_unit,
        )
        return replace(cfg, pressure_unit=pressure_unit)

    def parse_response(self, raw_response: str, cfg: Any) -> MeasurementReading:
        return VGC402Parser.parse(raw_response, pressure_unit=cfg.pressure_unit)

    def parse_readings(self, raw_response: str, cfg: Any) -> list[MeasurementReading]:
        return VGC402Parser.parse_many(
            raw_response,
            command=cfg.command,
            pressure_unit=cfg.pressure_unit,
        )

    def channels_for_readings(self, cfg: Any, reading_count: int) -> list[str]:
        if cfg.command.upper() == "PRX":
            return [f"CH{index + 1}" for index in range(reading_count)]

        return [cfg.channel] * reading_count


VGC402_PROFILE = VGC402DeviceProfile()

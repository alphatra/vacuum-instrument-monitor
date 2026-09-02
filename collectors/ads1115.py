from __future__ import annotations

import configparser
import math
import os
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from smbus2 import SMBus

from collectors.config import ConfigValidationError
from collectors.measurements import MeasurementReading
from simulators.enums import ParsedQuality

ADS1115_DEFAULT_ADDRESS = 0x48
ADS1115_CONFIG_REGISTER = 0x01
ADS1115_CONVERSION_REGISTER = 0x00
ADS1115_PGA_BITS = {2 / 3: 0, 1.0: 1, 2.0: 2, 4.0: 3, 8.0: 4, 16.0: 5}
ADS1115_LSB_VOLTS = {
    2 / 3: 0.0001875,
    1.0: 0.000125,
    2.0: 0.0000625,
    4.0: 0.00003125,
    8.0: 0.000015625,
    16.0: 0.0000078125,
}
ADS1115_DATA_RATE_BITS = {
    8: 0,
    16: 1,
    32: 2,
    64: 3,
    128: 4,
    250: 5,
    475: 6,
    860: 7,
}
GP350_ANALOG_EMISSION_OFFSETS = {10.0: 12.0, 1.0: 11.0, 0.1: 10.0}


class I2cBus(Protocol):
    def write_i2c_block_data(
        self,
        address: int,
        register: int,
        data: list[int],
    ) -> None: ...

    def read_i2c_block_data(
        self,
        address: int,
        register: int,
        length: int,
    ) -> list[int]: ...

    def close(self) -> None: ...


class AnalogReader(Protocol):
    @property
    def lsb_volts(self) -> float: ...

    def read_raw(self) -> int: ...


class ADS1115:
    """Minimal ADS1115 single-ended reader using the Raspberry Pi I2C bus."""

    def __init__(
        self,
        *,
        bus_id: int,
        address: int,
        channel: int,
        pga_gain: float,
        data_rate: int,
        bus: I2cBus | None = None,
    ):
        self.address = address
        self.channel = channel
        self.pga_gain = pga_gain
        self.data_rate = data_rate
        self.bus = bus if bus is not None else SMBus(bus_id)

    @property
    def lsb_volts(self) -> float:
        return ADS1115_LSB_VOLTS[self.pga_gain]

    def read_raw(self) -> int:
        mux_bits = 0x4 + self.channel
        config = (
            0x8000  # OS: start one conversion
            | (mux_bits << 12)  # MUX: AINx relative to GND
            | (ADS1115_PGA_BITS[self.pga_gain] << 9)
            | 0x0100  # MODE: single shot
            | (ADS1115_DATA_RATE_BITS[self.data_rate] << 5)
            | 0x0003  # comparator disabled
        )
        self._write_register(ADS1115_CONFIG_REGISTER, config)

        deadline = time.monotonic() + max(0.1, 2.0 / self.data_rate)
        while time.monotonic() < deadline:
            if self._read_register(ADS1115_CONFIG_REGISTER) & 0x8000:
                raw_value = self._read_register(ADS1115_CONVERSION_REGISTER)
                return raw_value - 0x10000 if raw_value & 0x8000 else raw_value
            time.sleep(0.001)

        raise TimeoutError("ADS1115 conversion timed out")

    def close(self) -> None:
        self.bus.close()

    def _write_register(self, register: int, value: int) -> None:
        self.bus.write_i2c_block_data(
            self.address,
            register,
            [(value >> 8) & 0xFF, value & 0xFF],
        )

    def _read_register(self, register: int) -> int:
        high, low = self.bus.read_i2c_block_data(self.address, register, 2)
        return (high << 8) | low


@dataclass(frozen=True)
class Ads1115Config:
    debug: bool = False
    log_level: str = "info"
    interval_seconds: float = 1.0
    device_name: str = "GP350_1"
    channel: str = "IG1"
    i2c_bus: int = 1
    i2c_address: int = ADS1115_DEFAULT_ADDRESS
    ads_channel: int = 0
    pga_gain: float = 1.0
    data_rate: int = 128
    samples_per_reading: int = 5
    divider_top_ohms: float = 68_000.0
    divider_bottom_ohms: float = 22_000.0
    signal_voltage_offset: float = 0.0
    emission_current_ma: float = 1.0
    fault_voltage_threshold: float = 10.05
    csv_filepath: str = "data/gp350_analog_readings.csv"
    csv_mode: str = "append"
    log_file: str = "logs/gp350_analog_collector.log"
    influx_enabled: bool = False
    influx_url: str = "http://localhost:8086"
    influx_org: str = ""
    influx_bucket: str = ""
    influx_token: str = ""
    influx_token_env: str = "INFLUXDB_TOKEN"
    influx_measurement: str = "vacuum_pressure"
    influx_timeout: float = 2.0
    influx_retries: int = 0
    influx_fail_on_error: bool = False
    path: str = "config/gp350-analog-ads1115.ini"

    @classmethod
    def from_file(cls, path: str) -> Ads1115Config:
        config = configparser.ConfigParser()
        defaults = cls(path=path)
        if os.path.exists(path):
            config.read(path)

        try:
            app_config = cls(
                debug=config.getboolean("General", "debug", fallback=defaults.debug),
                log_level=config.get(
                    "General", "log_level", fallback=defaults.log_level
                ).lower(),
                interval_seconds=config.getfloat(
                    "Collector",
                    "interval_seconds",
                    fallback=defaults.interval_seconds,
                ),
                device_name=config.get(
                    "Device", "device_name", fallback=defaults.device_name
                ).strip(),
                channel=config.get(
                    "Device", "channel", fallback=defaults.channel
                ).strip(),
                i2c_bus=config.getint("ADS1115", "i2c_bus", fallback=defaults.i2c_bus),
                i2c_address=int(
                    config.get(
                        "ADS1115",
                        "i2c_address",
                        fallback=hex(defaults.i2c_address),
                    ),
                    0,
                ),
                ads_channel=config.getint(
                    "ADS1115", "channel", fallback=defaults.ads_channel
                ),
                pga_gain=_normalize_pga_gain(
                    config.getfloat("ADS1115", "pga_gain", fallback=defaults.pga_gain)
                ),
                data_rate=config.getint(
                    "ADS1115", "data_rate", fallback=defaults.data_rate
                ),
                samples_per_reading=config.getint(
                    "ADS1115",
                    "samples_per_reading",
                    fallback=defaults.samples_per_reading,
                ),
                divider_top_ohms=config.getfloat(
                    "Calibration",
                    "divider_top_ohms",
                    fallback=defaults.divider_top_ohms,
                ),
                divider_bottom_ohms=config.getfloat(
                    "Calibration",
                    "divider_bottom_ohms",
                    fallback=defaults.divider_bottom_ohms,
                ),
                signal_voltage_offset=config.getfloat(
                    "Calibration",
                    "signal_voltage_offset",
                    fallback=defaults.signal_voltage_offset,
                ),
                emission_current_ma=config.getfloat(
                    "GP350",
                    "emission_current_ma",
                    fallback=defaults.emission_current_ma,
                ),
                fault_voltage_threshold=config.getfloat(
                    "GP350",
                    "fault_voltage_threshold",
                    fallback=defaults.fault_voltage_threshold,
                ),
                csv_filepath=config.get(
                    "File", "csv_filepath", fallback=defaults.csv_filepath
                ),
                csv_mode=config.get(
                    "File", "csv_mode", fallback=defaults.csv_mode
                ).lower(),
                log_file=config.get("File", "log_file", fallback=defaults.log_file),
                influx_enabled=config.getboolean(
                    "InfluxDB", "enabled", fallback=defaults.influx_enabled
                ),
                influx_url=config.get(
                    "InfluxDB", "url", fallback=defaults.influx_url
                ).rstrip("/"),
                influx_org=config.get(
                    "InfluxDB", "org", fallback=defaults.influx_org
                ).strip(),
                influx_bucket=config.get(
                    "InfluxDB", "bucket", fallback=defaults.influx_bucket
                ).strip(),
                influx_token=config.get(
                    "InfluxDB", "token", fallback=defaults.influx_token
                ).strip(),
                influx_token_env=config.get(
                    "InfluxDB",
                    "token_env",
                    fallback=defaults.influx_token_env,
                ).strip(),
                influx_measurement=config.get(
                    "InfluxDB",
                    "measurement",
                    fallback=defaults.influx_measurement,
                ).strip(),
                influx_timeout=config.getfloat(
                    "InfluxDB", "timeout", fallback=defaults.influx_timeout
                ),
                influx_retries=config.getint(
                    "InfluxDB", "retries", fallback=defaults.influx_retries
                ),
                influx_fail_on_error=config.getboolean(
                    "InfluxDB",
                    "fail_on_error",
                    fallback=defaults.influx_fail_on_error,
                ),
                path=path,
            )
        except (ValueError, configparser.Error) as error:
            raise ConfigValidationError(
                f"Błąd konfiguracji ADS1115: {error}"
            ) from error

        app_config.validate()
        return app_config

    @property
    def divider_ratio(self) -> float:
        return (self.divider_top_ohms + self.divider_bottom_ohms) / (
            self.divider_bottom_ohms
        )

    @property
    def emission_voltage_offset(self) -> float:
        return GP350_ANALOG_EMISSION_OFFSETS[self.emission_current_ma]

    @property
    def resolved_influx_token(self) -> str:
        if self.influx_token:
            return self.influx_token
        if not self.influx_token_env:
            return ""
        return os.environ.get(self.influx_token_env, "")

    def validate(self) -> None:
        if self.log_level not in {"debug", "info", "warning", "error"}:
            raise ConfigValidationError("General.log_level ma nieprawidłową wartość")
        if self.interval_seconds <= 0:
            raise ConfigValidationError("Collector.interval_seconds musi być dodatni")
        if not self.device_name or not self.channel:
            raise ConfigValidationError(
                "Device.device_name i Device.channel nie mogą być puste"
            )
        if self.i2c_bus < 0:
            raise ConfigValidationError("ADS1115.i2c_bus nie może być ujemny")
        if not 0x03 <= self.i2c_address <= 0x77:
            raise ConfigValidationError("ADS1115.i2c_address musi być adresem I2C")
        if self.ads_channel not in {0, 1, 2, 3}:
            raise ConfigValidationError("ADS1115.channel musi być w zakresie 0-3")
        if self.pga_gain not in ADS1115_PGA_BITS:
            raise ConfigValidationError(
                "ADS1115.pga_gain musi mieć wartość 0.666667, 1, 2, 4, 8 albo 16"
            )
        if self.data_rate not in ADS1115_DATA_RATE_BITS:
            raise ConfigValidationError(
                "ADS1115.data_rate musi mieć wartość 8, 16, 32, 64, 128, 250, "
                "475 albo 860"
            )
        if self.samples_per_reading < 1 or self.samples_per_reading % 2 == 0:
            raise ConfigValidationError(
                "ADS1115.samples_per_reading musi być dodatnią liczbą nieparzystą"
            )
        if self.divider_top_ohms <= 0 or self.divider_bottom_ohms <= 0:
            raise ConfigValidationError("Rezystory dzielnika muszą być dodatnie")
        if self.emission_current_ma not in GP350_ANALOG_EMISSION_OFFSETS:
            raise ConfigValidationError(
                "GP350.emission_current_ma musi mieć wartość 0.1, 1 albo 10"
            )
        if self.fault_voltage_threshold <= 0:
            raise ConfigValidationError(
                "GP350.fault_voltage_threshold musi być dodatni"
            )
        if self.csv_mode not in {"overwrite", "append"}:
            raise ConfigValidationError(
                "File.csv_mode musi mieć wartość overwrite albo append"
            )
        if self.influx_enabled:
            if not self.influx_url.startswith(("http://", "https://")):
                raise ConfigValidationError(
                    "InfluxDB.url musi zaczynać się od http:// albo https://"
                )
            if not self.influx_org or not self.influx_bucket:
                raise ConfigValidationError(
                    "InfluxDB.org i InfluxDB.bucket nie mogą być puste"
                )
            if not self.resolved_influx_token:
                raise ConfigValidationError(
                    "Ustaw InfluxDB.token albo zmienną z InfluxDB.token_env"
                )
            if not self.influx_measurement or self.influx_timeout <= 0:
                raise ConfigValidationError("Konfiguracja InfluxDB jest niepoprawna")
            if self.influx_retries < 0:
                raise ConfigValidationError("InfluxDB.retries nie może być ujemne")
        try:
            Path(self.csv_filepath)
            Path(self.log_file)
        except Exception as error:
            raise ConfigValidationError("Ścieżka pliku jest niepoprawna") from error


def read_gp350_analog(
    adc: AnalogReader,
    cfg: Ads1115Config,
) -> MeasurementReading:
    raw_value = int(
        statistics.median(adc.read_raw() for _ in range(cfg.samples_per_reading))
    )
    adc_voltage = raw_value * adc.lsb_volts
    signal_voltage = adc_voltage * cfg.divider_ratio
    calibrated_voltage = signal_voltage + cfg.signal_voltage_offset
    raw_response = (
        f"adc_raw={raw_value},adc_voltage={adc_voltage:.6f},"
        f"signal_voltage={signal_voltage:.6f}"
    )

    if raw_value < 0 or raw_value >= 32760:
        return MeasurementReading(
            pressure_torr=None,
            unit=None,
            gauge_status="adc_overrange",
            quality=ParsedQuality.ERROR,
            raw_response=raw_response,
            adc_voltage=adc_voltage,
            signal_voltage=signal_voltage,
            adc_raw=raw_value,
        )

    if calibrated_voltage >= cfg.fault_voltage_threshold:
        return MeasurementReading(
            pressure_torr=None,
            unit=None,
            gauge_status="gauge_off_or_overrange",
            quality=ParsedQuality.ERROR,
            raw_response=raw_response,
            adc_voltage=adc_voltage,
            signal_voltage=signal_voltage,
            adc_raw=raw_value,
        )

    pressure_torr = math.pow(
        10.0,
        calibrated_voltage - cfg.emission_voltage_offset,
    )
    return MeasurementReading(
        pressure_torr=pressure_torr,
        unit="Torr",
        gauge_status="ok",
        quality=ParsedQuality.GOOD,
        raw_response=raw_response,
        adc_voltage=adc_voltage,
        signal_voltage=signal_voltage,
        adc_raw=raw_value,
    )


def _normalize_pga_gain(value: float) -> float:
    if math.isclose(value, 2 / 3, rel_tol=0.0, abs_tol=0.000_001):
        return 2 / 3
    return value

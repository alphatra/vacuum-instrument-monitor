import math

import pytest

from collectors.ads1115 import ADS1115, Ads1115Config, read_gp350_analog
from simulators.enums import ParsedQuality


class FakeBus:
    def __init__(self) -> None:
        self.writes: list[tuple[int, int, list[int]]] = []
        self.closed = False

    def write_i2c_block_data(
        self,
        address: int,
        register: int,
        data: list[int],
    ) -> None:
        self.writes.append((address, register, data))

    def read_i2c_block_data(
        self,
        address: int,
        register: int,
        length: int,
    ) -> list[int]:
        assert address == 0x48
        assert length == 2
        if register == 0x01:
            return [0xC3, 0x83]
        assert register == 0x00
        return [0x19, 0x68]

    def close(self) -> None:
        self.closed = True


class FakeAdc:
    lsb_volts = 0.000125

    def __init__(self, raw_value: int) -> None:
        self.raw_value = raw_value

    def read_raw(self) -> int:
        return self.raw_value


def test_ads1115_reads_single_ended_a0() -> None:
    bus = FakeBus()
    adc = ADS1115(
        bus_id=1,
        address=0x48,
        channel=0,
        pga_gain=1.0,
        data_rate=128,
        bus=bus,
    )

    raw_value = adc.read_raw()
    adc.close()

    assert raw_value == 6504
    assert bus.writes == [(0x48, 0x01, [0xC3, 0x83])]
    assert bus.closed is True


def test_gp350_analog_conversion_uses_divider_and_emission_range() -> None:
    cfg = Ads1115Config(samples_per_reading=3, emission_current_ma=1.0)

    reading = read_gp350_analog(FakeAdc(6600), cfg)

    assert reading.quality is ParsedQuality.GOOD
    assert reading.adc_voltage == pytest.approx(0.825)
    assert reading.signal_voltage == pytest.approx(3.375)
    assert reading.pressure_torr == pytest.approx(math.pow(10, 3.375 - 11))
    assert reading.gauge_status == "ok"


def test_gp350_analog_marks_gauge_off_voltage_as_error() -> None:
    cfg = Ads1115Config(samples_per_reading=1, fault_voltage_threshold=10.05)

    reading = read_gp350_analog(FakeAdc(20_000), cfg)

    assert reading.quality is ParsedQuality.ERROR
    assert reading.pressure_torr is None
    assert reading.gauge_status == "gauge_off_or_overrange"


def test_ads1115_config_reads_divider_and_i2c_settings(tmp_path) -> None:
    config_path = tmp_path / "gp350-analog.ini"
    config_path.write_text(
        """
[ADS1115]
i2c_bus = 1
i2c_address = 0x49
channel = 2
pga_gain = 1
data_rate = 250
samples_per_reading = 3

[Calibration]
divider_top_ohms = 68000
divider_bottom_ohms = 22000

[GP350]
emission_current_ma = 10
""",
        encoding="utf-8",
    )

    cfg = Ads1115Config.from_file(str(config_path))

    assert cfg.i2c_address == 0x49
    assert cfg.ads_channel == 2
    assert cfg.divider_ratio == pytest.approx(90 / 22)
    assert cfg.emission_voltage_offset == 12.0

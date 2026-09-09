from __future__ import annotations

import argparse
import datetime
import logging
import time
from pathlib import Path

from collectors.ads1115 import ADS1115, Ads1115Config, read_gp350_analog
from collectors.config import ConfigValidationError
from collectors.csv_writer import CsvWriter, MeasurementRecord
from collectors.influx_writer import InfluxConfig, InfluxWriter
from collectors.measurements import MeasurementReading
from simulators.enums import ParsedQuality

# A sensor that keeps failing should surface as a failed unit, not as a
# healthy one producing nothing.
MAX_CONSECUTIVE_ERRORS = 10


class FailureRun:
    """Tracks one continuous run of failures.

    The first failure carries the stack trace; repeats of the same fault get
    a short line, so an unplugged sensor cannot flood the journal.
    """

    def __init__(self, limit: int = MAX_CONSECUTIVE_ERRORS):
        self.limit = limit
        self.count = 0

    def failure(self) -> tuple[bool, bool]:
        """Return (log_traceback, reached_limit)."""
        self.count += 1
        return self.count == 1, self.count >= self.limit

    def success(self) -> None:
        self.count = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kolektor GP350 przez ADS1115")
    parser.add_argument(
        "--config",
        default="config/examples/gp350-analog-ads1115.ini",
        help="Ścieżka do pliku konfiguracji ADS1115",
    )
    return parser.parse_args()


def setup_logging(cfg: Ads1115Config) -> None:
    Path(cfg.log_file).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, cfg.log_level.upper()),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(cfg.log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )


def build_influx_writer(cfg: Ads1115Config) -> InfluxWriter | None:
    if not cfg.influx_enabled:
        return None
    return InfluxWriter(
        InfluxConfig(
            url=cfg.influx_url,
            org=cfg.influx_org,
            bucket=cfg.influx_bucket,
            token=cfg.resolved_influx_token,
            measurement=cfg.influx_measurement,
            timeout=cfg.influx_timeout,
            retries=cfg.influx_retries,
            device_type="gp350",
            module_type="i2c",
            command="analog_output",
            username=cfg.influx_username,
            write_path=cfg.influx_write_path,
        )
    )


def error_reading(error: Exception) -> MeasurementReading:
    return MeasurementReading(
        pressure_torr=None,
        unit=None,
        gauge_status="i2c_error",
        quality=ParsedQuality.ERROR,
        raw_response=f"i2c_error: {error}",
    )


def run_collection_loop(
    adc: ADS1115,
    cfg: Ads1115Config,
    writer: CsvWriter,
    influx_writer: InfluxWriter | None,
    *,
    max_iterations: int | None = None,
) -> None:
    """Read, record and publish until interrupted.

    max_iterations bounds the loop for tests; production leaves it unset.
    """
    iterations = 0
    failures = FailureRun()

    while max_iterations is None or iterations < max_iterations:
        iterations += 1
        loop_start = time.monotonic()
        measurement_start = time.monotonic()
        stop_after_write = False
        try:
            reading = read_gp350_analog(adc, cfg)
            failures.success()
        except Exception as error:
            log_traceback, stop_after_write = failures.failure()
            if log_traceback:
                logging.exception("Błąd odczytu ADS1115: %s", error)
            else:
                logging.error(
                    "Błąd odczytu ADS1115 (%s z rzędu): %s", failures.count, error
                )
            reading = error_reading(error)
        latency_ms = (time.monotonic() - measurement_start) * 1000.0
        timestamp = datetime.datetime.now(datetime.UTC).isoformat()
        record = MeasurementRecord(
            timestamp=timestamp,
            device=cfg.device_name,
            channel=cfg.channel,
            latency_ms=latency_ms,
            reading=reading,
        )
        writer.write(record)
        if influx_writer is not None:
            try:
                influx_writer.write(record)
            except Exception as error:
                logging.exception("Błąd zapisu InfluxDB: %s", error)
                if cfg.influx_fail_on_error:
                    raise

        log = (
            logging.warning
            if reading.quality is not ParsedQuality.GOOD
            else logging.info
        )
        log(
            "Pomiar channel=%s quality=%s pressure=%s signal_voltage=%s "
            "adc_voltage=%s raw=%s latency=%.2fms",
            record.channel,
            reading.quality.value,
            reading.pressure_torr,
            reading.signal_voltage,
            reading.adc_voltage,
            reading.adc_raw,
            latency_ms,
        )
        print(
            f"[{timestamp}] device={record.device} channel={record.channel} "
            f"quality={reading.quality.value} "
            f"pressure={reading.pressure_torr} Torr "
            f"signal_voltage={reading.signal_voltage} V"
        )

        if stop_after_write:
            logging.error(
                "Zbyt wiele błędów z rzędu (%s), zatrzymuję kolektor", failures.count
            )
            return

        sleep_time = cfg.interval_seconds - (time.monotonic() - loop_start)
        if sleep_time > 0:
            time.sleep(sleep_time)


def main() -> None:
    args = parse_args()
    try:
        cfg = Ads1115Config.from_file(args.config)
    except ConfigValidationError as error:
        print(f"[KRYTYCZNY BŁĄD KONFIGURACJI] {error}")
        raise SystemExit(1) from None

    setup_logging(cfg)
    adc: ADS1115 | None = None
    writer: CsvWriter | None = None
    influx_writer: InfluxWriter | None = None
    try:
        adc = ADS1115(
            bus_id=cfg.i2c_bus,
            address=cfg.i2c_address,
            channel=cfg.ads_channel,
            pga_gain=cfg.pga_gain,
            data_rate=cfg.data_rate,
        )
        writer = CsvWriter(cfg.csv_filepath, mode=cfg.csv_mode)
        influx_writer = build_influx_writer(cfg)
        logging.info(
            "Kolektor ADS1115 uruchomiony: device=%s channel=%s i2c=%s "
            "address=0x%02X ads_channel=A%s ratio=%.6f emission=%smA",
            cfg.device_name,
            cfg.channel,
            cfg.i2c_bus,
            cfg.i2c_address,
            cfg.ads_channel,
            cfg.divider_ratio,
            cfg.emission_current_ma,
        )

        run_collection_loop(adc, cfg, writer, influx_writer)

    except KeyboardInterrupt:
        logging.info("Przerwano przez użytkownika")
    finally:
        if adc is not None:
            adc.close()
        if writer is not None:
            writer.close()
        if influx_writer is not None:
            influx_writer.close()


if __name__ == "__main__":
    main()

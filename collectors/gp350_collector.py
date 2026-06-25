# ruff: noqa: E402, I001
import argparse
import datetime
import logging
import os
import sys
import time
from collections import Counter
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import serial
from collectors.config import AppConfig, ConfigValidationError
from collectors.csv_writer import CsvWriter, MeasurementRecord
from collectors.influx_writer import InfluxConfig, InfluxWriter
from collectors.serial_client import SerialClient
from simulators import GP350Parser, ParsedQuality

MAX_CONSECUTIVE_ERRORS = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kolektor danych GP350")
    parser.add_argument(
        "--config",
        default="config/config.ini",
        help="Ścieżka do pliku konfiguracyjnego",
    )
    parser.add_argument("--port", help="Ścieżka do portu serial override config")
    return parser.parse_args()


def setup_logging(cfg: AppConfig) -> None:
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


def open_client(cfg: AppConfig) -> SerialClient:
    parity_map = {
        "none": serial.PARITY_NONE,
        "even": serial.PARITY_EVEN,
        "odd": serial.PARITY_ODD,
    }
    return SerialClient(
        port=cfg.serial_port,
        baudrate=cfg.baudrate,
        bytesize=cfg.bytesize,
        parity=parity_map[cfg.parity],
        stopbits=cfg.stopbits,
        line_terminator=cfg.line_terminator,
        timeout=cfg.timeout,
        write_timeout=cfg.write_timeout,
    )


def build_serial_command(cfg: AppConfig) -> str:
    if cfg.rs485_address is None:
        return cfg.command

    return f"#{cfg.rs485_address:02d}{cfg.command}"


def build_influx_config(cfg: AppConfig) -> InfluxConfig:
    return InfluxConfig(
        url=cfg.influx_url,
        org=cfg.influx_org,
        bucket=cfg.influx_bucket,
        token=cfg.resolved_influx_token,
        measurement=cfg.influx_measurement,
        timeout=cfg.influx_timeout,
        retries=cfg.influx_retries,
        module_type=cfg.module_type,
        command=build_serial_command(cfg),
    )


def open_influx_writer(cfg: AppConfig) -> InfluxWriter | None:
    if not cfg.influx_enabled:
        return None

    return InfluxWriter(build_influx_config(cfg))


def influx_settings_changed(old_cfg: AppConfig, new_cfg: AppConfig) -> bool:
    return (
        old_cfg.influx_enabled != new_cfg.influx_enabled
        or old_cfg.influx_url != new_cfg.influx_url
        or old_cfg.influx_org != new_cfg.influx_org
        or old_cfg.influx_bucket != new_cfg.influx_bucket
        or old_cfg.resolved_influx_token != new_cfg.resolved_influx_token
        or old_cfg.influx_measurement != new_cfg.influx_measurement
        or old_cfg.influx_timeout != new_cfg.influx_timeout
        or old_cfg.influx_retries != new_cfg.influx_retries
        or old_cfg.module_type != new_cfg.module_type
        or old_cfg.command != new_cfg.command
        or old_cfg.rs485_address != new_cfg.rs485_address
    )


def load_config_or_exit(config_path: str, port_override: str | None) -> AppConfig:
    try:
        return AppConfig.from_file(config_path, serial_port_override=port_override)
    except ConfigValidationError as error:
        print(f"[KRYTYCZNY BŁĄD KONFIGURACJI] {error}")
        raise SystemExit(1) from None


def log_summary(counters: Counter[str]) -> None:
    logging.info(
        "Podsumowanie: good=%s timeout=%s bad_format=%s error=%s "
        "exceptions=%s influx_errors=%s",
        counters[ParsedQuality.GOOD.value],
        counters[ParsedQuality.TIMEOUT.value],
        counters[ParsedQuality.BAD_FORMAT.value],
        counters[ParsedQuality.ERROR.value],
        counters["exceptions"],
        counters["influx_errors"],
    )


def main() -> None:
    args = parse_args()
    cfg = load_config_or_exit(args.config, args.port)
    setup_logging(cfg)

    last_config_modified = os.path.getmtime(cfg.path) if os.path.exists(cfg.path) else 0
    counters: Counter[str] = Counter()
    consecutive_errors = 0
    client: SerialClient | None = None
    writer: CsvWriter | None = None
    influx_writer: InfluxWriter | None = None

    try:
        client = open_client(cfg)
        writer = CsvWriter(cfg.csv_filepath, mode=cfg.csv_mode)
        influx_writer = open_influx_writer(cfg)
    except serial.SerialException as error:
        logging.critical("Błąd otwarcia portu %s: %s", cfg.serial_port, error)
        raise SystemExit(1) from None

    logging.info(
        "Kolektor uruchomiony: module_type=%s port=%s baudrate=%s bytesize=%s "
        "parity=%s stopbits=%s line_terminator=%r rs485_address=%s command=%s "
        "interval=%ss csv=%s csv_mode=%s influx_enabled=%s influx_measurement=%s",
        cfg.module_type,
        cfg.serial_port,
        cfg.baudrate,
        cfg.bytesize,
        cfg.parity,
        cfg.stopbits,
        cfg.line_terminator,
        cfg.rs485_address,
        cfg.command,
        cfg.interval_seconds,
        cfg.csv_filepath,
        cfg.csv_mode,
        cfg.influx_enabled,
        cfg.influx_measurement,
    )
    print("Kolektor uruchomiony. Naciśnij Ctrl+C, aby zatrzymać...")

    try:
        while True:
            loop_start_time = time.monotonic()

            changed, last_config_modified = cfg.has_changed(last_config_modified)
            if changed:
                try:
                    new_cfg = AppConfig.from_file(
                        cfg.path,
                        serial_port_override=args.port,
                    )
                    setup_logging(new_cfg)
                    logging.info("Konfiguracja przeładowana")

                    if (
                        new_cfg.csv_filepath != cfg.csv_filepath
                        or new_cfg.csv_mode != cfg.csv_mode
                    ) and writer is not None:
                        writer.close()
                        writer = CsvWriter(new_cfg.csv_filepath, mode=new_cfg.csv_mode)

                    if influx_settings_changed(cfg, new_cfg):
                        if influx_writer is not None:
                            influx_writer.close()
                        influx_writer = open_influx_writer(new_cfg)

                    if (
                        new_cfg.serial_port != cfg.serial_port
                        or new_cfg.baudrate != cfg.baudrate
                        or new_cfg.bytesize != cfg.bytesize
                        or new_cfg.parity != cfg.parity
                        or new_cfg.stopbits != cfg.stopbits
                        or new_cfg.line_terminator != cfg.line_terminator
                        or new_cfg.rs485_address != cfg.rs485_address
                        or new_cfg.timeout != cfg.timeout
                        or new_cfg.write_timeout != cfg.write_timeout
                    ):
                        if client is not None:
                            client.close()
                        client = open_client(new_cfg)

                    cfg = new_cfg
                except (ConfigValidationError, serial.SerialException) as error:
                    logging.error(
                        "Nowa konfiguracja niepoprawna, zostawiam starą: %s",
                        error,
                    )

            try:
                if client is None or writer is None:
                    raise RuntimeError("collector resources are not open")

                send_time = time.monotonic()
                raw_response = client.send_command(build_serial_command(cfg))
                receive_time = time.monotonic()

                latency_ms = (receive_time - send_time) * 1000.0
                reading = GP350Parser.parse(raw_response)
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
                        counters["influx_errors"] += 1
                        logging.error("Błąd zapisu InfluxDB: %s", error)
                        if cfg.influx_fail_on_error:
                            raise

                counters[reading.quality.value] += 1
                consecutive_errors = 0

                if reading.quality is not ParsedQuality.GOOD:
                    logging.warning(
                        "Pomiar quality=%s raw_response=%r",
                        reading.quality.value,
                        raw_response,
                    )
                elif cfg.debug:
                    logging.debug("Pomiar OK raw_response=%r", raw_response)

                print(
                    f"[{timestamp}] quality={reading.quality.value} "
                    f"pressure={reading.pressure_torr} {reading.unit or ''} "
                    f"latency={latency_ms:.2f} ms"
                )
            except Exception as error:
                counters["exceptions"] += 1
                consecutive_errors += 1
                logging.exception(
                    "Błąd iteracji (%s/%s), kontynuuję: %s",
                    consecutive_errors,
                    MAX_CONSECUTIVE_ERRORS,
                    error,
                )

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logging.error("Zbyt wiele błędów z rzędu, zatrzymuję kolektor")
                    break

            elapsed = time.monotonic() - loop_start_time
            sleep_time = cfg.interval_seconds - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        logging.info("Przerwano przez użytkownika")
    finally:
        logging.info("Zamykanie kolektora")
        if client is not None:
            client.close()
            logging.info("Port serial zamknięty")
        if writer is not None:
            writer.close()
            logging.info("Plik CSV zamknięty")
        if influx_writer is not None:
            influx_writer.close()
            logging.info("InfluxDB writer zamknięty")
        log_summary(counters)


if __name__ == "__main__":
    main()

# ruff: noqa: E402, I001
import argparse
import datetime
import logging
import os
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import serial
from collectors.config import AppConfig, ConfigValidationError
from collectors.csv_writer import CsvWriter, MeasurementRecord
from collectors.device_discovery import (
    DetectedDevice,
    DeviceDiscoveryError,
    discover_serial_devices,
    select_device,
)
from collectors.influx_writer import InfluxConfig, InfluxWriter
from collectors.serial_client import SerialClient
from collectors.vgc402 import (
    VGC402_COMMANDS,
    VGC402_DEVICE_TYPE,
)
from devices import get_device_profile
from simulators import ParsedQuality

MAX_CONSECUTIVE_ERRORS = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kolektor danych vacuum instruments")
    parser.add_argument(
        "--config",
        default="config/config.ini",
        help="Ścieżka do pliku konfiguracyjnego",
    )
    parser.add_argument("--port", help="Ścieżka do portu serial override config")
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Wykryj obsługiwane urządzenia na portach serial i zakończ",
    )
    parser.add_argument(
        "--auto-device-index",
        type=int,
        help="Indeks urządzenia wybranego przy serial_port=auto",
    )
    parser.add_argument(
        "--scan-rs485",
        action="store_true",
        help="Podczas autodetekcji skanuj adresy #00-#31",
    )
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
    command = (
        cfg.command.upper()
        if cfg.device_type == VGC402_DEVICE_TYPE
        else cfg.command
    )
    if cfg.rs485_address is None:
        return command

    return f"#{cfg.rs485_address:02d}{command}"


def discovery_device_types(cfg: AppConfig) -> tuple[str, ...]:
    if cfg.device_type == "auto":
        return ("gp350", VGC402_DEVICE_TYPE)

    return (cfg.device_type,)


def discovery_module_types(cfg: AppConfig) -> tuple[str, ...]:
    if cfg.device_type == VGC402_DEVICE_TYPE:
        return ("serial",) if cfg.module_type == "auto" else (cfg.module_type,)

    if cfg.module_type == "auto":
        if cfg.device_type == "auto":
            return ("digital", "rs232", "serial")
        return ("digital", "rs232")

    return (cfg.module_type,)


def discovery_rs485_addresses(cfg: AppConfig, *, force_scan: bool) -> tuple[int, ...]:
    if cfg.rs485_address is not None:
        return (cfg.rs485_address,)

    if cfg.auto_scan_rs485 or force_scan:
        return cfg.auto_rs485_addresses

    return ()


def discover_devices_for_config(
    cfg: AppConfig,
    *,
    force_rs485_scan: bool = False,
) -> list[DetectedDevice]:
    port_names = None if cfg.serial_port == "auto" else (cfg.serial_port,)
    return discover_serial_devices(
        port_names=port_names,
        include_device_types=discovery_device_types(cfg),
        include_module_types=discovery_module_types(cfg),
        rs485_addresses=discovery_rs485_addresses(cfg, force_scan=force_rs485_scan),
        timeout=cfg.auto_probe_timeout,
    )


def config_with_detected_device(
    cfg: AppConfig,
    detected: DetectedDevice,
) -> AppConfig:
    device_name = cfg.device_name
    channel = cfg.channel
    command = detected.command
    if detected.device_type == VGC402_DEVICE_TYPE:
        requested_command = cfg.command.upper()
        if requested_command in VGC402_COMMANDS and requested_command != "PR1":
            command = requested_command
        if cfg.device_name == AppConfig.device_name:
            device_name = "VGC402_1"
        if cfg.channel == AppConfig.channel:
            if command == "PRX":
                channel = "ALL"
            else:
                channel = "CH2" if command == "PR2" else "CH1"

    return replace(
        cfg,
        device_type=detected.device_type,
        module_type=detected.module_type,
        serial_port=detected.port,
        baudrate=detected.baudrate,
        bytesize=detected.bytesize,
        parity=detected.parity,
        stopbits=detected.stopbits,
        line_terminator=detected.line_terminator,
        rs485_address=detected.rs485_address,
        command=command,
        device_name=device_name,
        channel=channel,
    )


def resolve_detected_config(
    cfg: AppConfig,
    *,
    device_index_override: int | None = None,
    force_rs485_scan: bool = False,
) -> AppConfig:
    if not cfg.needs_device_detection:
        return cfg

    devices = discover_devices_for_config(cfg, force_rs485_scan=force_rs485_scan)
    selected_index = (
        cfg.auto_device_index
        if device_index_override is None
        else device_index_override
    )
    selected = select_device(devices, selected_index)
    return config_with_detected_device(cfg, selected)


def print_discovered_devices(devices: list[DetectedDevice]) -> None:
    if not devices:
        print("Nie wykryto obsługiwanego urządzenia.")
        return

    for index, device in enumerate(devices):
        address = (
            "" if device.rs485_address is None else f" address={device.rs485_address}"
        )
        print(
            f"[{index}] type={device.device_type} module={device.module_type} "
            f"port={device.port}{address} baudrate={device.baudrate} "
            f"confidence={device.confidence:.2f} raw={device.raw_response!r}"
        )


def build_influx_config(cfg: AppConfig) -> InfluxConfig:
    return InfluxConfig(
        url=cfg.influx_url,
        org=cfg.influx_org,
        bucket=cfg.influx_bucket,
        token=cfg.resolved_influx_token,
        measurement=cfg.influx_measurement,
        timeout=cfg.influx_timeout,
        retries=cfg.influx_retries,
        device_type=cfg.device_type,
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
        or old_cfg.device_type != new_cfg.device_type
        or old_cfg.module_type != new_cfg.module_type
        or old_cfg.command != new_cfg.command
        or old_cfg.rs485_address != new_cfg.rs485_address
    )


def read_device_response(client: SerialClient, cfg: AppConfig) -> str:
    command = build_serial_command(cfg)
    return get_device_profile(cfg.device_type).read_response(client, command)


def resolve_runtime_config(cfg: AppConfig, client: SerialClient) -> AppConfig:
    return get_device_profile(cfg.device_type).resolve_runtime_config(cfg, client)


def parse_device_response(raw_response: str, cfg: AppConfig):
    return get_device_profile(cfg.device_type).parse_response(raw_response, cfg)


def parse_device_readings(raw_response: str, cfg: AppConfig):
    return get_device_profile(cfg.device_type).parse_readings(raw_response, cfg)


def channels_for_readings(cfg: AppConfig, reading_count: int) -> list[str]:
    return get_device_profile(cfg.device_type).channels_for_readings(
        cfg,
        reading_count,
    )


def build_measurement_records(
    *,
    raw_response: str,
    cfg: AppConfig,
    timestamp: str,
    latency_ms: float,
) -> list[MeasurementRecord]:
    readings = parse_device_readings(raw_response, cfg)
    channels = channels_for_readings(cfg, len(readings))
    return [
        MeasurementRecord(
            timestamp=timestamp,
            device=cfg.device_name,
            channel=channel,
            latency_ms=latency_ms,
            reading=reading,
        )
        for channel, reading in zip(channels, readings, strict=True)
    ]


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

    if args.discover:
        devices = discover_devices_for_config(
            cfg,
            force_rs485_scan=args.scan_rs485,
        )
        print_discovered_devices(devices)
        return

    try:
        cfg = resolve_detected_config(
            cfg,
            device_index_override=args.auto_device_index,
            force_rs485_scan=args.scan_rs485,
        )
    except DeviceDiscoveryError as error:
        logging.critical("Autodetekcja nieudana: %s", error)
        raise SystemExit(1) from None

    last_config_modified = os.path.getmtime(cfg.path) if os.path.exists(cfg.path) else 0
    counters: Counter[str] = Counter()
    consecutive_errors = 0
    client: SerialClient | None = None
    writer: CsvWriter | None = None
    influx_writer: InfluxWriter | None = None

    try:
        client = open_client(cfg)
        cfg = resolve_runtime_config(cfg, client)
        writer = CsvWriter(cfg.csv_filepath, mode=cfg.csv_mode)
        influx_writer = open_influx_writer(cfg)
    except (RuntimeError, ValueError, serial.SerialException) as error:
        logging.critical("Błąd otwarcia portu %s: %s", cfg.serial_port, error)
        raise SystemExit(1) from None

    logging.info(
        "Kolektor uruchomiony: device_type=%s module_type=%s port=%s "
        "baudrate=%s bytesize=%s "
        "parity=%s stopbits=%s line_terminator=%r rs485_address=%s command=%s "
        "pressure_unit=%s interval=%ss csv=%s csv_mode=%s influx_enabled=%s "
        "influx_measurement=%s",
        cfg.device_type,
        cfg.module_type,
        cfg.serial_port,
        cfg.baudrate,
        cfg.bytesize,
        cfg.parity,
        cfg.stopbits,
        cfg.line_terminator,
        cfg.rs485_address,
        cfg.command,
        cfg.pressure_unit,
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
                    new_cfg = resolve_detected_config(
                        new_cfg,
                        device_index_override=args.auto_device_index,
                        force_rs485_scan=args.scan_rs485,
                    )
                    setup_logging(new_cfg)
                    logging.info("Konfiguracja przeładowana")

                    serial_settings_changed = (
                        new_cfg.serial_port != cfg.serial_port
                        or new_cfg.baudrate != cfg.baudrate
                        or new_cfg.bytesize != cfg.bytesize
                        or new_cfg.parity != cfg.parity
                        or new_cfg.stopbits != cfg.stopbits
                        or new_cfg.line_terminator != cfg.line_terminator
                        or new_cfg.rs485_address != cfg.rs485_address
                        or new_cfg.timeout != cfg.timeout
                        or new_cfg.write_timeout != cfg.write_timeout
                        or new_cfg.device_type != cfg.device_type
                    )

                    if serial_settings_changed:
                        if client is not None:
                            client.close()
                        client = open_client(new_cfg)

                    if client is None:
                        raise RuntimeError("collector serial client is not open")

                    new_cfg = resolve_runtime_config(new_cfg, client)

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

                    cfg = new_cfg
                except (
                    ConfigValidationError,
                    DeviceDiscoveryError,
                    RuntimeError,
                    ValueError,
                    serial.SerialException,
                ) as error:
                    logging.error(
                        "Nowa konfiguracja niepoprawna, zostawiam starą: %s",
                        error,
                    )

            try:
                if client is None or writer is None:
                    raise RuntimeError("collector resources are not open")

                send_time = time.monotonic()
                raw_response = read_device_response(client, cfg)
                receive_time = time.monotonic()

                latency_ms = (receive_time - send_time) * 1000.0
                timestamp = datetime.datetime.now(datetime.UTC).isoformat()
                records = build_measurement_records(
                    raw_response=raw_response,
                    cfg=cfg,
                    timestamp=timestamp,
                    latency_ms=latency_ms,
                )

                for record in records:
                    writer.write(record)
                    if influx_writer is not None:
                        try:
                            influx_writer.write(record)
                        except Exception as error:
                            counters["influx_errors"] += 1
                            logging.error("Błąd zapisu InfluxDB: %s", error)
                            if cfg.influx_fail_on_error:
                                raise

                    reading = record.reading
                    counters[reading.quality.value] += 1

                    if reading.quality is not ParsedQuality.GOOD:
                        logging.warning(
                            "Pomiar channel=%s quality=%s raw_response=%r",
                            record.channel,
                            reading.quality.value,
                            raw_response,
                        )
                    elif cfg.debug:
                        logging.debug(
                            "Pomiar OK channel=%s raw_response=%r",
                            record.channel,
                            raw_response,
                        )

                    print(
                        f"[{timestamp}] device={record.device} "
                        f"channel={record.channel} "
                        f"quality={reading.quality.value} "
                        f"pressure={reading.pressure_torr} {reading.unit or ''} "
                        f"latency={latency_ms:.2f} ms"
                    )

                consecutive_errors = 0
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

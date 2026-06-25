import configparser
import os
from dataclasses import dataclass
from pathlib import Path

MODULE_DEFAULTS = {
    "rs232": {
        "baudrate": 300,
        "bytesize": 7,
        "parity": "none",
        "stopbits": 2.0,
        "line_terminator": "\r\n",
        "command": "DS IG",
    },
    "digital": {
        "baudrate": 9600,
        "bytesize": 8,
        "parity": "none",
        "stopbits": 1.0,
        "line_terminator": "\r",
        "command": "RD",
    },
}

TERMINATOR_ALIASES = {
    "crlf": "\r\n",
    "\\r\\n": "\r\n",
    "cr": "\r",
    "\\r": "\r",
    "lf": "\n",
    "\\n": "\n",
}


class ConfigValidationError(Exception):
    """Raised when collector configuration is invalid."""


@dataclass(frozen=True)
class AppConfig:
    debug: bool = False
    log_level: str = "info"
    module_type: str = "digital"
    serial_port: str = ""
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = "none"
    stopbits: float = 1.0
    line_terminator: str = "\r"
    rs485_address: int | None = None
    timeout: float = 1.0
    write_timeout: float = 1.0
    command: str = "RD"
    auto_device_index: int = 0
    auto_probe_timeout: float = 0.35
    auto_scan_rs485: bool = False
    auto_rs485_addresses: tuple[int, ...] = tuple(range(32))
    interval_seconds: float = 1.0
    device_name: str = "GP350_1"
    channel: str = "IG1"
    csv_filepath: str = "data/gp350_readings.csv"
    csv_mode: str = "overwrite"
    log_file: str = "logs/collector.log"
    influx_enabled: bool = False
    influx_url: str = "http://localhost:8086"
    influx_org: str = ""
    influx_bucket: str = ""
    influx_token: str = ""
    influx_token_env: str = "INFLUXDB_TOKEN"
    influx_measurement: str = "gp350_reading"
    influx_timeout: float = 2.0
    influx_retries: int = 0
    influx_fail_on_error: bool = False
    path: str = "config/config.ini"

    @classmethod
    def from_file(
        cls,
        path: str = "config/config.ini",
        *,
        serial_port_override: str | None = None,
    ) -> "AppConfig":
        config = configparser.ConfigParser()
        defaults = cls(path=path)

        if os.path.exists(path):
            config.read(path)

        try:
            serial_port = config.get(
                "Connection",
                "serial_port",
                fallback=defaults.serial_port,
            ).strip()
            if serial_port.lower() == "auto":
                serial_port = "auto"
            if serial_port_override:
                serial_port = serial_port_override

            module_type = config.get(
                "Connection",
                "module_type",
                fallback=defaults.module_type,
            ).strip().lower()
            if module_type not in {*MODULE_DEFAULTS, "auto"}:
                raise ConfigValidationError(
                    "module_type musi mieć wartość auto, rs232 albo digital"
                )

            module_defaults = MODULE_DEFAULTS[
                "digital" if module_type == "auto" else module_type
            ]
            rs485_address = cls._read_optional_int(
                config,
                "Connection",
                "rs485_address",
            )

            app_config = cls(
                debug=config.getboolean("General", "debug", fallback=defaults.debug),
                log_level=config.get(
                    "General",
                    "log_level",
                    fallback=defaults.log_level,
                ).lower(),
                module_type=module_type,
                serial_port=serial_port,
                baudrate=config.getint(
                    "Connection",
                    "baudrate",
                    fallback=int(module_defaults["baudrate"]),
                ),
                bytesize=config.getint(
                    "Connection",
                    "bytesize",
                    fallback=int(module_defaults["bytesize"]),
                ),
                parity=config.get(
                    "Connection",
                    "parity",
                    fallback=str(module_defaults["parity"]),
                ).lower(),
                stopbits=config.getfloat(
                    "Connection",
                    "stopbits",
                    fallback=float(module_defaults["stopbits"]),
                ),
                line_terminator=cls._read_line_terminator(
                    config,
                    str(module_defaults["line_terminator"]),
                ),
                rs485_address=rs485_address,
                timeout=config.getfloat(
                    "Connection",
                    "timeout",
                    fallback=defaults.timeout,
                ),
                write_timeout=config.getfloat(
                    "Connection",
                    "write_timeout",
                    fallback=defaults.write_timeout,
                ),
                command=config.get(
                    "Collector",
                    "command",
                    fallback=str(module_defaults["command"]),
                ).strip(),
                auto_device_index=config.getint(
                    "Detection",
                    "device_index",
                    fallback=defaults.auto_device_index,
                ),
                auto_probe_timeout=config.getfloat(
                    "Detection",
                    "probe_timeout",
                    fallback=defaults.auto_probe_timeout,
                ),
                auto_scan_rs485=config.getboolean(
                    "Detection",
                    "scan_rs485",
                    fallback=defaults.auto_scan_rs485,
                ),
                auto_rs485_addresses=cls._read_address_list(
                    config,
                    fallback=defaults.auto_rs485_addresses,
                ),
                interval_seconds=config.getfloat(
                    "Collector",
                    "interval_seconds",
                    fallback=defaults.interval_seconds,
                ),
                device_name=config.get(
                    "Device",
                    "device_name",
                    fallback=defaults.device_name,
                ).strip(),
                channel=config.get(
                    "Device",
                    "channel",
                    fallback=defaults.channel,
                ).strip(),
                csv_filepath=config.get(
                    "File",
                    "csv_filepath",
                    fallback=defaults.csv_filepath,
                ),
                csv_mode=config.get(
                    "File",
                    "csv_mode",
                    fallback=defaults.csv_mode,
                ).lower(),
                log_file=config.get(
                    "File",
                    "log_file",
                    fallback=defaults.log_file,
                ),
                influx_enabled=config.getboolean(
                    "InfluxDB",
                    "enabled",
                    fallback=defaults.influx_enabled,
                ),
                influx_url=config.get(
                    "InfluxDB",
                    "url",
                    fallback=defaults.influx_url,
                ).rstrip("/"),
                influx_org=config.get(
                    "InfluxDB",
                    "org",
                    fallback=defaults.influx_org,
                ).strip(),
                influx_bucket=config.get(
                    "InfluxDB",
                    "bucket",
                    fallback=defaults.influx_bucket,
                ).strip(),
                influx_token=config.get(
                    "InfluxDB",
                    "token",
                    fallback=defaults.influx_token,
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
                    "InfluxDB",
                    "timeout",
                    fallback=defaults.influx_timeout,
                ),
                influx_retries=config.getint(
                    "InfluxDB",
                    "retries",
                    fallback=defaults.influx_retries,
                ),
                influx_fail_on_error=config.getboolean(
                    "InfluxDB",
                    "fail_on_error",
                    fallback=defaults.influx_fail_on_error,
                ),
                path=path,
            )
        except ValueError as error:
            raise ConfigValidationError(
                f"Błąd typu danych w pliku konfiguracyjnym: {error}"
            ) from error

        app_config.validate()
        return app_config

    @staticmethod
    def _read_optional_int(
        config: configparser.ConfigParser,
        section: str,
        option: str,
    ) -> int | None:
        if not config.has_option(section, option):
            return None

        raw_value = config.get(section, option).strip()
        if raw_value == "":
            return None

        return int(raw_value)

    @staticmethod
    def _read_line_terminator(
        config: configparser.ConfigParser,
        default: str,
    ) -> str:
        raw_value = config.get(
            "Connection",
            "line_terminator",
            fallback=default,
        )

        if raw_value in {"\r\n", "\r", "\n"}:
            return raw_value

        normalized = raw_value.strip().lower()
        if normalized not in TERMINATOR_ALIASES:
            raise ConfigValidationError(
                "line_terminator musi mieć wartość crlf, cr albo lf"
            )

        return TERMINATOR_ALIASES[normalized]

    @staticmethod
    def _read_address_list(
        config: configparser.ConfigParser,
        *,
        fallback: tuple[int, ...],
    ) -> tuple[int, ...]:
        raw_value = config.get(
            "Detection",
            "rs485_addresses",
            fallback="",
        ).strip()

        if not raw_value:
            return fallback

        addresses: set[int] = set()
        for part in raw_value.replace(" ", "").split(","):
            if not part:
                continue

            if "-" in part:
                start_text, end_text = part.split("-", maxsplit=1)
                start = int(start_text)
                end = int(end_text)
                if start > end:
                    raise ConfigValidationError(
                        "rs485_addresses ma zakres od większej do mniejszej wartości"
                    )
                addresses.update(range(start, end + 1))
            else:
                addresses.add(int(part))

        return tuple(sorted(addresses))

    def validate(self) -> None:
        if not self.serial_port:
            raise ConfigValidationError(
                "Nie podano serial_port. "
                "Ustaw go w config/config.ini, wpisz auto albo użyj --port."
            )

        if self.module_type not in {*MODULE_DEFAULTS, "auto"}:
            raise ConfigValidationError(
                "module_type musi mieć wartość auto, rs232 albo digital"
            )

        valid_baudrates = {75, 150, 300, 600, 1200, 2400, 4800, 9600, 19200}
        if self.baudrate not in valid_baudrates:
            raise ConfigValidationError(
                f"Nieprawidłowy baudrate: {self.baudrate}. "
                f"Dozwolone wartości: {sorted(valid_baudrates)}"
            )

        if self.bytesize not in {7, 8}:
            raise ConfigValidationError("bytesize musi mieć wartość 7 albo 8")

        if self.parity not in {"none", "even", "odd"}:
            raise ConfigValidationError("parity musi mieć wartość none, even albo odd")

        if self.stopbits not in {1.0, 2.0}:
            raise ConfigValidationError("stopbits musi mieć wartość 1 albo 2")

        if self.line_terminator not in {"\r\n", "\r", "\n"}:
            raise ConfigValidationError(
                "line_terminator musi mieć wartość crlf, cr albo lf"
            )

        if self.rs485_address is not None and not 0 <= self.rs485_address <= 31:
            raise ConfigValidationError(
                "rs485_address musi być puste albo w zakresie 0-31"
            )

        if self.rs485_address is not None and self.module_type not in {
            "auto",
            "digital",
        }:
            raise ConfigValidationError(
                "rs485_address działa tylko dla module_type=digital"
            )

        if self.auto_device_index < 0:
            raise ConfigValidationError("Detection.device_index nie może być ujemny")

        if self.auto_probe_timeout <= 0:
            raise ConfigValidationError("Detection.probe_timeout musi być dodatni")

        if any(address < 0 or address > 31 for address in self.auto_rs485_addresses):
            raise ConfigValidationError(
                "Detection.rs485_addresses musi zawierać adresy 0-31"
            )

        if self.timeout <= 0:
            raise ConfigValidationError("timeout musi być dodatni")

        if self.write_timeout <= 0:
            raise ConfigValidationError("write_timeout musi być dodatni")

        if self.interval_seconds <= 0:
            raise ConfigValidationError("interval_seconds musi być dodatni")

        if not self.command:
            raise ConfigValidationError("command nie może być pusty")

        if not self.device_name:
            raise ConfigValidationError("device_name nie może być pusty")

        if not self.channel:
            raise ConfigValidationError("channel nie może być pusty")

        if self.log_level not in {"debug", "info", "warning", "error"}:
            raise ConfigValidationError(
                f"Nieznany log_level: '{self.log_level}'. "
                "Wybierz z: debug, info, warning, error"
            )

        if self.csv_mode not in {"overwrite", "append"}:
            raise ConfigValidationError(
                f"Nieznany csv_mode: '{self.csv_mode}'. Wybierz overwrite albo append"
            )

        if self.influx_enabled:
            if not (
                self.influx_url.startswith("http://")
                or self.influx_url.startswith("https://")
            ):
                raise ConfigValidationError(
                    "influx url musi zaczynać się od http:// albo https://"
                )

            if not self.influx_org:
                raise ConfigValidationError("influx org nie może być pusty")

            if not self.influx_bucket:
                raise ConfigValidationError("influx bucket nie może być pusty")

            if not self.resolved_influx_token:
                raise ConfigValidationError(
                    "influx token nie może być pusty; ustaw token albo token_env"
                )

            if not self.influx_measurement:
                raise ConfigValidationError("influx measurement nie może być pusty")

            if self.influx_timeout <= 0:
                raise ConfigValidationError("influx timeout musi być dodatni")

            if self.influx_retries < 0:
                raise ConfigValidationError("influx retries nie może być ujemne")

        try:
            Path(self.csv_filepath)
            Path(self.log_file)
        except Exception as error:
            raise ConfigValidationError("Ścieżka pliku jest niepoprawna") from error

    @property
    def resolved_influx_token(self) -> str:
        if self.influx_token:
            return self.influx_token

        if not self.influx_token_env:
            return ""

        return os.environ.get(self.influx_token_env, "")

    @property
    def needs_device_detection(self) -> bool:
        return self.serial_port == "auto" or self.module_type == "auto"

    def has_changed(self, last_modified_time: float) -> tuple[bool, float]:
        try:
            current_modified = os.path.getmtime(self.path)
        except FileNotFoundError:
            return False, last_modified_time

        if current_modified > last_modified_time:
            return True, current_modified

        return False, last_modified_time

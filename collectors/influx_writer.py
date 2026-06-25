import datetime
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from collectors.csv_writer import MeasurementRecord


class InfluxWriteError(Exception):
    """Raised when writing to InfluxDB fails."""


@dataclass(frozen=True)
class InfluxConfig:
    url: str
    org: str
    bucket: str
    token: str
    measurement: str
    timeout: float
    retries: int
    module_type: str
    command: str


def _escape_measurement(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(" ", "\\ ")


def _escape_key(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace("=", "\\=")
        .replace(" ", "\\ ")
    )


def _escape_string_field(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _format_tag(key: str, value: str) -> str:
    return f"{_escape_key(key)}={_escape_key(value)}"


def _format_string_field(key: str, value: str) -> str:
    return f'{_escape_key(key)}="{_escape_string_field(value)}"'


def _timestamp_to_ns(timestamp: str) -> int:
    parsed = datetime.datetime.fromisoformat(timestamp)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)

    return int(parsed.timestamp() * 1_000_000_000)


class InfluxWriter:
    def __init__(self, config: InfluxConfig):
        self.config = config
        query = urllib.parse.urlencode(
            {
                "org": config.org,
                "bucket": config.bucket,
                "precision": "ns",
            }
        )
        self.write_url = f"{config.url.rstrip('/')}/api/v2/write?{query}"

    def write(self, record: MeasurementRecord) -> None:
        line = self.to_line_protocol(record)
        payload = line.encode("utf-8")
        last_error: Exception | None = None

        for attempt in range(self.config.retries + 1):
            try:
                self._post(payload)
                return
            except Exception as error:
                last_error = error
                if attempt < self.config.retries:
                    time.sleep(min(0.25 * (attempt + 1), 2.0))

        raise InfluxWriteError(f"InfluxDB write failed: {last_error}") from last_error

    def to_line_protocol(self, record: MeasurementRecord) -> str:
        reading = record.reading
        tags = [
            _format_tag("device", record.device),
            _format_tag("channel", record.channel),
            _format_tag("quality", reading.quality.value),
            _format_tag("module_type", self.config.module_type),
            _format_tag("command", self.config.command),
        ]

        fields = [
            f"latency_ms={record.latency_ms:.3f}",
            f'raw_response="{_escape_string_field(reading.raw_response)}"',
            f"is_good={str(reading.quality.value == 'good').lower()}",
        ]

        if reading.pressure_torr is not None:
            fields.insert(0, f"pressure_torr={reading.pressure_torr:.12g}")

        if reading.unit:
            fields.append(_format_string_field("unit", reading.unit))

        measurement = _escape_measurement(self.config.measurement)
        timestamp_ns = _timestamp_to_ns(record.timestamp)
        return f"{measurement},{','.join(tags)} {','.join(fields)} {timestamp_ns}"

    def _post(self, payload: bytes) -> None:
        request = urllib.request.Request(
            self.write_url,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Token {self.config.token}",
                "Content-Type": "text/plain; charset=utf-8",
            },
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.config.timeout,
            ) as response:
                status = response.getcode()
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise InfluxWriteError(
                f"InfluxDB HTTP {error.code}: {body or error.reason}"
            ) from error

        if status < 200 or status >= 300:
            raise InfluxWriteError(f"InfluxDB HTTP {status}")

    def close(self) -> None:
        pass

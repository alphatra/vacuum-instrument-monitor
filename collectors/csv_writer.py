import csv
from dataclasses import dataclass
from pathlib import Path

from collectors.measurements import MeasurementReading

CSV_HEADER = [
    "timestamp",
    "device",
    "channel",
    "pressure_torr",
    "unit",
    "quality",
    "gauge_status",
    "raw_response",
    "latency_ms",
]


@dataclass(frozen=True)
class MeasurementRecord:
    timestamp: str
    device: str
    channel: str
    latency_ms: float
    reading: MeasurementReading


class CsvWriter:
    def __init__(
        self,
        filepath: str = "data/gp350_readings.csv",
        mode: str = "overwrite",
    ):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

        if mode not in {"overwrite", "append"}:
            raise ValueError("mode must be overwrite or append")

        file_mode = "w" if mode == "overwrite" else "a"
        is_new_file = (
            mode == "overwrite"
            or not self.filepath.exists()
            or self.filepath.stat().st_size == 0
        )

        self.file = open(self.filepath, file_mode, newline="", encoding="utf-8")
        self.writer = csv.writer(self.file)

        if is_new_file:
            self.writer.writerow(CSV_HEADER)
            self.file.flush()

    def write(self, record: MeasurementRecord) -> None:
        self.writer.writerow(
            [
                record.timestamp,
                record.device,
                record.channel,
                record.reading.pressure_torr,
                record.reading.unit or "",
                record.reading.quality.value,
                record.reading.gauge_status or "",
                record.reading.raw_response,
                f"{record.latency_ms:.3f}",
            ]
        )
        self.file.flush()

    def close(self) -> None:
        if hasattr(self, "file") and not self.file.closed:
            self.file.close()

    def __enter__(self) -> "CsvWriter":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

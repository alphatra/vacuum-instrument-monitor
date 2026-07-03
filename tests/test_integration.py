import csv
import queue
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


def _read_lines(process: subprocess.Popen[str]) -> queue.Queue[str]:
    lines: queue.Queue[str] = queue.Queue()

    def reader() -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            lines.put(line)

    threading.Thread(target=reader, daemon=True).start()
    return lines


def _wait_for_virtual_port(
    lines: queue.Queue[str],
    *,
    marker: str,
    timeout: float = 8.0,
) -> str:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=0.1)
        except queue.Empty:
            continue

        if marker in line:
            return line.split(marker, maxsplit=1)[1].strip()

    raise TimeoutError(f"virtual server did not print marker: {marker}")


def _wait_for_csv_rows(
    csv_path: Path,
    *,
    data_rows: int = 1,
    timeout: float = 12.0,
) -> list[list[str]]:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        if csv_path.exists():
            rows = list(csv.reader(csv_path.open(encoding="utf-8")))
            if len(rows) >= data_rows + 1:
                return rows[1 : data_rows + 1]

        time.sleep(0.1)

    raise TimeoutError("collector did not write expected CSV data rows")


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def test_virtual_gp350_collector_writes_real_csv_row(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    csv_path = tmp_path / "integration.csv"
    log_path = tmp_path / "integration.log"
    config_path = tmp_path / "config.ini"
    config_path.write_text(
        f"""
[General]
log_level = error

[Connection]
module_type = digital
serial_port = /dev/not-used
timeout = 1.0
write_timeout = 1.0

[Collector]
interval_seconds = 0.1

[File]
csv_filepath = {csv_path}
csv_mode = overwrite
log_file = {log_path}
""",
        encoding="utf-8",
    )

    virtual_process = subprocess.Popen(
        [sys.executable, "-u", "virtual_gp350.py"],
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    collector_process: subprocess.Popen[str] | None = None

    try:
        virtual_lines = _read_lines(virtual_process)
        serial_port = _wait_for_virtual_port(
            virtual_lines,
            marker="Virtual GP350 command port created:",
        )

        collector_process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "collectors.gp350_collector",
                "--config",
                str(config_path),
                "--port",
                serial_port,
            ],
            cwd=project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )

        row = _wait_for_csv_rows(csv_path)[0]

        assert row[3]
        assert row[4] == "Torr"
        assert row[5] == "good"
        assert row[6] == ""
        assert "E" in row[7]
    finally:
        if collector_process is not None:
            _stop_process(collector_process)
        _stop_process(virtual_process)


def test_virtual_vgc402_collector_writes_prx_rows_with_auto_unit(
    tmp_path: Path,
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    csv_path = tmp_path / "vgc402.csv"
    log_path = tmp_path / "vgc402.log"
    config_path = tmp_path / "vgc402.ini"
    config_path.write_text(
        f"""
[General]
log_level = error

[Connection]
module_type = serial
serial_port = /dev/not-used
baudrate = 9600
line_terminator = crlf
timeout = 1.0
write_timeout = 1.0

[Collector]
command = PRX
interval_seconds = 0.1

[Device]
device_type = inficon_vgc402
device_name = VGC402_TEST
channel = ALL
pressure_unit = auto

[File]
csv_filepath = {csv_path}
csv_mode = overwrite
log_file = {log_path}
""",
        encoding="utf-8",
    )

    virtual_process = subprocess.Popen(
        [sys.executable, "-u", "virtual_vgc402.py", "--unit", "micron"],
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    collector_process: subprocess.Popen[str] | None = None

    try:
        virtual_lines = _read_lines(virtual_process)
        serial_port = _wait_for_virtual_port(
            virtual_lines,
            marker="Virtual VGC402 command port created:",
        )

        collector_process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-m",
                "collectors.gp350_collector",
                "--config",
                str(config_path),
                "--port",
                serial_port,
            ],
            cwd=project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )

        ch1, ch2 = _wait_for_csv_rows(csv_path, data_rows=2)

        assert ch1[1] == "VGC402_TEST"
        assert ch1[2] == "CH1"
        assert ch1[4] == "Torr"
        assert ch1[5] == "good"
        assert ch1[6] == "ok"
        assert ch1[7] == "0,1.2300E-03,0,4.5600E-03"

        assert ch2[1] == "VGC402_TEST"
        assert ch2[2] == "CH2"
        assert ch2[4] == "Torr"
        assert ch2[5] == "good"
        assert ch2[6] == "ok"
        assert ch2[7] == "0,1.2300E-03,0,4.5600E-03"
    finally:
        if collector_process is not None:
            _stop_process(collector_process)
        _stop_process(virtual_process)

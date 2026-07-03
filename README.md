# Vacuum Instrument Monitor

Python toolkit for collecting serial data from vacuum instruments, storing
readings in CSV or InfluxDB, and preparing live Grafana dashboards.

Supported device profiles:

- Granville-Phillips 350 (`gp350`)
- INFICON VGC402 (`inficon_vgc402`)

The project name is intentionally wider than one controller, so more instruments
can be added later without renaming the repository.

## Setup

```bash
uv sync --dev
```

## Sample Output

```bash
uv run python main.py --samples 5 --interval 0 --command "DS IG"
```

Useful options:

- `--seed` controls repeatable random output.
- `--samples` sets sample count and must be at least `1`.
- `--interval` sets delay between samples and must not be negative.
- `--command` chooses command sent to the simulator.

## Virtual Serial Device

Start the simulator:

```bash
uv run python virtual_gp350.py
```

It prints a pseudo-terminal path, for example `/dev/ttys005`. Use that path
from another terminal:

```bash
uv run python serial_terminal.py /dev/ttys005
```

For old RS-232 Module defaults:

```bash
uv run python serial_terminal.py /dev/cu.usbserial-XXXX --baudrate 300 --bytesize 7 --parity none --stopbits 2 --line-terminator crlf
```

For Digital Interface RS-485 address `1`:

```bash
uv run python serial_terminal.py /dev/cu.usbserial-XXXX --address 1 --line-terminator cr
```

Use `--verbose` with `virtual_gp350.py` to print raw serial bytes while
debugging.

Virtual VGC402:

```bash
uv run python virtual_vgc402.py --unit micron
uv run python -m collectors.gp350_collector \
  --config config/examples/vgc402.ini \
  --port /dev/ttys005
```

## Device Discovery

Scan connected serial adapters for supported controllers:

```bash
uv run python -m collectors.gp350_collector --discover
```

Run collector with automatic port and module detection:

```bash
uv run python -m collectors.gp350_collector
```

When two controllers are connected, run two collector processes with separate
configs or choose detected index:

```bash
uv run python -m collectors.gp350_collector --auto-device-index 0
uv run python -m collectors.gp350_collector --auto-device-index 1
```

## Current Device Commands

INFICON VGC402:

- `PR1` reads channel 1.
- `PR2` reads channel 2.
- `PRX` reads all channels and writes one record per channel.
- `UNI` is used when `pressure_unit = auto` to read the display unit.
- Protocol uses `command -> ACK -> ENQ -> data`, for example `0,1.23E-06`.
- Supported baudrates: `9600`, `19200`, `38400`.
- Supported units: `Torr`, `mbar`, `bar`, `Pa`, `micron`; stored as `Torr`.

GP350:

- `DS IG` returns RS-232 pressure, e.g. `1.20E-07`.
- `DG ON` / `DG OFF` controls degas and returns `OK` or `INVALID`.
  At high pressure `DG ON` can return `OK` while `DGS` still reports off.
- `DGS` returns degas status: `1` or `0`.
- `IG1 ON` / `IG1 OFF` controls filament 1.
- `IG2 ON` / `IG2 OFF` controls filament 2.
- `RD` returns Digital Interface pressure.
- `IGB` returns filament status.
- `F1 1` / `F1 0` and `F2 1` / `F2 0` control digital filaments.
  Responses use GP350 shape, e.g. `11G1 ON`.
- `PC` supports basic modifiers: `S`, `B`, `1-4`, and setpoint programming.

## Development

Run checks:

```bash
uv run pytest
uv run ruff check .
uv run pyrefly check
```

## Documentation

Polish project walkthrough with diagrams:
[docs/dzialanie.md](docs/dzialanie.md)

Collector design plan in Polish:
[docs/kolektor_danych.md](docs/kolektor_danych.md)

Collector configuration scenarios:
[docs/scenariusze_konfiguracji.md](docs/scenariusze_konfiguracji.md)

Real GP350 wiring and DIP switch checklist:
[docs/podlaczenie_gp350.md](docs/podlaczenie_gp350.md)

InfluxDB + Grafana setup:
[docs/influxdb_grafana.md](docs/influxdb_grafana.md)

Automatic serial device discovery:
[docs/autodetekcja_urzadzen.md](docs/autodetekcja_urzadzen.md)

Device profile layer:
[docs/warstwa_urzadzen.md](docs/warstwa_urzadzen.md)

Linux runner, systemd autostart, external InfluxDB/Grafana:
[docs/linux_systemd_runner.md](docs/linux_systemd_runner.md)

Acceptance tests:
[docs/acceptance_tests.md](docs/acceptance_tests.md)

Grafana dashboard:
[grafana/vacuum-dashboard.json](grafana/vacuum-dashboard.json)

Grafana alert rules:
[grafana/alert-rules.md](grafana/alert-rules.md)

Run collector:

```bash
uv run python -m collectors.gp350_collector --port /dev/ttys005
```

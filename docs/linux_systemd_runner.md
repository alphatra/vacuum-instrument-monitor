# Linux runner i autostart kolektora

Cel: urządzenie Linux/Raspberry Pi ma samo startować kolektor po boot, wykrywać
GP350, zapisywać CSV i wysyłać dane do zewnętrznego InfluxDB, który potem czyta
Grafana.

## Architektura

```mermaid
flowchart LR
    GP1["GP350 #1"] --> USB1["USB-RS232"]
    GP2["GP350 #2"] --> USB2["USB-RS232"]
    USB1 --> Linux["Linux / Raspberry Pi"]
    USB2 --> Linux
    Linux --> Runner["run_collector_linux.sh"]
    Runner --> C1["collector@ gp350-1"]
    Runner --> C2["collector@ gp350-2"]
    C1 --> CSV1["local CSV backup"]
    C2 --> CSV2["local CSV backup"]
    C1 --> Influx["external InfluxDB"]
    C2 --> Influx
    Influx --> Grafana["external Grafana"]
```

Grafana nie dostaje danych bezpośrednio z kolektora. Kolektor pisze do
InfluxDB. Grafana czyta InfluxDB.

## Runtime

Najprostszy runtime: CPython 3.11+ przez `uv` albo gotowa binarka PyInstaller.

Dlaczego nie Cython/PyPy:

- pomiar jest wolny względem CPU, bo czeka na RS-232 i HTTP,
- proces działa długo, więc koszt startu Pythona nie ma znaczenia,
- największy zysk daje stabilny daemon i `systemd`, nie kompilowanie kodu.

Najlżejszy wariant na produkcji: zbudować binarkę PyInstaller na Linux/RPi i
odpalać ją przez `systemd`. Wtedy na docelowym systemie nie potrzeba `uv`, `pip`
ani `.venv`.

## Pliki

- `scripts/run_collector_linux.sh` - uruchamia kolektor z absolutną ścieżką do configu.
- `scripts/build_linux_binary.sh` - buduje binarkę PyInstaller na Linux.
- `scripts/run_collector_binary_linux.sh` - odpala gotową binarkę.
- `systemd/vacuum-monitor-collector@.service` - autostart/restart.
- `systemd/vacuum-monitor-collector-binary@.service` - autostart dla binarki.
- `scripts/install_linux_service.sh` - instaluje usługę.
- `scripts/install_linux_binary_service.sh` - buduje binarkę i instaluje usługę.
- `config/examples/gp350-1.ini` - pierwszy GP350.
- `config/examples/gp350-2.ini` - drugi GP350.
- `config/examples/collector.env.example` - token InfluxDB.

## Instalacja na Linux/Raspberry Pi

Założenie: projekt jest w:

```bash
/opt/vacuum-instrument-monitor
```

Instalacja zależności:

```bash
sudo apt-get update
sudo apt-get install -y git curl
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
cd /opt/vacuum-instrument-monitor
uv sync --no-dev
```

Sekrety:

```bash
sudo mkdir -p /etc/vacuum-monitor
sudo cp config/examples/collector.env.example /etc/vacuum-monitor/collector.env
sudo nano /etc/vacuum-monitor/collector.env
```

Wpisz:

```bash
INFLUXDB_TOKEN=twój_token_write_do_influxdb
UV_BIN=/usr/local/bin/uv
PYTHON_VERSION=3.11
```

Configi:

```bash
sudo cp config/examples/gp350-1.ini /etc/vacuum-monitor/gp350-1.ini
sudo cp config/examples/gp350-2.ini /etc/vacuum-monitor/gp350-2.ini
```

W obu plikach zmień:

```ini
[InfluxDB]
url = https://twoj-influx.example.com
org = lab
bucket = vacuum
```

## Test ręczny

Najpierw wykrywanie:

```bash
/opt/vacuum-instrument-monitor/scripts/run_collector_linux.sh \
  /etc/vacuum-monitor/gp350-1.ini \
  --discover
```

Potem start jednego kolektora:

```bash
/opt/vacuum-instrument-monitor/scripts/run_collector_linux.sh \
  /etc/vacuum-monitor/gp350-1.ini
```

## Autostart systemd

Wariant z Python/uv:

Pierwszy GP350:

```bash
sudo /opt/vacuum-instrument-monitor/scripts/install_linux_service.sh gp350-1
```

Drugi GP350:

```bash
sudo /opt/vacuum-instrument-monitor/scripts/install_linux_service.sh gp350-2
```

Status:

```bash
systemctl status vacuum-monitor-collector@gp350-1.service
systemctl status vacuum-monitor-collector@gp350-2.service
```

Logi:

```bash
journalctl -u vacuum-monitor-collector@gp350-1.service -f
journalctl -u vacuum-monitor-collector@gp350-2.service -f
```

Restart:

```bash
sudo systemctl restart vacuum-monitor-collector@gp350-1.service
```

Wyłączenie autostartu:

```bash
sudo systemctl disable --now vacuum-monitor-collector@gp350-1.service
```

## Binarka PyInstaller

Build musi powstać na tym samym typie Linuxa, na którym ma działać:

- Raspberry Pi 64-bit -> buduj na ARM64 Linux/Raspberry Pi.
- Raspberry Pi 32-bit -> buduj na armhf/ARMv7.
- x86_64 serwer -> buduj na x86_64 Linux.

Build onefile:

```bash
cd /opt/vacuum-instrument-monitor
scripts/build_linux_binary.sh --onefile --install /opt/vacuum-instrument-monitor/bin
```

Efekt:

```text
/opt/vacuum-instrument-monitor/bin/vacuum-collector
```

Test:

```bash
/opt/vacuum-instrument-monitor/bin/vacuum-collector \
  --config /etc/vacuum-monitor/gp350-1.ini \
  --discover
```

Autostart z binarki:

```bash
sudo /opt/vacuum-instrument-monitor/scripts/install_linux_binary_service.sh gp350-1
sudo /opt/vacuum-instrument-monitor/scripts/install_linux_binary_service.sh gp350-2
```

Logi:

```bash
journalctl -u vacuum-monitor-collector-binary@gp350-1.service -f
```

Status:

```bash
systemctl status vacuum-monitor-collector-binary@gp350-1.service
```

Restart:

```bash
sudo systemctl restart vacuum-monitor-collector-binary@gp350-1.service
```

`onefile` łatwo kopiować, ale startuje trochę wolniej. `onedir` startuje
szybciej, ale ma katalog z plikami:

```bash
scripts/build_linux_binary.sh --onedir --install /opt/vacuum-instrument-monitor/bin
```

## Automatyczny build na GitHub

Workflow:

```text
.github/workflows/build-linux-binary.yml
```

Co robi:

- `workflow_dispatch` buduje ręcznie po kliknięciu w GitHub Actions,
- tag `v*` buduje automatycznie release artifact,
- x86_64 buduje na `ubuntu-24.04`,
- ARM64 buduje na self-hosted runner z label `meterdevicepi`.

Ważne: binarka ARM64 dla Raspberry Pi musi powstać na ARM64 Linux. Artifact z
`ubuntu-24.04` działa na x86_64, nie na Raspberry Pi.

Jeśli `/tmp` ma `noexec`, `--onefile` może nie ruszyć, bo PyInstaller rozpakowuje
się do katalogu tymczasowego. Wtedy użyj:

```bash
scripts/build_linux_binary.sh --onedir --install /opt/vacuum-instrument-monitor/bin
```

## Zewnętrzna Grafana

Grafana musi mieć datasource do tego samego InfluxDB:

- Influx URL: taki sam jak w `config.ini`
- org: taki sam
- bucket: taki sam
- token: może być read-only

Kolektor potrzebuje tokenu write. Grafana najlepiej token read.

## Typowy flow po boot

```mermaid
sequenceDiagram
    participant Boot as Linux boot
    participant Systemd as systemd
    participant Runner as run_collector_linux.sh
    participant Collector as gp350_collector
    participant GP350 as GP350
    participant Influx as InfluxDB

    Boot->>Systemd: multi-user.target
    Systemd->>Runner: start service instance
    Runner->>Collector: python -m collector albo binarka
    Collector->>GP350: autodetection RD / DS IG
    GP350-->>Collector: pressure response
    loop co interval_seconds
        Collector->>GP350: read pressure
        Collector->>Influx: write line protocol
        Collector->>Collector: append CSV backup
    end
```

## Gdy port USB zmieni nazwę

Nie szkodzi, jeśli config ma:

```ini
[Connection]
module_type = auto
serial_port = auto
```

Po restarcie usługi kolektor znowu wykryje port.

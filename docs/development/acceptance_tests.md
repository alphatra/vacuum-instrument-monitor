# Acceptance tests

Cel: szybko potwierdzić, że kolektor, porty, CSV, InfluxDB i Grafana działają
przed prawdziwym pomiarem.

## 1. INFICON VGC402 na prawdziwym sprzęcie

```bash
uv run python -m collectors.gp350_collector \
  --config config/examples/vgc402.ini \
  --discover
```

Wynik poprawny:

- widać `type=inficon_vgc402`
- widać właściwy `port`
- `baudrate` jest jednym z `9600`, `19200`, `38400`
- `raw` ma kształt `0,1.23E-06`

Krótki test kolektora:

```bash
scripts/acceptance_vgc402.sh config/examples/vgc402.ini
```

Sprawdź:

- CSV ma dwa kanały: `CH1`, `CH2`
- `quality=good` dla obu kanałów, jeśli kontroler nie zgłasza błędu
- `pressure_torr` zgadza się rzędem wielkości z ekranem VGC402
- w logu jest wpis o `UNI`, gdy `pressure_unit = auto`

Jeśli ekran VGC402 pokazuje `Micron`, `mbar` albo `Pa`, CSV nadal ma
`unit=Torr`, bo kolektor konwertuje wynik do `pressure_torr`.

## 2. Symulator VGC402 bez sprzętu

Terminal 1:

```bash
uv run python virtual_vgc402.py --unit micron
```

Skopiuj port z linii:

```text
Virtual VGC402 command port created: /dev/ttysXXX
```

Terminal 2:

```bash
uv run python -m collectors.gp350_collector \
  --config config/examples/vgc402.ini \
  --port /dev/ttysXXX
```

Wynik poprawny:

- kolektor startuje bez błędu
- `pressure_unit = auto` używa `UNI`
- CSV dostaje `CH1` i `CH2`
- `raw_response` wygląda jak `0,1.2300E-03,0,4.5600E-03`

## 3. GP350

Terminal 1:

```bash
uv run python virtual_gp350.py
```

Terminal 2:

```bash
uv run python -m collectors.gp350_collector --port /dev/ttysXXX
```

Wynik poprawny:

- CSV ma `device=GP350_1`
- `channel=IG1`
- `quality=good`
- `raw_response` ma kształt `1.23E-06`

## 4. InfluxDB + Grafana

Config:

```ini
[InfluxDB]
enabled = true
url = https://us-east-1-1.aws.cloud2.influxdata.com
org = your_org
bucket = vacuum
token_env = INFLUXDB_TOKEN
measurement = vacuum_pressure
```

Terminal:

```bash
export INFLUXDB_TOKEN="..."
uv run python -m collectors.gp350_collector --config config/examples/vgc402.ini
```

Grafana:

- importuj `grafana/vacuum-dashboard.json`
- wybierz data source InfluxDB
- ustaw bucket `vacuum`
- sprawdź panel `Pressure by channel`
- dodaj alerty z `grafana/alert-rules.md`

## 5. Raspberry Pi binary

Na Raspberry Pi:

```bash
scripts/build_linux_binary.sh --onefile --install /opt/vacuum-instrument-monitor/bin
scripts/check_linux_binary.sh /etc/vacuum-monitor/vgc402.ini
```

Wynik poprawny:

- `Architecture` pokazuje architekturę Raspberry Pi
- `Binary help: OK`
- `--discover` widzi urządzenie albo jasno pokazuje brak sprzętu

## 6. Systemd

```bash
sudo scripts/install_linux_binary_service.sh vgc402
sudo systemctl status vacuum-monitor-collector-binary@vgc402.service
journalctl -u vacuum-monitor-collector-binary@vgc402.service -f
```

Wynik poprawny:

- service ma status `active`
- journal pokazuje start kolektora
- CSV/logi powstają w `/opt/vacuum-instrument-monitor/data` i `logs`
- po restarcie Raspberry Pi service startuje sam

## 7. Stabilne porty udev

1. Skopiuj `udev/99-vacuum-monitor.rules.example` do
   `udev/99-vacuum-monitor.rules`.
2. Wstaw `idVendor`, `idProduct`, `serial` adapterów.
3. Zainstaluj:

```bash
sudo scripts/install_udev_rules.sh /opt/vacuum-instrument-monitor/udev/99-vacuum-monitor.rules
```

Wynik poprawny:

```bash
ls -l /dev/vacuum-*
```

Pokazuje np.:

```text
/dev/vacuum-gp350-1
/dev/vacuum-vgc402
```

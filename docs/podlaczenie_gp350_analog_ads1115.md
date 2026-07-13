# GP350 analog output z ADS1115

Ten wariant jest dla GP350 bez modułu RS-232/RS-485. Kolektor odczytuje
analogowe wyjście IG przez ADS1115 i zapisuje `pressure_torr`, `adc_voltage`,
`signal_voltage` oraz `adc_raw` do tego samego measurementu InfluxDB.

## 1. Połączenia

```text
GP350 ANALOG signal (tip mini-jack)
    |
   68 kOhm
    |
    +---- ADS1115 A0
    |
   22 kOhm
    |
GP350 ANALOG ground (sleeve mini-jack) ---- ADS1115 GND ---- Raspberry Pi GND

Raspberry Pi 3V3  ---- ADS1115 VDD
Raspberry Pi GPIO2, pin 3  ---- ADS1115 SDA
Raspberry Pi GPIO3, pin 5  ---- ADS1115 SCL
```

Nie podłączaj wyjścia GP350 bezpośrednio do A0 ani do GPIO. Dzielnik zmienia
10 V na około 2.44 V. Zasil ADS1115 z `3V3`, nie z `5V`, aby linie I2C były
bezpieczne dla Raspberry Pi.

Przed podłączeniem ADS zmierz multimierzem napięcie między tipem i sleeve
minijacka. Upewnij się też w dokumentacji konkretnego modułu GP350, że te dwa
styki są odpowiednio sygnałem i masą.

## 2. Włącz I2C na Raspberry Pi

```bash
sudo raspi-config nonint do_i2c 0
sudo apt update
sudo apt install -y i2c-tools
sudo reboot
```

Po restarcie ADS1115 pod domyślnym adresem powinien być widoczny jako `48`:

```bash
i2cdetect -y 1
```

Brak `48` oznacza problem z połączeniem SDA/SCL, zasilaniem albo adresem ADDR.

## 3. Konfiguracja ciśnienia

Skopiuj przykład do miejsca używanego przez usługę:

```bash
sudo cp /opt/vacuum-instrument-monitor/config/examples/gp350-analog-ads1115.ini \
  /etc/vacuum-monitor/gp350-analog-ads1115.ini
sudoedit /etc/vacuum-monitor/gp350-analog-ads1115.ini
```

Najważniejsze ustawienia:

- `emission_current_ma` musi być identyczne z ustawieniem GP350: `0.1`, `1` albo `10` mA.
- Dla dzielnika 68 kOhm / 22 kOhm pozostaw `divider_top_ohms = 68000` i
  `divider_bottom_ohms = 22000`.
- `pga_gain = 1` wybiera zakres ADS1115 +/-4.096 V; A0 nadal nie może być
  wyższe niż napięcie zasilania ADS1115.
- Ustaw poświadczenia InfluxDB tak samo jak dla VGC402 i ustaw `enabled = true`.

GP350 daje 1 V na dekadę. Kolektor stosuje wzory z instrukcji GP350:

```text
10 mA:  pressure [Torr] = 10^(V - 12)
 1 mA:  pressure [Torr] = 10^(V - 11)
0.1 mA: pressure [Torr] = 10^(V - 10)
```

`V` jest napięciem wyjściowym GP350 odtworzonym z napięcia A0 i dzielnika.
Gdy GP350 zwraca trochę ponad 10 V (wyłączony IG albo overrange), kolektor
zapisuje `quality=error` i `gauge_status=gauge_off_or_overrange`.

## 4. Test i autostart

Test ręczny:

```bash
cd /opt/vacuum-instrument-monitor
uv sync --no-dev
set -a
source /etc/vacuum-monitor/collector.env
set +a
uv run --no-dev python -m collectors.ads1115_collector \
  --config /etc/vacuum-monitor/gp350-analog-ads1115.ini
```

Jeżeli `signal_voltage` różni się od multimetru, popraw tylko
`signal_voltage_offset` po sprawdzeniu dzielnika. Nie zmieniaj rezystorów w
konfiguracji, jeśli ich rzeczywiste wartości są nadal 68 kOhm i 22 kOhm.

Po poprawnym teście zainstaluj usługę:

```bash
sudo /opt/vacuum-instrument-monitor/scripts/install_ads1115_service.sh \
  gp350-analog-ads1115
systemctl status vacuum-monitor-ads1115@gp350-analog-ads1115.service
journalctl -u vacuum-monitor-ads1115@gp350-analog-ads1115.service -f
```

W Grafanie GP350 z analogowego toru ma tagi `device_type=gp350`,
`module_type=i2c`, `command=analog_output`, `device=GP350_1`, `channel=IG1`.

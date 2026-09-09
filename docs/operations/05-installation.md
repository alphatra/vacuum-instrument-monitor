# Instalacja na nowym Raspberry Pi

Instrukcja od zera — świeży system na Raspberry Pi do działającego,
samostartującego pomiaru.

Wymaga uprawnień administratora (`sudo`). Jeśli nie masz do nich dostępu,
poproś osobę techniczną.

## 1. Włącz I2C (tylko gdy używasz ADS1115)

Potrzebne wyłącznie dla GP350 podłączonego przez wyjście analogowe.
Przy GP350/VGC402 na kablu RS-232/RS-485 pomiń ten krok.

```bash
sudo raspi-config nonint do_i2c 0
sudo apt-get update
sudo apt-get install -y i2c-tools
```

Sprawdź, że magistrala istnieje:

```bash
ls /dev/i2c-1
```

## 2. Zainstaluj uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sudo env UV_INSTALL_DIR=/usr/local/bin sh
```

Ważne, żeby `uv` trafił do `/usr/local/bin`, a nie do katalogu domowego —
usługa systemowa nie widzi katalogów domowych i nie uruchomiłaby się.

## 3. Pobierz projekt

```bash
sudo mkdir -p /opt/vacuum-instrument-monitor
sudo chown "$USER" /opt/vacuum-instrument-monitor
git clone https://github.com/alphatra/vacuum-instrument-monitor.git \
  /opt/vacuum-instrument-monitor
```

## 4. Zainstaluj usługę

Wybierz wariant pasujący do Twojego urządzenia.

GP350 przez wyjście analogowe (ADS1115):

```bash
sudo /opt/vacuum-instrument-monitor/scripts/install_ads1115_service.sh \
  gp350-analog-ads1115
```

GP350 albo VGC402 przez kabel serial:

```bash
sudo /opt/vacuum-instrument-monitor/scripts/install_linux_service.sh vgc402
```

Instalator sam: tworzy użytkownika systemowego `vacuum-monitor`, katalogi na
dane i logi, kopiuje pliki konfiguracji do `/etc/vacuum-monitor/`, przygotowuje
środowisko Pythona i włącza autostart po restarcie.

## 5. Sprawdź, czy działa

```bash
systemctl status vacuum-monitor-ads1115@gp350-analog-ads1115.service
journalctl -u vacuum-monitor-ads1115@gp350-analog-ads1115.service -f
```

Powinieneś zobaczyć linie z pomiarami. Jeśli nie — zobacz
[Diagnostyka problemów](03-troubleshooting.md).

## 6. Dostosuj ustawienia

Pliki konfiguracji są w `/etc/vacuum-monitor/`. Co wolno zmieniać opisuje
[Zmiana konfiguracji](04-configuration.md). Po zmianie:

```bash
sudo systemctl restart vacuum-monitor-ads1115@gp350-analog-ads1115.service
```

## Dwa przyrządy naraz

Każdy przyrząd to osobna usługa z własnym plikiem konfiguracji, np. VGC402 na
kablu RS-232 i GP350 czytany przez Arduino:

```bash
sudo scripts/install_linux_service.sh vgc402
sudo scripts/install_linux_service.sh gp350-analog-arduino
```

Podgląd obu naraz:

```bash
journalctl -u 'vacuum-monitor-collector@*' -f
```

### Nadaj portom stałe nazwy

Przy dwóch przyrządach **nie zostawiaj `serial_port = auto`**. Każdy kolektor
przy starcie sprawdza wtedy wszystkie porty po kolei, także ten należący do
drugiego przyrządu. Arduino resetuje się przy każdym otwarciu swojego portu,
więc traci wtedy odczyty.

Skopiuj szablon reguł, wstaw numery seryjne swoich urządzeń i zainstaluj:

```bash
cp udev/99-vacuum-monitor.rules.example udev/99-vacuum-monitor.rules
udevadm info -q property -n /dev/ttyACM0
sudo scripts/install_udev_rules.sh /opt/vacuum-instrument-monitor/udev/99-vacuum-monitor.rules
```

Powstaną stałe nazwy niezależne od kolejności wpinania:

```bash
ls -l /dev/vacuum-*
```

Wpisz je do plików konfiguracji zamiast `auto`:

```ini
[Connection]
serial_port = /dev/vacuum-arduino
```

## Aktualizacja do nowszej wersji

```bash
cd /opt/vacuum-instrument-monitor
sudo scripts/deploy_on_pi.sh
```

Pobiera najnowszy kod, przebudowuje środowisko i restartuje działające usługi.

## Dlaczego instalator robi więcej niż `git clone`

Usługa działa jako osobny użytkownik systemowy z włączoną izolacją katalogów
domowych (`ProtectHome`). Dlatego środowisko Pythona musi być zbudowane poza
katalogiem domowym i należeć do tego użytkownika — inaczej usługa nie
wystartuje, mimo że ręczne uruchomienie z Twojego konta działa. Robi to
`scripts/prepare_runtime.sh`, wywoływany automatycznie przez instalatory i
przez `deploy_on_pi.sh`.

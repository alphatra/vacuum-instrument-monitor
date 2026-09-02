# Zmiana konfiguracji

Ustawienia pomiaru są w pliku tekstowym `.ini` (np. `config/config.ini`
albo `config/examples/vgc402.ini`). Możesz go otworzyć zwykłym edytorem
tekstu. Ten dokument mówi, co wolno bezpiecznie zmienić samodzielnie, a
co wymaga wiedzy o urządzeniu (i lepiej zapytać, zanim ruszysz).

Po każdej zmianie zapisz plik i zrestartuj kolektor:

```bash
sudo systemctl restart vacuum-monitor-collector@gp350-1.service
```

(albo zatrzymaj i uruchom ponownie ręcznie, jeśli nie używasz usługi
systemowej — patrz [Uruchomienie i zatrzymanie](01-start-stop.md)).

Niektóre wersje kolektora wykrywają zmianę pliku same, bez restartu —
ale restart jest zawsze bezpieczny i pewny.

## Bezpieczne do zmiany samodzielnie

### Jak często mierzyć — sekcja `[Collector]`

```ini
[Collector]
interval_seconds = 1.0
```

Większa wartość = rzadszy pomiar, mniej danych. `10.0` znaczy pomiar co
10 sekund. Nie musi być liczbą całkowitą, `0.5` też działa.

### Gdzie zapisywać dane — sekcja `[File]`

```ini
[File]
csv_filepath = data/gp350_readings.csv
csv_mode = overwrite
log_file = logs/collector.log
```

- `csv_filepath` — ścieżka do pliku z pomiarami. Zmień, jeśli chcesz
  osobny plik na każdy dzień/eksperyment.
- `csv_mode` — `overwrite` znaczy "zacznij od nowa przy każdym starcie
  kolektora" (stary plik zostanie nadpisany). `append` znaczy "dopisuj
  do istniejącego pliku". Użyj `append`, jeśli chcesz zachować historię
  między restartami.

### Nazwa urządzenia i kanału — sekcja `[Device]`

```ini
[Device]
device_name = GP350_1
channel = IG1
```

To tylko etykiety, które trafiają do CSV — możesz je zmienić na coś
czytelniejszego dla siebie, np. `device_name = KOMORA_GLOWNA`. Nie wpływa
to na sam pomiar.

### Ile szczegółów w logu — sekcja `[General]`

```ini
[General]
debug = false
log_level = info
```

Ustaw `debug = true` i `log_level = debug`, jeśli masz problem i chcesz
zebrać więcej informacji do pokazania programiście. Na co dzień zostaw
`false` / `info` — więcej logów spowalnia i zaśmieca plik.

## Wymaga wiedzy o urządzeniu — nie zgaduj

Te ustawienia muszą **dokładnie** pasować do fizycznych ustawień
urządzenia (np. przełączników DIP z tyłu GP350). Zła wartość nie
zepsuje niczego trwale, ale pomiar przestanie działać (`timeout` albo
`bad_format` w CSV):

```ini
[Connection]
baudrate = 9600
bytesize = 8
parity = none
stopbits = 1
line_terminator = cr
rs485_address =
```

Jeśli musisz to zmienić — sprawdź najpierw manual urządzenia albo
dokument podłączenia:
[Podłączenie prawdziwego GP350](gp350-wiring.md).

Najbezpieczniejsza opcja, jeśli nie jesteś pewien: zostaw
`serial_port = auto` i `module_type = auto` — kolektor sam spróbuje
rozpoznać urządzenie i dobrać właściwe ustawienia.

## Nie zmieniaj bez konsultacji z programistą

- `device_type` — decyduje, jakiego protokołu kolektor używa do
  rozmowy z urządzeniem. Zła wartość = kolektor w ogóle nie wystartuje.
- Cała sekcja `[InfluxDB]` poza `enabled` — te dane (adres serwera,
  token) dostajesz od osoby, która skonfigurowała bazę danych, nie
  zgaduj ich.
- `command` — konkretna komenda protokołu wysyłana do urządzenia
  (np. `RD`, `PRX`). Zmiana bez znajomości protokołu urządzenia zepsuje
  pomiar.

## Jak sprawdzić, czy zmiana zadziałała

Po restarcie sprawdź log:

```bash
journalctl -u vacuum-monitor-collector@gp350-1.service -n 20
```

Szukaj linii `Kolektor uruchomiony` — pokazuje wszystkie aktualne
ustawienia na raz, dobry sposób żeby potwierdzić, że zmiana się przyjęła.

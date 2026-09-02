# Diagnostyka problemów

Checklist typowych sytuacji — przejdź po kolei zanim zawołasz programistę.
Większość problemów da się rozpoznać z samego CSV albo loga, bez
czytania kodu.

## "Nie wiem, czy pomiar w ogóle działa"

```bash
systemctl status vacuum-monitor-collector@gp350-1.service
```

`active (running)` = działa. `inactive`/`failed` = nie działa, zobacz
niżej "Usługa nie startuje". Jeśli pracujesz bez usługi systemowej,
sprawdź po prostu czy okno terminala z kolektorem nadal jest otwarte i
wypisuje nowe linie.

## "CSV jest puste albo nie przybywają nowe wiersze"

1. Sprawdź, czy proces w ogóle działa (patrz wyżej).
2. Sprawdź log:
   ```bash
   tail -n 50 logs/collector.log
   ```
   albo dla usługi systemowej:
   ```bash
   journalctl -u vacuum-monitor-collector@gp350-1.service -n 50
   ```
3. Szukaj słowa `KRYTYCZNY` albo `critical` — to oznacza, że kolektor w
   ogóle nie wystartował (zły port, zła konfiguracja). Zobacz sekcję
   "Błąd konfiguracji" niżej.
4. Jeśli log pokazuje normalne pomiary, ale CSV jest puste — sprawdź, czy
   patrzysz na właściwy plik. Ścieżka do CSV jest w pliku konfiguracji,
   w sekcji `[File]`, pole `csv_filepath`.

## "Widzę dane w CSV, ale kolumna `quality` nie mówi `good`"

To jest normalne, jeśli zdarza się rzadko — komunikacja po kablu czasem
się myli. Problem jest wtedy, gdy `quality` inne niż `good` pojawia się
**często** albo **stale**.

| Wartość `quality` | Co to znaczy | Co sprawdzić |
| --- | --- | --- |
| `good` | Pomiar OK, użyj do analizy. | — |
| `timeout` | Urządzenie nie odpowiedziało w ogóle. | Kabel odłączony, urządzenie wyłączone, zły port. |
| `bad_format` | Odpowiedź przyszła, ale wygląda dziwnie/nie do rozpoznania. | Zła prędkość transmisji (baudrate) albo złe ustawienia portu w konfiguracji — zobacz [Zmiana konfiguracji](04-configuration.md). Zakłócenia na kablu. |
| `error` | Urządzenie samo zgłosiło błąd (np. czujnik wyłączony, poza zakresem). | To informacja z samego urządzenia — sprawdź jego wyświetlacz/panel. Dla GP350 wartość `9.90E+09` w kolumnie `raw_response` znaczy "ion gauge wyłączony albo się rozgrzewa", to nie jest awaria kolektora. |

Jeżeli **wszystkie** pomiary od dłuższego czasu mają `timeout` — prawie
zawsze to kabel, port albo zasilanie urządzenia, nie kod.

## "Usługa nie startuje" / status `failed`

```bash
systemctl status vacuum-monitor-collector@gp350-1.service
journalctl -u vacuum-monitor-collector@gp350-1.service -n 50
```

Najczęstsze przyczyny:

- Zły port w konfiguracji (urządzenie było podłączone do innego portu
  USB niż zapisany w pliku ustawień).
- Plik konfiguracji ma literówkę albo nieprawidłową wartość — kolektor
  odmawia startu i loguje `KRYTYCZNY BŁĄD KONFIGURACJI` z opisem, co
  dokładnie jest nie tak.
- Port jest już zajęty przez inny program (np. dwa kolektory próbują
  używać tego samego portu).

## "Błąd konfiguracji" przy starcie

Log pokaże dokładnie, które pole jest złe, po polsku, np.:

```text
[KRYTYCZNY BŁĄD KONFIGURACJI] Nieprawidłowy baudrate: 1000. Dozwolone wartości: [...]
```

Otwórz plik konfiguracji, znajdź wskazane pole, popraw wartość na jedną
z dozwolonych wymienionych w komunikacie. Jeśli nie masz pewności jaka
wartość jest poprawna — zobacz [Zmiana konfiguracji](04-configuration.md)
albo dokument podłączenia dla Twojego urządzenia.

## "Autodetekcja (`--discover`) nie widzi urządzenia"

```bash
uv run python -m collectors.gp350_collector --discover
```

Pusta lista albo brak Twojego urządzenia:

1. Sprawdź fizyczne połączenie kabla USB — wyciągnij i włóż ponownie.
2. Sprawdź, czy urządzenie jest włączone i ma prąd.
3. Sprawdź w systemie, czy w ogóle widać nowy port po podłączeniu:
   ```bash
   ls /dev/cu.*      # macOS
   ls /dev/ttyUSB*   # Linux
   ```
   Jeśli nic tam nie ma po podłączeniu kabla — to problem sprzętowy
   (kabel, sterownik USB), nie problem kolektora.
4. Dla GP350: sprawdź przełączniki DIP z tyłu urządzenia zgadzają się z
   ustawieniami w konfiguracji (baudrate, parzystość itd.) — patrz
   [Podłączenie prawdziwego GP350](gp350-wiring.md).

## Pomiar analogowy przez ADS1115 (I2C) — specyficzne problemy

`quality=error` z `gauge_status=i2c_error` w logu:

```bash
i2cdetect -y 1
```

Jeśli w tabeli nie ma adresu `48`, ADS1115 nie jest widziany przez
Raspberry Pi — sprawdź zasilanie (`VDD`, `GND`) i linie `SDA`/`SCL`.
Szczegóły w [Podłączenie GP350 przez ADS1115](gp350-analog-ads1115-wiring.md).

`gauge_status=gauge_off_or_overrange` — GP350 zwraca napięcie powyżej
progu (domyślnie 10.05V), co zwykle znaczy, że czujnik jonizacyjny jest
wyłączony. To informacja z urządzenia, nie awaria pomiaru.

## Kiedy na pewno wołać programistę

- Log pokazuje `Traceback` (wielolinijkowy tekst techniczny z angielskimi
  słowami typu `Error`, ścieżki plików `.py`).
- Ten sam problem powtarza się po restarcie usługi i sprawdzeniu kabli.
- Nie jesteś pewien, czy zmiana w konfiguracji, którą chcesz zrobić, jest
  bezpieczna — pytanie zawsze tańsze niż zepsuty pomiar.

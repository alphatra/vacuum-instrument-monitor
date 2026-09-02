# Uruchomienie i zatrzymanie

Ten dokument opisuje codzienną obsługę — bez edycji kodu.

## Czy system już działa automatycznie?

Jeśli ktoś wcześniej zainstalował "usługę systemową" (systemd) na
Raspberry Pi albo serwerze Linux, pomiar startuje sam po włączeniu
komputera i nie musisz nic robić ręcznie. Sprawdź to najpierw:

```bash
systemctl status vacuum-monitor-collector@gp350-1.service
```

- `active (running)` — pomiar działa, nic nie musisz robić.
- `inactive` albo `failed` — pomiar nie działa, patrz sekcje niżej.
- Komenda zwraca błąd "nie znaleziono" — usługa nie jest zainstalowana,
  używasz trybu ręcznego (sekcja "Uruchomienie ręczne" niżej).

Nazwa po `@` zależy od tego, jak system został skonfigurowany u Ciebie —
typowe nazwy to `gp350-1`, `gp350-2`, `vgc402`. Zapytaj osobę, która
instalowała system, jakich nazw używacie, albo sprawdź:

```bash
systemctl list-units 'vacuum-monitor-*'
```

## Uruchomienie usługi systemowej (jeśli jest zainstalowana)

```bash
sudo systemctl start vacuum-monitor-collector@gp350-1.service
```

## Zatrzymanie usługi systemowej

```bash
sudo systemctl stop vacuum-monitor-collector@gp350-1.service
```

## Restart (zatrzymaj i uruchom ponownie)

Rób to, gdy zmieniłeś ustawienia albo podejrzewasz, że pomiar "się zawiesił":

```bash
sudo systemctl restart vacuum-monitor-collector@gp350-1.service
```

## Podgląd na żywo, co się dzieje

```bash
journalctl -u vacuum-monitor-collector@gp350-1.service -f
```

`-f` znaczy "śledź na żywo" — nowe linie pojawiają się same. Zatrzymaj
podgląd klawiszami `Ctrl+C` (to nie zatrzymuje pomiaru, tylko podgląd).

## Uruchomienie ręczne (bez usługi systemowej, np. na laptopie do testu)

```bash
cd /ścieżka/do/projektu
uv run python -m collectors.gp350_collector --config config/config.ini
```

Zobaczysz linie takie jak:

```text
[2026-01-01T12:00:00] device=GP350_1 channel=IG1 quality=good pressure=1.23e-06 Torr latency=12.34 ms
```

To znaczy, że pomiar działa i dane lecą do pliku CSV. Zatrzymaj klawiszami
`Ctrl+C` — kolektor zamknie plik CSV bezpiecznie, nie urywaj zasilania.

Dla urządzenia INFICON VGC402 zamiast `config/config.ini` użyj configu
tego urządzenia, np.:

```bash
uv run python -m collectors.gp350_collector --config config/examples/vgc402.ini
```

Dla GP350 podłączonego przez ADS1115 (wyjście analogowe, nie kabel
RS-232/RS-485) komenda jest inna:

```bash
uv run python -m collectors.ads1115_collector --config config/examples/gp350-analog-ads1115.ini
```

## Skąd wiem, że dane faktycznie się zapisują?

Otwórz plik CSV wskazany w ustawieniach (domyślnie w folderze `data/`) i
sprawdź, czy przybywają nowe wiersze:

```bash
tail -f data/gp350_readings.csv
```

`Ctrl+C` zatrzymuje tylko podgląd, nie pomiar.

## Jeśli coś nie działa

Zobacz [Diagnostyka problemów](03-troubleshooting.md).

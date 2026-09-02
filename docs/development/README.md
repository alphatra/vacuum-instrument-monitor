# Dokumentacja techniczna

Architektura, protokoły, design decyzje. Dla osób czytających/piszących
kod tego repo.

Jeśli szukasz instrukcji obsługi (uruchomienie, podłączenie sprzętu,
diagnostyka) bez czytania kodu, zajrzyj do
[../operations/](../operations/README.md).

## Spis

- [dzialanie.md](dzialanie.md) — jak działa projekt GP350: protokół,
  parser, przepływ danych do CSV.
- [kolektor_danych.md](kolektor_danych.md) — plan funkcjonalny kolektora,
  podział odpowiedzialności między plikami.
- [warstwa_urzadzen.md](warstwa_urzadzen.md) — architektura profili
  urządzeń (`devices/registry.py`), jak dodać nowe urządzenie.
- [autodetekcja_urzadzen.md](autodetekcja_urzadzen.md) — mechanizm
  automatycznego wykrywania urządzeń na portach serial.
- [scenariusze_konfiguracji.md](scenariusze_konfiguracji.md) — gotowe
  przykłady `config.ini` dla każdego scenariusza (symulator, RS-232,
  RS-485, VGC402, debug, InfluxDB).
- [influxdb_grafana.md](influxdb_grafana.md) — schemat danych InfluxDB,
  zapytania Flux, import dashboardu Grafana.
- [linux_systemd_runner.md](linux_systemd_runner.md) — instalacja na
  Raspberry Pi/Linux, systemd, budowanie binarki PyInstaller, CI.
- [acceptance_tests.md](acceptance_tests.md) — checklist testów
  akceptacyjnych przed uruchomieniem produkcyjnym.

## Sprawdzenie jakości kodu

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run pyrefly check
```

Wszystkie cztery uruchamiane automatycznie w CI (`.github/workflows/ci.yml`)
na każdy push i pull request.

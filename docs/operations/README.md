# Dokumentacja dla obsługi (bez programowania)

Te dokumenty są dla osoby, która na co dzień obsługuje pomiar — nie musi
znać Pythona ani czytać kodu.

Jeśli szukasz dokumentacji technicznej (architektura, protokoły, jak
rozwijać kod), zajrzyj do [../development/](../development/README.md).

## Spis

1. [Uruchomienie i zatrzymanie](01-start-stop.md) —
   jak włączyć pomiar, sprawdzić czy działa, zatrzymać.
2. [Podłączenie urządzenia](02-device-wiring.md) —
   jak fizycznie podłączyć GP350 albo VGC402 do komputera.
3. [Diagnostyka problemów](03-troubleshooting.md) —
   "nie widzę danych", "CSV jest puste", "w logu jest błąd" — co sprawdzić
   zanim zawołasz programistę.
4. [Zmiana konfiguracji](04-configuration.md) —
   co wolno samodzielnie zmienić w pliku ustawień, a czego nie ruszać.

Szczegółowe schematy podłączenia (osobno dla każdego urządzenia):

- [Podłączenie prawdziwego GP350](gp350-wiring.md)
- [Podłączenie GP350 przez wyjście analogowe (ADS1115)](gp350-analog-ads1115-wiring.md)

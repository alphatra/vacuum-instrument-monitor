# Podłączenie urządzenia

Ten dokument to krótki punkt startowy. Szczegółowe instrukcje krok po
kroku, ze schematami, są w osobnych plikach — wybierz swój przypadek
niżej.

## Który dokument mnie dotyczy?

**Masz GP350 z kablem RS-232 albo RS-485** (złącze typu D-sub z tyłu
kontrolera, kabel idzie do adaptera USB-serial) →
[Podłączenie prawdziwego GP350](gp350-wiring.md)

**Masz GP350 tylko z wyjściem analogowym** (gniazdo BNC z tyłu
kontrolera, sygnał 0-10V, brak złącza RS-232/RS-485) →
[Podłączenie GP350 przez ADS1115](gp350-analog-ads1115-wiring.md)

**Masz INFICON VGC402** → schemat jest prostszy: kabel RS-232 z
kontrolera do adaptera USB-serial w komputerze/Raspberry Pi. Nie
potrzeba dodatkowej elektroniki. Ustawienia portu są opisane w pliku
konfiguracji przykładowej `config/examples/vgc402.ini` — nie musisz nic
lutować ani dodawać rezystorów.

## Ogólna zasada bezpieczeństwa

Zanim cokolwiek podłączysz albo odłączysz:

- Nie podłączaj wyjścia analogowego (0-10V) bezpośrednio do Raspberry Pi
  ani żadnego innego mikrokontrolera — zniszczysz go. Wyjście analogowe
  zawsze musi przejść przez dzielnik napięcia opisany w dedykowanym
  dokumencie.
- Nie odłączaj kabli pod napięciem, jeśli nie masz pewności co robisz —
  zapytaj osobę techniczną.
- Praca z aparaturą próżniową i źródłami wysokiego napięcia wymaga
  nadzoru osoby uprawnionej. Ten dokument nie zastępuje instrukcji
  bezpieczeństwa laboratorium.

## Po podłączeniu — jak sprawdzić, że komputer widzi urządzenie

```bash
uv run python -m collectors.gp350_collector --discover
```

Jeśli urządzenie jest podłączone poprawnie, zobaczysz linię z jego typem
i portem, np.:

```text
[0] type=gp350 module=digital port=/dev/cu.usbserial-A baudrate=9600 confidence=1.00 raw='1.23E-06'
```

Jeśli lista jest pusta — patrz [Diagnostyka problemów](03-troubleshooting.md).

# Jak działa projekt GP350

Projekt ma dwa światy:

- `virtual_gp350.py` - symuluje port serial i odpowiada jak GP350.
- `collectors/gp350_collector.py` - czyta ciśnienie z portu, zapisuje CSV i
  opcjonalnie InfluxDB pod Grafanę.

```mermaid
flowchart LR
    User["użytkownik"] --> Virtual["virtual_gp350.py"]
    Collector["gp350_collector.py"] --> Port["port serial"]
    Virtual --> Port
    Collector --> CSV["CSV"]
    Collector --> Influx["InfluxDB"]
    Influx --> Grafana["Grafana"]
    Collector --> Log["log"]
```

## Protokół zgodny z manualem

Najważniejsze: `DGS` nie jest pomiarem ciśnienia.

| Komenda | Znaczenie | Przykład odpowiedzi |
| --- | --- | --- |
| `DS IG` | odczyt ciśnienia RS-232 Module | `1.20E-07` |
| `RD` | odczyt ciśnienia Digital Interface | `1.20E-07` albo `* 1.20E-07` |
| `DGS` | status degas | `0` albo `1` |
| `DG ON` | włącz degas | `OK` albo `INVALID` |
| `DG OFF` | wyłącz degas | `OK` |
| `IG1 ON/OFF` | filament 1 | `OK` albo `INVALID` |
| `IG2 ON/OFF` | filament 2 | `OK` albo `INVALID` |
| `IGB` | status filamentów | `00`, `01`, `10`, `11` |
| `F1 1/F1 0` | cyfrowe sterowanie filamentem 1 | `11G1 ON`, `01G1 OFF` |
| `F2 1/F2 0` | cyfrowe sterowanie filamentem 2 | `12G2 ON`, `02G2 OFF` |
| `PC S` | status process control | `0000` |
| `PC B` | status process control jako bajt | `@` |

## Odczyt ciśnienia

```mermaid
sequenceDiagram
    participant App as collector
    participant Serial as serial_client
    participant GP350 as GP350

    App->>Serial: send_command("DS IG")
    Serial->>GP350: "DS IG\\r\\n"
    GP350-->>Serial: "1.20E-07\\r\\n"
    Serial-->>App: "1.20E-07"
```

Parser przyjmuje format:

```text
X.XXE±XX
```

Przykłady:

```text
1.20E-07
9.90E+09
```

`9.90E+09` oznacza brak poprawnego odczytu, np. ion gauge off albo start po
włączeniu. Kolektor zapisuje to jako `quality=error`.

## CSV

```mermaid
flowchart TD
    Raw["1.20E-07"] --> Parser["GP350Parser"]
    Parser --> Reading["pressure_torr=1.2e-07, quality=good"]
    Reading --> CSV["timestamp,device,channel,pressure_torr,unit,quality,raw_response,latency_ms"]
```

Kolumny:

```text
timestamp,device,channel,pressure_torr,unit,quality,raw_response,latency_ms
```

Nie ma kolumny `gauge_status`, bo odpowiedź pomiarowa GP350 nie zwraca tekstu
`ON/OFF/FAIL`.

## Stany jakości

```mermaid
flowchart LR
    Response["odpowiedź"] --> Good{"X.XXE±XX?"}
    Good -->|tak| QGood["good"]
    Good -->|nie| Err{"błąd GP350?"}
    Err -->|tak| QErr["error"]
    Err -->|nie| Empty{"pusto?"}
    Empty -->|tak| QTimeout["timeout"]
    Empty -->|nie| QBad["bad_format"]
```

## Ustawienia portu

```mermaid
flowchart TD
    Module{"Jaki moduł?"}
    Module --> RS232["RS-232 Module: 300, 7N2, DS IG"]
    Module --> Digital["Digital Interface: 9600, 8N1, RD"]
```

W configu:

```ini
[Connection]
module_type = digital
baudrate = 9600
bytesize = 8
parity = none
stopbits = 1
line_terminator = cr
rs485_address =

[Collector]
command = RD
```

Jeśli `command` albo parametry serial nie są podane, kolektor dobiera defaulty z
`module_type`.

RS-485 z adresem:

```ini
[Connection]
module_type = digital
rs485_address = 1
```

Kolektor wyśle `#01RD`, parser przyjmie `* 1.20E-07`.

## Awaria i błędy

Manualowe błędy:

```text
OVERRUN ERROR
PARITY ERROR
SYNTAX ERROR
INVALID
? SYNTX ER
? PRITY ER
? OVERR ER
? RAM FAIL
? INVALID
```

Kolektor nie crashuje od pojedynczego błędu. Zapisuje rekord z `quality=error`
albo `bad_format`, loguje problem i idzie dalej.

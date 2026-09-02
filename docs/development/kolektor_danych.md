# Kolektor danych - jak działa

Kolektor pyta urządzenie o ciśnienie komendą zgodną z instrukcją, mierzy czas
odpowiedzi, parsuje ASCII i zapisuje wynik do CSV oraz opcjonalnie InfluxDB.

```mermaid
flowchart LR
    GP350["GP350 / virtual_gp350.py"] --> Serial["SerialClient"]
    VGC["INFICON VGC402"] --> Serial
    Serial --> Collector["gp350_collector.py"]
    Collector --> Parser["GP350Parser / VGC402Parser"]
    Parser --> Writer["CsvWriter"]
    Writer --> CSV["data/vacuum_readings.csv"]
    Parser --> Influx["InfluxWriter"]
    Influx --> Bucket["InfluxDB bucket"]
    Collector --> Log["logs/collector.log"]
```

## Komenda pomiarowa

Komenda zależy od `module_type`:

```text
module_type = auto    -> autodetekcja: digital, rs232 albo serial
module_type = rs232   -> DS IG
module_type = digital -> RD
module_type = serial  -> PR1, PR2 albo PRX dla VGC402
```

`DS IG` jest dla RS-232 Module. `RD` jest dla Digital Interface. Odpowiedź ma
postać samej liczby albo liczby z prefixem `*` przy RS-485:

```text
1.20E-07
```

Bez jednostki, bez statusu `ON`, bez przecinka.

`DGS` nie jest pomiarem. `DGS` zwraca status degas: `1` albo `0`.

INFICON VGC402 działa inaczej:

```text
PR1\r\n -> ACK
ENQ     -> 0,1.20E-07\r\n
```

`PR1` czyta kanał 1, `PR2` kanał 2. `PRX` czyta wszystkie kanały jednym
zapytaniem:

```text
PRX\r\n -> ACK
ENQ     -> 0,1.20E-07,0,2.30E-07\r\n
```

Pierwsza liczba w każdej parze to status kanału, druga to ciśnienie w
jednostce ustawionej na kontrolerze. Gdy `pressure_unit = auto`, kolektor przy
starcie wysyła `UNI`, odczytuje jednostkę z urządzenia i dopiero potem mierzy.

```mermaid
flowchart LR
    PRX["PRX"] --> Raw["0,1.20E-07,0,2.30E-07"]
    Raw --> CH1["CSV/Influx: CH1"]
    Raw --> CH2["CSV/Influx: CH2"]
```

## Pętla kolektora

```mermaid
sequenceDiagram
    participant Collector as gp350_collector.py
    participant Client as serial_client.py
    participant Port as serial
    participant Parser as Parser urządzenia
    participant CSV as CsvWriter
    participant Influx as InfluxWriter

    Collector->>Client: send command
    Client->>Port: reset buffers
    Client->>Port: "RD\\r"
    Port-->>Client: "1.20E-07\\r"
    Client-->>Collector: raw_response
    Collector->>Parser: parse(raw_response)
    Parser-->>Collector: pressure_torr + quality + gauge_status
    Collector->>CSV: write(record)
    Collector->>Influx: write(record), jeśli enabled=true
```

## Konfiguracja serial

```ini
[Connection]
module_type = auto
serial_port = auto
baudrate = 9600
bytesize = 8
parity = none
stopbits = 1
line_terminator = cr
rs485_address =
timeout = 1.0
write_timeout = 1.0

[Detection]
device_index = 0
probe_timeout = 0.35
scan_rs485 = false
rs485_addresses = 0-31
```

Manual GP350 dopuszcza:

- `baudrate`: `75`, `150`, `300`, `600`, `1200`, `2400`, `4800`, `9600`, `19200`
- `bytesize`: `7` albo `8`
- `parity`: `none`, `even`, `odd`
- `stopbits`: `1` albo `2`
- `line_terminator`: `crlf`, `cr` albo `lf`

Manual INFICON VGC402 dopuszcza `baudrate`: `9600`, `19200`, `38400`.

Starszy RS-232 Module fabrycznie: `300`, `7`, `none`, `2`.
Digital Interface fabrycznie: `9600`, `8`, `none`, `1`, terminator `CR`.

Jeśli usuniesz `baudrate`, `bytesize`, `parity`, `stopbits` albo `command`,
kolektor dobierze wartości z `module_type`.

Jeśli ustawisz `module_type = auto` i `serial_port = auto`, kolektor najpierw
wykona autodetekcję. Szczegóły: `docs/autodetekcja_urzadzen.md`.

RS-485:

```ini
[Connection]
module_type = digital
rs485_address = 1

[Collector]
command = RD
```

Kolektor wyśle wtedy:

```text
#01RD
```

## Parser

```mermaid
flowchart TD
    Raw["raw_response"] --> Empty{"puste?"}
    Empty -->|tak| Timeout["quality=timeout"]
    Empty -->|nie| Error{"błąd GP350 albo 9.90E+09?"}
    Error -->|tak| Err["quality=error"]
    Error -->|nie| Star{"prefix * ?"}
    Star -->|tak| Strip["usuń *"]
    Star -->|nie| Pressure
    Strip --> Pressure{"format X.XXE±XX?"}
    Pressure -->|tak| Good["quality=good"]
    Pressure -->|nie| Bad["quality=bad_format"]
```

Obsługiwane poprawne odczyty:

```text
1.20E-07
* 1.20E-07
```

Obsługiwane błędy urządzenia:

```text
9.90E+09
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

## CSV

Nagłówek:

```text
timestamp,device,channel,pressure_torr,unit,quality,gauge_status,raw_response,latency_ms
```

Przykład GP350:

```text
2026-06-24T12:00:00+00:00,GP350_1,IG1,1.2e-07,Torr,good,,1.20E-07,12.346
```

Przykład VGC402:

```text
2026-06-24T12:00:00+00:00,VGC402_1,CH1,1.2e-07,Torr,good,ok,"0,1.20E-07",14.120
```

Przykład VGC402 z `PRX`:

```text
2026-06-24T12:00:00+00:00,VGC402_1,CH1,1.2e-07,Torr,good,ok,"0,1.20E-07,0,2.30E-07",14.120
2026-06-24T12:00:00+00:00,VGC402_1,CH2,2.3e-07,Torr,good,ok,"0,1.20E-07,0,2.30E-07",14.120
```

`pressure_unit = auto` jest zalecane dla VGC402. Kolektor używa wtedy `UNI` i
rozpoznaje: `mbar`, `Torr`, `Pa`, `micron`. Wynik i tak zapisuje jako
`pressure_torr`.

## InfluxDB dla Grafany

CSV zostaje lokalnym backupem. InfluxDB jest opcjonalnym drugim outputem pod
Grafanę.

Minimalny config:

```ini
[InfluxDB]
enabled = true
url = http://localhost:8086
org = lab
bucket = vacuum
token_env = INFLUXDB_TOKEN
measurement = vacuum_pressure
```

Szczegóły: `docs/influxdb_grafana.md`.

## Jakość rekordu

```mermaid
flowchart LR
    Good["good"] --> Use["użyj pressure_torr"]
    Timeout["timeout"] --> Gap["luka w danych"]
    Bad["bad_format"] --> Raw["sprawdź raw_response"]
    Error["error"] --> Device["stan urządzenia / błąd protokołu"]
```

Znaczenie:

- `good`: poprawny odczyt ciśnienia.
- `timeout`: brak odpowiedzi.
- `bad_format`: odpowiedź nie pasuje do manualowego formatu ciśnienia.
- `error`: GP350 zwrócił błąd albo `9.90E+09`; VGC402 zwrócił status kanału
  inny niż `0`, np. `7 = bpg_bcg_hpg_error`.

## Odporność

Pojedynczy zły pomiar nie zatrzymuje kolektora.

```mermaid
stateDiagram-v2
    [*] --> Running
    Running --> Running: good / timeout / bad_format / error
    Running --> Running: pojedynczy exception
    Running --> Stopped: Ctrl+C
    Running --> Stopped: 10 wyjątków z rzędu
```

Przy zamkniętym porcie kolektor loguje wyjątek, próbuje dalej i kończy po
`10` błędach z rzędu.

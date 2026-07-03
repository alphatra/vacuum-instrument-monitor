# Alert rules for Grafana Cloud

Use data source: InfluxDB, query language: Flux.

Variables to replace:

- `vacuum` - InfluxDB bucket.
- `vacuum_pressure` - measurement name.
- `VGC402_1` - device tag, or remove device filter for all devices.

## No data from collector

Query:

```flux
from(bucket: "vacuum")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "vacuum_pressure")
  |> filter(fn: (r) => r._field == "pressure_torr" or r._field == "latency_ms")
  |> filter(fn: (r) => r.device == "VGC402_1")
  |> count()
```

Condition:

```text
last() IS BELOW 1
```

Recommended evaluation: every `1m`, for `5m`.

## Any non-good sample

Query:

```flux
from(bucket: "vacuum")
  |> range(start: -2m)
  |> filter(fn: (r) => r._measurement == "vacuum_pressure")
  |> filter(fn: (r) => r._field == "is_good")
  |> filter(fn: (r) => r.device == "VGC402_1")
  |> map(fn: (r) => ({ r with _value: if r._value == false then 1 else 0 }))
  |> sum()
```

Condition:

```text
last() IS ABOVE 0
```

Recommended evaluation: every `1m`, for `1m`.

## Sensor off

Query:

```flux
from(bucket: "vacuum")
  |> range(start: -2m)
  |> filter(fn: (r) => r._measurement == "vacuum_pressure")
  |> filter(fn: (r) => r._field == "gauge_status")
  |> filter(fn: (r) => r.device == "VGC402_1")
  |> filter(fn: (r) => r._value == "sensor_off")
  |> count()
```

Condition:

```text
last() IS ABOVE 0
```

## BPG/BCG/HPG error

Query:

```flux
from(bucket: "vacuum")
  |> range(start: -2m)
  |> filter(fn: (r) => r._measurement == "vacuum_pressure")
  |> filter(fn: (r) => r._field == "gauge_status")
  |> filter(fn: (r) => r.device == "VGC402_1")
  |> filter(fn: (r) => r._value == "bpg_bcg_hpg_error")
  |> count()
```

Condition:

```text
last() IS ABOVE 0
```

## Where to click

1. Grafana Cloud -> Alerting -> Alert rules -> New alert rule.
2. Pick `InfluxDB` data source.
3. Paste query.
4. Add Reduce expression: `last`.
5. Add Threshold expression from the matching condition above.
6. Set folder `Vacuum Monitor`.
7. Set contact point.
8. Save rule.

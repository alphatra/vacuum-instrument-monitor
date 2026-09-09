import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMETHEUS_ALERTS = PROJECT_ROOT / "grafana/prometheus-alert-rules.yml"
PROMETHEUS_DASHBOARD = PROJECT_ROOT / "grafana/vacuum-dashboard-prometheus.json"


def test_prometheus_alert_rules_cover_collector_and_sensor_failures() -> None:
    rules = PROMETHEUS_ALERTS.read_text(encoding="utf-8")

    assert "alert: VacuumCollectorNoData" in rules
    assert "absent_over_time(" in rules
    assert 'vacuum_pressure_latency_ms{device="VGC402_1"}[5m]' in rules

    assert "alert: VacuumReadingTimeout" in rules
    assert 'quality="timeout"' in rules
    assert "count_over_time(" in rules

    assert "alert: VacuumReadingBadFormat" in rules
    assert 'quality="bad_format"' in rules

    assert "alert: VacuumSensorOff" in rules
    assert 'gauge_status="sensor_off"' in rules

    assert "alert: VacuumSensorHardwareError" in rules
    assert "bpg_bcg_hpg_error" in rules
    assert "sensor_error" in rules


def test_prometheus_device_variable_uses_always_present_latency_metric() -> None:
    dashboard = json.loads(PROMETHEUS_DASHBOARD.read_text(encoding="utf-8"))
    device_variable = next(
        item for item in dashboard["templating"]["list"] if item["name"] == "device"
    )

    assert "vacuum_pressure_latency_ms" in device_variable["definition"]
    assert "vacuum_pressure_latency_ms" in device_variable["query"]["query"]
    assert "vacuum_pressure_pressure_torr" not in device_variable["definition"]


def test_quality_panel_counts_samples_over_time() -> None:
    dashboard = json.loads(PROMETHEUS_DASHBOARD.read_text(encoding="utf-8"))
    quality_panel = next(
        panel
        for panel in dashboard["panels"]
        if panel["title"] == "Odczyty według jakości"
    )
    expression = quality_panel["targets"][0]["expr"]

    assert "count_over_time(" in expression
    assert "sum by (quality)" in expression
    assert "[$__interval]" in expression


def test_prometheus_channel_variable_uses_always_present_latency_metric() -> None:
    """A channel whose readings all fail must still be selectable.

    The writer omits pressure_torr for failed readings, so a channel that
    never reports a good one - a VGC402 input with no sensor attached, for
    instance - would be missing from the dropdown, which is exactly the
    channel an operator needs to look at.
    """
    dashboard = json.loads(PROMETHEUS_DASHBOARD.read_text(encoding="utf-8"))
    channel_variable = next(
        item for item in dashboard["templating"]["list"] if item["name"] == "channel"
    )

    assert "vacuum_pressure_latency_ms" in channel_variable["definition"]
    assert "vacuum_pressure_latency_ms" in channel_variable["query"]["query"]
    assert "vacuum_pressure_pressure_torr" not in channel_variable["definition"]
    assert "vacuum_pressure_pressure_torr" not in channel_variable["query"]["query"]

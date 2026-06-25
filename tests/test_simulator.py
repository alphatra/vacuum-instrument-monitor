from simulators.enums import CommunicationQuality, GaugeStatus, SimulationScenario
from simulators.gp350_generator import GP350Parser, GP350Simulator


def test_ds_ig_returns_pressure_without_unit_or_status() -> None:
    sim = GP350Simulator(seed=1)

    response = sim.handle_command("DS IG")
    reading = GP350Parser.parse(response)

    assert reading.quality.value == "good"
    assert reading.unit == "Torr"
    assert reading.gauge_status is None
    assert " " not in response


def test_dgs_returns_degas_status_only() -> None:
    sim = GP350Simulator(seed=1, pressure_torr=1e-6)

    assert sim.handle_command("DGS") == "0"
    assert sim.handle_command("DG ON") == "OK"
    assert sim.handle_command("DGS") == "1"
    assert sim.handle_command("DG OFF") == "OK"
    assert sim.handle_command("DGS") == "0"


def test_dg_accepts_degas_signal_when_pressure_too_high() -> None:
    sim = GP350Simulator(pressure_torr=1e-3)

    assert sim.handle_command("DG ON") == "OK"
    assert sim.handle_command("DGS") == "0"


def test_invalid_command_returns_error() -> None:
    sim = GP350Simulator()

    assert sim.handle_command("NOPE") == "SYNTAX ERROR"


def test_bad_quality_overrides_response() -> None:
    sim = GP350Simulator(communication_quality=CommunicationQuality.BAD_FORMAT)

    assert sim.handle_command("DS IG") == "???"


def test_ig1_off_returns_not_ready_pressure() -> None:
    sim = GP350Simulator()

    assert sim.handle_command("IG1 OFF") == "OK"
    assert sim.handle_command("DS IG") == "9.90E+09"


def test_failure_pressure_does_not_decrease() -> None:
    sim = GP350Simulator(
        scenario=SimulationScenario.FAILURE,
        pressure_torr=1e-6,
        seed=2,
    )
    previous_pressure = sim.pressure_torr

    for _ in range(10):
        sim.step()
        assert sim.pressure_torr >= previous_pressure
        previous_pressure = sim.pressure_torr


def test_failure_scenario_eventually_reports_fail_status() -> None:
    sim = GP350Simulator(
        scenario=SimulationScenario.FAILURE,
        pressure_torr=9.0e-4,
        seed=1,
    )

    response = sim.handle_command("DS IG")
    reading = GP350Parser.parse(response)

    assert sim.gauge_status == GaugeStatus.FAIL
    assert reading.quality.value == "error"
    assert response == "9.90E+09"


def test_rd_supports_digital_interface_pressure() -> None:
    sim = GP350Simulator(seed=1)

    response = sim.handle_command("RD")
    reading = GP350Parser.parse(response)

    assert reading.quality.value == "good"


def test_addressed_digital_command_uses_star_prefix() -> None:
    sim = GP350Simulator(seed=1)

    response = sim.handle_command("#01RD")

    assert response.startswith("* ")


def test_addressed_digital_command_allows_space_after_address() -> None:
    sim = GP350Simulator(seed=1)

    response = sim.handle_command("#01 RD")

    assert response.startswith("* ")


def test_addressed_command_rejects_invalid_address() -> None:
    sim = GP350Simulator(seed=1)

    assert sim.handle_command("#32RD") == "? SYNTX ER"
    assert sim.handle_command("#AARD") == "? SYNTX ER"


def test_addressed_invalid_modifier_uses_digital_error() -> None:
    sim = GP350Simulator(seed=1)

    assert sim.handle_command("#01DG NOPE") == "? SYNTX ER"
    assert sim.handle_command("#01DG ON") == "* 0DG OFF"


def test_digital_degas_reports_on_when_pressure_allows_it() -> None:
    sim = GP350Simulator(pressure_torr=1e-6)

    assert sim.handle_command("#01DG1 ON") == "* 1DG ON"
    assert sim.handle_command("#01DG ON") == "* 1DG ON"
    assert sim.handle_command("#01DGS") == "* 1DG ON"
    assert sim.handle_command("#01DG0 OFF") == "* 0DG OFF"
    assert sim.handle_command("#01DG OFF") == "* 0DG OFF"
    assert sim.handle_command("#01DGS") == "* 0DG OFF"


def test_digital_filament_response_uses_manual_format() -> None:
    sim = GP350Simulator()

    assert sim.handle_command("#01F1 0") == "* 01G1 OFF"
    assert sim.handle_command("#01F1 1") == "* 11G1 ON"
    assert sim.handle_command("#01F2 1") == "* 12G2 ON"
    assert sim.handle_command("#01F2 0") == "* 02G2 OFF"


def test_rd1_and_rd2_check_selected_filament() -> None:
    sim = GP350Simulator(seed=1)

    assert sim.handle_command("RD2") == "9.90E+09"
    assert sim.handle_command("F2 1") == "12G2 ON"
    assert GP350Parser.parse(sim.handle_command("RD2")).quality.value == "good"
    assert sim.handle_command("F1 0") == "01G1 OFF"
    assert sim.handle_command("RD1") == "9.90E+09"


def test_pc_command_modifiers() -> None:
    sim = GP350Simulator(seed=1)

    assert sim.handle_command("#01PC") == "* 0000"
    assert sim.handle_command("#01PC 1") == "* 0"
    assert sim.handle_command("#01PC S") == "* 0000"
    assert sim.handle_command("#01PC B") == "* @"
    assert sim.handle_command("#01PC 1 7.60E-06") == "* PROGM OK"
    assert sim.handle_command("#01PC1_7.60E-06") == "* PROGM OK"
    assert sim.handle_command("#01PC1_7.6E-06") == "? SYNTX ER"
    assert sim.handle_command("#01PC X") == "? SYNTX ER"


def test_undocumented_aliases_are_rejected() -> None:
    sim = GP350Simulator(seed=1)

    assert sim.handle_command("#01PCS") == "? SYNTX ER"
    assert sim.handle_command("#01IGS") == "? SYNTX ER"

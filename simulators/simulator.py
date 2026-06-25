import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .enums import CommunicationQuality, GaugeStatus, SimulationScenario
from .formatting import apply_communication_quality, format_pressure
from .physics import (
    generate_failure_pressure,
    generate_normal_pump_down_pressure,
    generate_stable_pressure,
)


@dataclass(frozen=False)
class GP350Simulator:
    # Stateful command simulator for the documented GP350 serial protocol.
    device_name: str = "gp350"
    channel: str = "IG1"
    unit: str = "Torr"

    gauge_status: GaugeStatus = GaugeStatus.ON
    communication_quality: CommunicationQuality = CommunicationQuality.GOOD
    scenario: SimulationScenario = SimulationScenario.NORMAL_PUMP_DOWN

    pressure_torr: float = 1.0e-3
    simulation_time: float = 0.0

    p0: float = 1.0e-3
    p_min: float = 1.0e-12
    p_max: float = 1.0e-3
    tau: float = 120.0

    noise_relative_std: float = 0.02
    outgassing_probability: float = 0.01

    display_digits: int = 2
    pressure_resolution: float = 1e-10

    manual_pressure_mode: bool = False
    filament_1_on: bool = True
    filament_2_on: bool = False
    degas_active: bool = False

    # Fixed hover target for the STABLE scenario. Set from pressure_torr at
    # construction and whenever the scenario / manual pressure changes.
    stable_setpoint: float = field(init=False, default=1.0e-3)

    seed: int | None = None
    rng: random.Random = field(default_factory=random.Random)

    def __post_init__(self) -> None:
        if self.seed is not None:
            self.rng.seed(self.seed)

        if self.p_min <= 0:
            raise ValueError("p_min must be positive")

        if self.p0 <= 0:
            raise ValueError("p0 must be positive")

        if self.p_max <= self.p_min:
            raise ValueError("p_max must be greater than p_min")

        if self.tau <= 0:
            raise ValueError("tau must be positive")

        if self.noise_relative_std < 0:
            raise ValueError("noise_relative_std must be non-negative")

        if not 0 <= self.outgassing_probability <= 1:
            raise ValueError("outgassing_probability must be between 0 and 1")

        if self.pressure_resolution <= 0:
            raise ValueError("pressure_resolution must be positive")

        if self.pressure_resolution > self.p_max:
            raise ValueError("pressure_resolution must not exceed p_max")

        if not 1 <= self.display_digits <= 10:
            raise ValueError("display_digits must be between 1 and 10")

        if not self.p_min <= self.pressure_torr <= self.p_max:
            raise ValueError("pressure_torr must be between p_min and p_max")

        self.stable_setpoint = self.pressure_torr

    def step(self, dt: float = 1.0) -> None:
        # Time advances for every measurement request.
        self.simulation_time += dt

        if self.gauge_status == GaugeStatus.OFF:
            return

        if self.gauge_status == GaugeStatus.FAIL:
            return

        self.pressure_torr = self.generate_pressure()

    def generate_pressure(self) -> float:
        if self.manual_pressure_mode:
            # Manual mode keeps pressure fixed for direct simulator setup.
            return self.pressure_torr

        if self.scenario == SimulationScenario.NORMAL_PUMP_DOWN:
            return generate_normal_pump_down_pressure(
                self.simulation_time,
                self.p0,
                self.p_min,
                self.p_max,
                self.tau,
                self.noise_relative_std,
                self.outgassing_probability,
                self.rng,
            )

        if self.scenario == SimulationScenario.STABLE:
            return generate_stable_pressure(
                self.stable_setpoint,
                self.simulation_time,
                self.p_min,
                self.p_max,
                self.noise_relative_std,
                self.rng,
            )

        if self.scenario == SimulationScenario.FAILURE:
            # Failure mode rises until pressure is high enough to trip gauge.
            pressure = generate_failure_pressure(
                self.pressure_torr,
                self.p_min,
                self.p_max,
                self.noise_relative_std,
                self.rng,
            )
            pressure = max(self.pressure_torr, pressure)

            if pressure > self.p_max * 0.8:
                self.gauge_status = GaugeStatus.FAIL

            return pressure

        return self.pressure_torr

    def _format_pressure(self) -> str:
        return format_pressure(
            self.pressure_torr,
            self.pressure_resolution,
            self.display_digits,
        )

    def _apply_communication_quality(self, response: str) -> str:
        return apply_communication_quality(response, self.communication_quality)

    def handle_command(self, raw_command: str) -> str:
        command_text = raw_command.strip()
        addressed = False

        if command_text.startswith("#"):
            addressed = True
            if len(command_text) < 3 or not command_text[1:3].isdigit():
                return self._apply_communication_quality(self._syntax_error(addressed))

            address = int(command_text[1:3])
            if address > 31:
                return self._apply_communication_quality(self._syntax_error(addressed))

            command_text = command_text[3:].strip()

        parts = command_text.split()

        if not parts:
            return self._apply_communication_quality(self._syntax_error(addressed))

        command = parts[0].upper()
        args = parts[1:]

        if command.startswith("PC") and command not in {"PC", "PCS"}:
            args = [command[2:], *args]
            command = "PC"

        if command in {"DG1", "DG0"}:
            args = [command[2], *args]
            command = "DG"

        if command in {"RD1", "RD2", "RDA", "RDB"}:
            args = [command[2:], *args]
            command = "RD"

        if addressed and command == "DG":
            command_response = self._handle_dg_digital(args)
            if command_response.startswith("? "):
                return self._apply_communication_quality(command_response)
            return self._apply_communication_quality(f"* {command_response}")

        if addressed and command == "DGS":
            command_response = self._handle_dgs_digital(args)
            if command_response.startswith("? "):
                return self._apply_communication_quality(command_response)
            return self._apply_communication_quality(f"* {command_response}")

        handlers: dict[str, Callable[[list[str]], str]] = {
            "DG": self._handle_dg,
            "DGS": self._handle_dgs,
            "DS": self._handle_ds,
            "IG1": self._handle_ig1,
            "IG2": self._handle_ig2,
            "RD": self._handle_rd,
            "IGB": self._handle_igb,
            "F1": self._handle_f1,
            "F2": self._handle_f2,
            "PC": self._handle_pc,
        }

        handler = handlers.get(command)

        if handler is None:
            return self._apply_communication_quality(self._syntax_error(addressed))

        command_response = handler(args)
        if addressed and command_response == "SYNTAX ERROR":
            command_response = self._syntax_error(addressed)
        elif addressed and command_response == "INVALID":
            command_response = "? INVALID"
        elif addressed and not command_response.startswith("? "):
            command_response = f"* {command_response}"
        return self._apply_communication_quality(command_response)

    def _handle_dg(self, args: list[str]) -> str:
        if len(args) != 1:
            return "SYNTAX ERROR"

        modifier = args[0].upper()
        if modifier in {"ON", "1"}:
            if not self._ion_gauge_active():
                return "INVALID"
            self.degas_active = self.pressure_torr <= 5e-5
            return "OK"

        if modifier in {"OFF", "0"}:
            self.degas_active = False
            return "OK"

        return "SYNTAX ERROR"

    def _handle_dg_digital(self, args: list[str]) -> str:
        if len(args) < 1:
            return "? SYNTX ER"

        modifier = args[0].upper()
        if modifier in {"ON", "1"} and _optional_on_off_matches(args, enabled=True):
            if not self._ion_gauge_active():
                return "? INVALID"
            self.degas_active = self.pressure_torr <= 5e-5
            return "1DG ON" if self.degas_active else "0DG OFF"

        if modifier in {"OFF", "0"} and _optional_on_off_matches(args, enabled=False):
            self.degas_active = False
            return "0DG OFF"

        return "? SYNTX ER"

    def _handle_dgs(self, args: list[str]) -> str:
        if args:
            return "SYNTAX ERROR"
        return "1" if self.degas_active else "0"

    def _handle_dgs_digital(self, args: list[str]) -> str:
        if args:
            return "? SYNTX ER"
        return "1DG ON" if self.degas_active else "0DG OFF"

    def _handle_ds(self, args: list[str]) -> str:
        if len(args) != 1 or args[0].upper() not in {"IG", "IG1", "IG2"}:
            return "SYNTAX ERROR"
        return self._pressure_response()

    def _handle_ig1(self, args: list[str]) -> str:
        return self._set_filament(args, filament_number=1)

    def _handle_ig2(self, args: list[str]) -> str:
        return self._set_filament(args, filament_number=2)

    def _handle_rd(self, args: list[str]) -> str:
        if len(args) > 1:
            return "SYNTAX ERROR"

        selector = args[0].upper() if args else ""
        if selector == "":
            return self._pressure_response()

        if selector == "1":
            return self._pressure_response(filament_number=1)

        if selector == "2":
            return self._pressure_response(filament_number=2)

        if selector in {"A", "B"}:
            return "9.90E+09"

        return "SYNTAX ERROR"

    def _handle_igb(self, args: list[str]) -> str:
        if args:
            return "SYNTAX ERROR"
        if self.filament_1_on and self.filament_2_on:
            return "11"
        if self.filament_1_on:
            return "01"
        if self.filament_2_on:
            return "10"
        return "00"

    def _handle_f1(self, args: list[str]) -> str:
        return self._set_digital_filament(args, filament_number=1)

    def _handle_f2(self, args: list[str]) -> str:
        return self._set_digital_filament(args, filament_number=2)

    def _handle_pc(self, args: list[str]) -> str:
        if not args:
            return "0000"

        if len(args) > 2:
            return "SYNTAX ERROR"

        modifier = args[0].upper()
        if modifier in {"1", "2", "3", "4"} and len(args) == 1:
            return "0"

        if modifier == "S" and len(args) == 1:
            return "0000"

        if modifier == "B" and len(args) == 1:
            return "@"

        if self._is_pc_setpoint_modifier(args):
            return "PROGM OK"

        return "SYNTAX ERROR"

    def _pressure_response(self, filament_number: int | None = None) -> str:
        if filament_number == 1 and not self._filament_active(1):
            return "9.90E+09"

        if filament_number == 2 and not self._filament_active(2):
            return "9.90E+09"

        if filament_number is None and not self._ion_gauge_active():
            return "9.90E+09"

        self.step()

        if filament_number == 1 and not self._filament_active(1):
            return "9.90E+09"

        if filament_number == 2 and not self._filament_active(2):
            return "9.90E+09"

        if filament_number is None and not self._ion_gauge_active():
            return "9.90E+09"

        return self._format_pressure()

    def _set_filament(self, args: list[str], filament_number: int) -> str:
        if len(args) != 1:
            return "SYNTAX ERROR"

        value = args[0].upper()
        if value not in {"ON", "OFF"}:
            return "SYNTAX ERROR"

        current = self.filament_1_on if filament_number == 1 else self.filament_2_on
        requested = value == "ON"
        if current == requested:
            return "INVALID"

        self._apply_filament_state(filament_number, requested)
        return "OK"

    def _set_digital_filament(self, args: list[str], filament_number: int) -> str:
        if len(args) != 1:
            return "SYNTAX ERROR"

        value = args[0].upper()
        if value not in {"1", "0"}:
            return "SYNTAX ERROR"

        enabled = value == "1"
        self._apply_filament_state(filament_number, enabled)
        status_digit = "1" if enabled else "0"
        suffix = "ON" if enabled else "OFF"
        return f"{status_digit}{filament_number}G{filament_number} {suffix}"

    def _apply_filament_state(self, filament_number: int, enabled: bool) -> None:
        if filament_number == 1:
            self.filament_1_on = enabled
        else:
            self.filament_2_on = enabled

        if self.filament_1_on or self.filament_2_on:
            self.gauge_status = GaugeStatus.ON
            return

        self.gauge_status = GaugeStatus.OFF
        self.degas_active = False

    def _ion_gauge_active(self) -> bool:
        return (
            self.gauge_status == GaugeStatus.ON
            and (self.filament_1_on or self.filament_2_on)
        )

    def _filament_active(self, filament_number: int) -> bool:
        if self.gauge_status != GaugeStatus.ON:
            return False

        if filament_number == 1:
            return self.filament_1_on

        return self.filament_2_on

    @staticmethod
    def _is_pc_setpoint_modifier(args: list[str]) -> bool:
        if len(args) == 1:
            return re.match(r"^[1-4]_?[+-]?\d\.\d{2}E[+-]\d{2}$", args[0]) is not None

        if len(args) == 2 and args[0] in {"1", "2", "3", "4"}:
            return re.match(r"^[+-]?\d\.\d{2}E[+-]\d{2}$", args[1]) is not None

        return False

    @staticmethod
    def _syntax_error(addressed: bool = False) -> str:
        return "? SYNTX ER" if addressed else "SYNTAX ERROR"


def _optional_on_off_matches(args: list[str], enabled: bool) -> bool:
    if len(args) == 1:
        return True

    if len(args) != 2:
        return False

    expected = "ON" if enabled else "OFF"
    return args[1].upper() == expected

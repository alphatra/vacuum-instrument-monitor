"""Backward-compatible facade.

The implementation moved into focused modules:

- ``simulators.enums``      — enums (scenario, gauge status, comm quality)
- ``simulators.physics``    — pure pressure-generation functions
- ``simulators.formatting`` — pressure formatting + comm-quality injection
- ``simulators.simulator``  — GP350Simulator (state + command dispatch)
- ``simulators.parser``     — GP350Reading + GP350Parser

This module re-exports the public API so existing imports keep working:
``from simulators.gp350_generator import GP350Simulator``.
"""

from .enums import (
    CommunicationQuality,
    GaugeStatus,
    ParsedQuality,
    SimulationScenario,
)
from .parser import GP350Parser, GP350Reading
from .simulator import GP350Simulator

__all__ = [
    "SimulationScenario",
    "GaugeStatus",
    "CommunicationQuality",
    "ParsedQuality",
    "GP350Simulator",
    "GP350Parser",
    "GP350Reading",
]


if __name__ == "__main__":
    sim = GP350Simulator(seed=123)

    commands = [
        "DS IG",
        "DS IG",
        "DGS",
        "DG ON",
        "DGS",
        "DG OFF",
        "IG1 OFF",
        "DS IG",
        "IG1 ON",
        "DS IG",
        "RD",
        "IGB",
    ]

    for test_command in commands:
        test_response = sim.handle_command(test_command)
        print(f"> {test_command}")
        print(test_response)
        print()

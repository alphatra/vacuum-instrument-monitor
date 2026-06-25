from enum import StrEnum


class SimulationScenario(StrEnum):
    # Pressure behavior models available in simulator.
    NORMAL_PUMP_DOWN = "normal_pump_down"
    STABLE = "stable"
    FAILURE = "failure"


class GaugeStatus(StrEnum):
    # Internal gauge state; pressure commands do not return this text.
    ON = "on"
    OFF = "off"
    FAIL = "fail"


class CommunicationQuality(StrEnum):
    # Artificial communication modes for testing client robustness.
    GOOD = "good"
    TIMEOUT = "timeout"
    BAD_FORMAT = "bad_format"
    ERROR = "error"
    OUT_OF_RANGE = "out_of_range"


class ParsedQuality(StrEnum):
    # Parser result categories for raw device responses.
    GOOD = "good"
    TIMEOUT = "timeout"
    BAD_FORMAT = "bad_format"
    ERROR = "error"

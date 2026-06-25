from simulators.enums import ParsedQuality
from simulators.parser import GP350Parser


def test_parse_pressure_response() -> None:
    reading = GP350Parser.parse("1.23E-06")

    assert reading.pressure_torr == 1.23e-6
    assert reading.unit == "Torr"
    assert reading.gauge_status is None
    assert reading.quality == ParsedQuality.GOOD


def test_parse_digital_pressure_response() -> None:
    reading = GP350Parser.parse("* 1.23E-06")

    assert reading.pressure_torr == 1.23e-6
    assert reading.unit == "Torr"
    assert reading.quality == ParsedQuality.GOOD


def test_parse_timeout() -> None:
    reading = GP350Parser.parse("")

    assert reading.pressure_torr is None
    assert reading.quality == ParsedQuality.TIMEOUT


def test_parse_bad_format_marker() -> None:
    reading = GP350Parser.parse("???")

    assert reading.pressure_torr is None
    assert reading.quality == ParsedQuality.BAD_FORMAT


def test_parse_error_response() -> None:
    reading = GP350Parser.parse("SYNTAX ERROR")

    assert reading.pressure_torr is None
    assert reading.quality == ParsedQuality.ERROR


def test_parse_digital_error_response() -> None:
    reading = GP350Parser.parse("? INVALID")

    assert reading.pressure_torr is None
    assert reading.quality == ParsedQuality.ERROR


def test_parse_not_ready_pressure_as_error() -> None:
    reading = GP350Parser.parse("9.90E+09")

    assert reading.pressure_torr is None
    assert reading.quality == ParsedQuality.ERROR


def test_rejects_non_pressure_status_response() -> None:
    reading = GP350Parser.parse("1")

    assert reading.pressure_torr is None
    assert reading.quality == ParsedQuality.BAD_FORMAT

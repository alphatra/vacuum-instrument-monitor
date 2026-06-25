from simulators.formatting import format_pressure, quantize_pressure


def test_quantize_pressure_to_resolution() -> None:
    assert quantize_pressure(1.23456e-6, 1e-8) == 1.23e-6


def test_format_pressure_uses_scientific_notation() -> None:
    assert format_pressure(1.23456e-6, 1e-10, 2) == "1.23E-06"

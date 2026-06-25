from .enums import CommunicationQuality


def quantize_pressure(pressure: float, resolution: float) -> float:
    # Round reading to configured sensor resolution.
    return round(pressure / resolution) * resolution


def format_pressure(
    pressure: float,
    resolution: float,
    display_digits: int,
) -> str:
    quantized = quantize_pressure(pressure, resolution)
    # GP350-like output uses scientific notation.
    return f"{quantized:.{display_digits}E}"


def apply_communication_quality(
    response: str,
    quality: CommunicationQuality,
) -> str:
    # Communication quality can replace otherwise valid simulator responses.
    if quality == CommunicationQuality.GOOD:
        return response

    if quality == CommunicationQuality.TIMEOUT:
        return ""

    if quality == CommunicationQuality.BAD_FORMAT:
        return "???"

    if quality == CommunicationQuality.ERROR:
        return "ERROR: communication error"

    if quality == CommunicationQuality.OUT_OF_RANGE:
        return "ERROR: out of range"

    return response

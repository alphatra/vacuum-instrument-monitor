from dataclasses import dataclass

VGC402_UNIT_CODES_BY_UNIT = {
    "mbar": "0",
    "torr": "1",
    "pa": "2",
    "micron": "3",
}
VGC402_UNIT_FACTORS_FROM_TORR = {
    "mbar": 1.0 / 0.750061683,
    "torr": 1.0,
    "pa": 1.0 / 0.00750061683,
    "micron": 1000.0,
}
VGC402_VALID_STATUS_CODES = set(range(8))


@dataclass
class VGC402CommandResult:
    accepted: bool
    data: str


@dataclass
class VGC402Simulator:
    unit: str = "torr"
    pressure_torr_ch1: float = 1.23e-6
    pressure_torr_ch2: float = 4.56e-6
    status_ch1: int = 0
    status_ch2: int = 0

    def __post_init__(self) -> None:
        self.unit = self.unit.lower()
        if self.unit not in VGC402_UNIT_CODES_BY_UNIT:
            raise ValueError("unit must be mbar, torr, pa, or micron")
        self._validate_status(self.status_ch1)
        self._validate_status(self.status_ch2)

    def handle_command(self, raw_command: str) -> VGC402CommandResult:
        command = raw_command.strip().upper()
        if command == "PR1":
            return VGC402CommandResult(True, self._format_channel(1))
        if command == "PR2":
            return VGC402CommandResult(True, self._format_channel(2))
        if command == "PRX":
            return VGC402CommandResult(
                True,
                f"{self._format_channel(1)},{self._format_channel(2)}",
            )
        if command == "UNI":
            return VGC402CommandResult(True, VGC402_UNIT_CODES_BY_UNIT[self.unit])

        return VGC402CommandResult(False, "0001")

    def _format_channel(self, channel: int) -> str:
        status = self.status_ch1 if channel == 1 else self.status_ch2
        pressure_torr = (
            self.pressure_torr_ch1 if channel == 1 else self.pressure_torr_ch2
        )

        if status != 0:
            return f"{status},0.0000E+00"

        value = pressure_torr * VGC402_UNIT_FACTORS_FROM_TORR[self.unit]
        return f"{status},{value:.4E}"

    @staticmethod
    def _validate_status(status: int) -> None:
        if status not in VGC402_VALID_STATUS_CODES:
            raise ValueError("status must be in range 0-7")

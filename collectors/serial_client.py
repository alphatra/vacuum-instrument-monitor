import time

import serial


class SerialClient:
    def __init__(
        self,
        port: str,
        baudrate: int,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: float = 1,
        line_terminator: str = "\r\n",
        timeout: float = 1.0,
        write_timeout: float = 1.0,
    ):
        self.line_terminator = line_terminator
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=timeout,
            write_timeout=write_timeout,
        )
        time.sleep(2.0)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    def send_command(self, command: str) -> str:
        if not self.ser.is_open:
            raise serial.SerialException("serial port is closed")

        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.ser.write(f"{command}{self.line_terminator}".encode("ascii"))
        self.ser.flush()
        raw_bytes = (
            self._read_until_cr()
            if self.line_terminator == "\r"
            else self.ser.readline()
        )
        return raw_bytes.decode("ascii", errors="replace").strip()

    def _read_until_cr(self) -> bytes:
        data = b""

        while True:
            byte = self.ser.read(1)
            if not byte:
                break

            data += byte
            if byte == b"\r":
                break

        return data

    def close(self) -> None:
        if self.ser.is_open:
            self.ser.close()

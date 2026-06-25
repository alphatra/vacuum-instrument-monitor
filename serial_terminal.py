import argparse

import serial


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive GP350 serial terminal.")
    parser.add_argument("port", help="Serial port path, e.g. /dev/ttys005")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--bytesize", type=int, choices=[7, 8], default=8)
    parser.add_argument("--parity", choices=["none", "even", "odd"], default="none")
    parser.add_argument("--stopbits", type=float, choices=[1.0, 2.0], default=1.0)
    parser.add_argument("--address", type=int, choices=range(32))
    parser.add_argument(
        "--line-terminator",
        choices=["crlf", "cr", "lf"],
        default="cr",
    )
    return parser.parse_args()


def _read_until_cr(serial_port: serial.Serial) -> bytes:
    data = b""

    while True:
        byte = serial_port.read(1)
        if not byte:
            break

        data += byte
        if byte == b"\r":
            break

    return data


def run_terminal(
    port_name: str,
    baudrate: int = 9600,
    bytesize: int = 8,
    parity: str = "none",
    stopbits: float = 1.0,
    address: int | None = None,
    line_terminator_name: str = "cr",
) -> None:
    parity_map = {
        "none": serial.PARITY_NONE,
        "even": serial.PARITY_EVEN,
        "odd": serial.PARITY_ODD,
    }
    line_terminators = {
        "crlf": "\r\n",
        "cr": "\r",
        "lf": "\n",
    }
    line_terminator = line_terminators[line_terminator_name]

    # Port path usually comes from virtual_gp350.py output.
    with serial.Serial(
        port=port_name,
        baudrate=baudrate,
        bytesize=bytesize,
        parity=parity_map[parity],
        stopbits=stopbits,
        timeout=1.0,
        write_timeout=1.0,
    ) as serial_port:
        serial_port.reset_input_buffer()
        serial_port.reset_output_buffer()

        print(f"Connected to {port_name}")
        print("Type commands: DS IG, DGS, DG ON, DG OFF, IG1 ON, IG1 OFF, RD")
        print("Type quit to exit.")
        print()

        while True:
            try:
                command_text = input("> ").strip()
            except EOFError:
                print()
                break

            if command_text.lower() in ("quit", "exit", "q"):
                break

            # Drop stale bytes so each command reads a fresh response.
            serial_port.reset_input_buffer()
            serial_port.reset_output_buffer()

            command_to_send = command_text
            if address is not None:
                command_to_send = f"#{address:02d}{command_to_send}"

            try:
                encoded_command = (command_to_send + line_terminator).encode("ascii")
            except UnicodeEncodeError:
                print("ERROR: command must use ASCII characters")
                continue

            # GP350 commands are ASCII lines with module-specific terminator.
            serial_port.write(encoded_command)
            serial_port.flush()

            response_bytes = (
                _read_until_cr(serial_port)
                if line_terminator == "\r"
                else serial_port.readline()
            )
            response_text = response_bytes.decode("ascii", errors="replace").strip()

            print(response_text)


def main() -> None:
    args = parse_args()

    try:
        run_terminal(
            port_name=args.port,
            baudrate=args.baudrate,
            bytesize=args.bytesize,
            parity=args.parity,
            stopbits=args.stopbits,
            address=args.address,
            line_terminator_name=args.line_terminator,
        )
    except KeyboardInterrupt:
        print("\nStopped.")
    except serial.SerialException as error:
        print(f"Serial error: {error}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()

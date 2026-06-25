import argparse
import os
import pty
import re
import select
import termios
import tty

from simulators.gp350_generator import GP350Simulator

LINE_PATTERN = re.compile(rb"\r\n|\r|\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a virtual GP350 serial server.")
    parser.add_argument("--seed", type=int, default=123, help="Random seed.")
    parser.add_argument(
        "--module-type",
        choices=["rs232", "digital"],
        default="digital",
        help="Response terminator style.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print raw serial bytes for debugging.",
    )
    return parser.parse_args()


def run_virtual_command_server(
    seed: int = 123,
    verbose: bool = False,
    module_type: str = "digital",
) -> None:
    master_fd: int | None = None
    slave_fd: int | None = None

    # Create a pseudo-terminal pair; external tools connect to the slave path.
    master_fd, slave_fd = pty.openpty()

    try:
        slave_port_name = os.ttyname(slave_fd)
        # Raw mode keeps command bytes close to a real serial connection.
        tty.setraw(master_fd)
        tty.setraw(slave_fd)

        # Disable echo so sent commands do not appear as fake responses.
        attrs = termios.tcgetattr(slave_fd)
        attrs[3] = attrs[3] & ~termios.ECHO
        termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)

        print(f"Virtual GP350 command port created: {slave_port_name}")
        print("Send commands from another terminal/program, e.g.:")
        print(f"  printf 'RD\\r' > {slave_port_name}")
        print("Press Ctrl+C to stop.")
        print()

        sim = GP350Simulator(seed=seed)
        line_terminator = "\r" if module_type == "digital" else "\r\n"
        # Buffer stores partial command lines between reads.
        buffer = b""

        while True:
            readable, _, _ = select.select([master_fd], [], [], 0.1)

            if not readable:
                continue

            chunk = os.read(master_fd, 1024)

            if not chunk:
                continue

            if verbose:
                print(f"RAW BYTES: {chunk!r}")
            buffer += chunk

            # One read can contain many complete CR, LF, or CRLF commands.
            while True:
                line_end = LINE_PATTERN.search(buffer)
                if line_end is None:
                    break

                raw_line = buffer[: line_end.start()]
                buffer = buffer[line_end.end() :]

                command = raw_line.decode("ascii", errors="replace").strip("\r\n ")

                if not command:
                    continue

                response = sim.handle_command(command)
                response_line = _format_response_line(response, line_terminator)

                os.write(master_fd, response_line.encode("ascii"))

                print(f"RX <- {command}")
                print(f"TX -> {response}")

    except KeyboardInterrupt:
        print("\nStopped.")

    finally:
        if master_fd is not None:
            os.close(master_fd)
        if slave_fd is not None:
            os.close(slave_fd)


def _format_response_line(response: str, line_terminator: str) -> str:
    if line_terminator == "\r":
        return response.ljust(10)[:10] + line_terminator

    return response + line_terminator


if __name__ == "__main__":
    args = parse_args()
    run_virtual_command_server(
        seed=args.seed,
        verbose=args.verbose,
        module_type=args.module_type,
    )

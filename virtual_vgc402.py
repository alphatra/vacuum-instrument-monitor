import argparse
import os
import pty
import select
import termios
import tty

from collectors.vgc402 import ACK, ENQ, NAK
from simulators.vgc402_simulator import VGC402Simulator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a virtual INFICON VGC402.")
    parser.add_argument(
        "--unit",
        choices=["mbar", "torr", "pa", "micron"],
        default="torr",
        help="Display unit returned by UNI and used in PR responses.",
    )
    parser.add_argument("--pressure-ch1", type=float, default=1.23e-6)
    parser.add_argument("--pressure-ch2", type=float, default=4.56e-6)
    parser.add_argument("--status-ch1", type=int, default=0, choices=range(8))
    parser.add_argument("--status-ch2", type=int, default=0, choices=range(8))
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print raw serial bytes for debugging.",
    )
    return parser.parse_args()


def run_virtual_command_server(
    *,
    unit: str = "torr",
    pressure_ch1: float = 1.23e-6,
    pressure_ch2: float = 4.56e-6,
    status_ch1: int = 0,
    status_ch2: int = 0,
    verbose: bool = False,
) -> None:
    master_fd: int | None = None
    slave_fd: int | None = None
    master_fd, slave_fd = pty.openpty()

    try:
        slave_port_name = os.ttyname(slave_fd)
        tty.setraw(master_fd)
        tty.setraw(slave_fd)

        attrs = termios.tcgetattr(slave_fd)
        attrs[3] = attrs[3] & ~termios.ECHO
        termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)

        print(f"Virtual VGC402 command port created: {slave_port_name}")
        print("Protocol: command -> ACK/NAK, ENQ -> data")
        print("Example commands: PR1, PR2, PRX, UNI")
        print("Press Ctrl+C to stop.")
        print()

        sim = VGC402Simulator(
            unit=unit,
            pressure_torr_ch1=pressure_ch1,
            pressure_torr_ch2=pressure_ch2,
            status_ch1=status_ch1,
            status_ch2=status_ch2,
        )
        command_buffer = b""
        pending_response: str | None = None

        while True:
            readable, _, _ = select.select([master_fd], [], [], 0.1)
            if not readable:
                continue

            chunk = os.read(master_fd, 1024)
            if not chunk:
                continue

            if verbose:
                print(f"RAW BYTES: {chunk!r}")

            for byte in chunk:
                if byte == ENQ[0]:
                    if pending_response is not None:
                        os.write(master_fd, f"{pending_response}\r\n".encode("ascii"))
                        print(f"TX data -> {pending_response}")
                        pending_response = None
                    continue

                command_buffer += bytes([byte])
                if byte not in (10, 13):
                    continue

                raw_line = command_buffer.strip(b"\r\n ")
                command_buffer = b""
                if not raw_line:
                    continue

                command = raw_line.decode("ascii", errors="replace")
                result = sim.handle_command(command)
                handshake = ACK if result.accepted else NAK
                os.write(master_fd, f"{handshake}\r\n".encode("ascii"))
                pending_response = result.data

                print(f"RX <- {command}")
                print(f"TX handshake -> {'ACK' if result.accepted else 'NAK'}")

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if master_fd is not None:
            os.close(master_fd)
        if slave_fd is not None:
            os.close(slave_fd)


if __name__ == "__main__":
    args = parse_args()
    run_virtual_command_server(
        unit=args.unit,
        pressure_ch1=args.pressure_ch1,
        pressure_ch2=args.pressure_ch2,
        status_ch1=args.status_ch1,
        status_ch2=args.status_ch2,
        verbose=args.verbose,
    )

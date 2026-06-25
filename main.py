import argparse
import time

from simulators.gp350_generator import GP350Simulator


def positive_int(value: str) -> int:
    parsed_value = int(value)
    if parsed_value < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed_value


def non_negative_float(value: str) -> float:
    parsed_value = float(value)
    if parsed_value < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed_value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print sample GP350 responses.")
    parser.add_argument("--seed", type=int, default=1234, help="Random seed.")
    parser.add_argument(
        "--samples",
        type=positive_int,
        default=20,
        help="Number of samples.",
    )
    parser.add_argument(
        "--interval",
        type=non_negative_float,
        default=1.0,
        help="Delay between samples.",
    )
    parser.add_argument("--command", default="DS IG", help="Simulator command to run.")
    return parser.parse_args()


def run_talk_only(
    seed: int = 1234,
    samples: int = 20,
    interval: float = 1.0,
    command: str = "DS IG",
) -> None:
    if samples < 1:
        raise ValueError("samples must be at least 1")

    if interval < 0:
        raise ValueError("interval must be non-negative")

    # Fixed seed makes demo samples repeatable.
    sim = GP350Simulator(seed=seed)

    for i in range(samples):
        # Default DS IG command returns a documented pressure reading.
        response = sim.handle_command(command)
        print(f"Sample {i + 1}/{samples}")
        print(response)
        if interval > 0:
            time.sleep(interval)


if __name__ == "__main__":
    args = parse_args()
    run_talk_only(
        seed=args.seed,
        samples=args.samples,
        interval=args.interval,
        command=args.command,
    )

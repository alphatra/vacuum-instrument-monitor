"""A permanently failing sensor must not flood the journal or run forever.

Observed on hardware: with the ADS1115 unplugged the collector logged a full
traceback every second — 1799 journal lines per minute — and never stopped,
so systemd saw a healthy service that was producing nothing.
"""

import logging

import pytest

from collectors import ads1115_collector as collector
from collectors.ads1115 import Ads1115Config


class BrokenAdc:
    """I2C bus that is gone, e.g. the module lost power."""

    lsb_volts = 0.000125

    def read_raw(self) -> int:
        raise OSError(5, "Input/output error")

    def close(self) -> None:
        pass


class RecordingWriter:
    def __init__(self) -> None:
        self.records: list[object] = []

    def write(self, record: object) -> None:
        self.records.append(record)

    def close(self) -> None:
        pass


def config() -> Ads1115Config:
    return Ads1115Config(interval_seconds=0.0, csv_filepath="data/x.csv")


def test_loop_stops_after_a_run_of_failures() -> None:
    """Otherwise a dead sensor keeps the unit 'active' forever."""
    writer = RecordingWriter()

    collector.run_collection_loop(
        BrokenAdc(),  # type: ignore[arg-type]
        config(),
        writer,  # type: ignore[arg-type]
        None,
        max_iterations=100,
    )

    assert len(writer.records) <= collector.MAX_CONSECUTIVE_ERRORS, (
        f"loop kept going for {len(writer.records)} failed reads; "
        "it must give up so systemd can restart or report the failure"
    )


def test_traceback_is_logged_once_per_failure_run(caplog) -> None:
    """Repeating the same stack trace every second buries real events."""
    caplog.set_level(logging.DEBUG, logger="root")
    writer = RecordingWriter()

    collector.run_collection_loop(
        BrokenAdc(),  # type: ignore[arg-type]
        config(),
        writer,  # type: ignore[arg-type]
        None,
        max_iterations=5,
    )

    with_traceback = [r for r in caplog.records if r.exc_info is not None]
    assert len(with_traceback) == 1, (
        f"{len(with_traceback)} tracebacks for one continuous failure; "
        "expected one, then short lines"
    )


def test_recovered_sensor_resets_the_failure_run() -> None:
    """After a good reading a later failure is a new run, not a continuation."""
    tracker = collector.FailureRun(limit=3)

    assert tracker.failure() == (True, False)
    assert tracker.failure() == (False, False)
    tracker.success()
    assert tracker.failure() == (True, False), "recovery must reset the run"


@pytest.mark.parametrize("limit", [1, 3, 10])
def test_failure_run_reports_stop_at_limit(limit: int) -> None:
    tracker = collector.FailureRun(limit=limit)
    outcomes = [tracker.failure()[1] for _ in range(limit)]

    assert outcomes[-1] is True
    assert not any(outcomes[:-1])

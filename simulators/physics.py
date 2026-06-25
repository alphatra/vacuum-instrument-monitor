import random
from math import exp, sin


def clamp_pressure(pressure: float, p_min: float, p_max: float) -> float:
    # Keep simulated readings inside valid sensor range.
    return max(p_min, min(p_max, pressure))


def generate_normal_pump_down_pressure(
    simulation_time: float,
    p0: float,
    p_min: float,
    p_max: float,
    tau: float,
    noise_relative_std: float,
    outgassing_probability: float,
    rng: random.Random,
) -> float:
    # Pump-down follows exponential decay toward minimum pressure.
    pressure = p_min + (p0 - p_min) * exp(-simulation_time / tau)

    # Slow drift represents temperature and chamber changes.
    drift = 1.0 + 0.03 * sin(simulation_time / 300.0)
    pressure *= drift

    # Gaussian noise makes readings look less ideal.
    noise_factor = rng.normalvariate(1.0, noise_relative_std)
    pressure *= noise_factor

    if rng.random() < outgassing_probability:
        # Outgassing creates rare upward pressure spikes.
        pressure *= rng.uniform(1.5, 5.0)

    return clamp_pressure(pressure, p_min, p_max)


def generate_stable_pressure(
    setpoint: float,
    simulation_time: float,
    p_min: float,
    p_max: float,
    noise_relative_std: float,
    rng: random.Random,
) -> float:
    drift = 1.0 + 0.01 * sin(simulation_time / 600.0)
    noise_factor = rng.normalvariate(1.0, noise_relative_std / 2)

    # Stable mode oscillates around the chosen setpoint.
    pressure = setpoint * drift * noise_factor

    return clamp_pressure(pressure, p_min, p_max)


def generate_failure_pressure(
    pressure_torr: float,
    p_min: float,
    p_max: float,
    noise_relative_std: float,
    rng: random.Random,
) -> float:
    # Failure is modeled as a leak that grows every step.
    leak_growth = 1.03
    pressure = pressure_torr * leak_growth

    # Broken gauge has stronger noise than normal operation.
    noise_factor = rng.normalvariate(1.0, noise_relative_std * 2)
    pressure *= noise_factor

    return clamp_pressure(pressure, p_min, p_max)

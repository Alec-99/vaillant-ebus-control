"""Pure HVAC logic: offline simulation only, never emits boiler commands."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from math import isfinite


@dataclass(frozen=True)
class Reading:
    value_c: float
    observed_at: datetime
    source: str

    def valid(self, now: datetime, max_age: timedelta = timedelta(minutes=10)) -> bool:
        if now.tzinfo is None or self.observed_at.tzinfo is None:
            return False
        age = now - self.observed_at
        return -timedelta(seconds=30) <= age <= max_age and isfinite(self.value_c)


@dataclass(frozen=True)
class Curve:
    slope: float = 1.2
    kp: float = 2.0
    ki: float = 0.0
    min_flow: float = 30.0
    max_flow: float = 65.0
    hysteresis: float = 0.2
    integral_limit: float = 5.0


@dataclass(frozen=True)
class Evaluation:
    demand: bool
    requested_flow_c: float | None
    reason: str
    pump_advice: str = "native-boiler-control-only"


class Thermostat:
    def __init__(self, curve: Curve | None = None):
        self.curve = curve or Curve()
        self.last_heat_demand = False
        self.integral = 0.0
        self.last_at: datetime | None = None

    def evaluate(self, *, mode: str, target: float, room: Reading | None,
                 outdoor: Reading | None, now: datetime | None = None) -> Evaluation:
        now = now or datetime.now(timezone.utc)
        if mode != "heat":
            self._reset(now)
            return Evaluation(False, None, "mode-off")
        if room is None or outdoor is None or not room.valid(now) or not outdoor.valid(now):
            self._reset(now)
            return Evaluation(False, None, "sensor-missing-or-stale")
        if not (-20 <= room.value_c <= 60 and -50 <= outdoor.value_c <= 60):
            self._reset(now)
            return Evaluation(False, None, "sensor-out-of-range")
        error = target - room.value_c
        if self.last_heat_demand:
            demand = room.value_c < target + self.curve.hysteresis
        else:
            demand = room.value_c < target - self.curve.hysteresis
        if not demand:
            self._reset(now)
            return Evaluation(False, None, "target-satisfied")
        elapsed = (now - self.last_at).total_seconds() if self.last_at is not None else 0
        # Guard against delayed inputs or clock jumps, and anti-windup.
        elapsed = max(0.0, min(elapsed, 300.0))
        self.integral = max(-self.curve.integral_limit, min(
            self.curve.integral_limit, self.integral + error * self.curve.ki * elapsed))
        self.last_heat_demand = True
        self.last_at = now
        base = target + self.curve.slope * (target - outdoor.value_c)
        raw = base + self.curve.kp * error + self.integral
        flow = max(self.curve.min_flow, min(self.curve.max_flow, raw))
        return Evaluation(True, round(flow, 2), "simulated-heat-request")

    def _reset(self, now: datetime) -> None:
        self.last_heat_demand = False
        self.last_at = now
        self.integral = 0.0


@dataclass(frozen=True)
class PumpObservation:
    flame_on: bool
    pump_on: bool
    flow_c: float
    return_c: float


def pump_advice(observation: PumpObservation, *, seconds_since_flame_off: float | None,
                naloop_minutes: int = 45, delta_stop_c: float = 0.3) -> str:
    """Observation-only suggestion: NEVER a pump actuator."""
    if observation.flame_on:
        return "heating"
    if not observation.pump_on:
        return "pump-already-off"
    if seconds_since_flame_off is None or seconds_since_flame_off < 0:
        return "insufficient-timing-data"
    delta = observation.flow_c - observation.return_c
    if delta <= delta_stop_c:
        return "low-delta-observed-consider-stop-only-after-validation"
    if seconds_since_flame_off < naloop_minutes * 60:
        return "postrun-active"
    return "extended-circulation-candidate-needs-test"

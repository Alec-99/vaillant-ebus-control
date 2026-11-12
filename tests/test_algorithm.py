from datetime import datetime, timedelta, timezone
import math
from vaillant_control.algorithm import Reading, Thermostat, Curve, PumpObservation, pump_advice

NOW = datetime(2026, 10, 30, 18, 0, tzinfo=timezone.utc)


def sample(value, *, age=0):
    return Reading(value_c=value, observed_at=NOW-timedelta(seconds=age), source="fixture")


def test_curve_calculation_and_room_correction():
    t = Thermostat(Curve(slope=1.2, kp=2.0, min_flow=30, max_flow=65))
    result = t.evaluate(mode="heat", target=21, room=sample(20), outdoor=sample(5), now=NOW)
    assert result.demand
    assert result.requested_flow_c == 42.2   # 21 + 1.2*(21-5) + 2*(21-20)


def test_curve_clamp():
    t = Thermostat(Curve(slope=4, kp=10, min_flow=30, max_flow=65))
    assert t.evaluate(mode="heat", target=22, room=sample(17), outdoor=sample(-20), now=NOW).requested_flow_c == 65


def test_curve_lower_clamp():
    t = Thermostat(Curve(slope=0, kp=0, min_flow=33, max_flow=65))
    assert t.evaluate(mode="heat", target=20, room=sample(18), outdoor=sample(10), now=NOW).requested_flow_c == 33


def test_mode_off_disables_demand():
    t = Thermostat()
    assert t.evaluate(mode="off", target=21, room=sample(20), outdoor=sample(10), now=NOW).reason == "mode-off"


def test_stale_room_disables_demand():
    t = Thermostat()
    r = t.evaluate(mode="heat", target=21, room=sample(20, age=601), outdoor=sample(10), now=NOW)
    assert not r.demand and r.requested_flow_c is None


def test_stale_outdoor_disables_demand():
    t = Thermostat()
    assert t.evaluate(mode="heat", target=21, room=sample(20), outdoor=None, now=NOW).reason == "sensor-missing-or-stale"


def test_reading_clock_skew_rejected():
    assert not Reading(12, NOW+timedelta(minutes=1), "test").valid(NOW)
    assert not Reading(float("nan"), NOW, "test").valid(NOW)


def test_hysteresis_and_reentry():
    t = Thermostat(Curve(hysteresis=0.2))
    assert t.evaluate(mode="heat", target=21, room=sample(20.7), outdoor=sample(5), now=NOW).demand
    assert t.evaluate(mode="heat", target=21, room=sample(21.1), outdoor=sample(5), now=NOW).demand
    assert not t.evaluate(mode="heat", target=21, room=sample(21.2), outdoor=sample(5), now=NOW).demand
    assert not t.evaluate(mode="heat", target=21, room=sample(20.9), outdoor=sample(5), now=NOW).demand
    assert t.evaluate(mode="heat", target=21, room=sample(20.79), outdoor=sample(5), now=NOW).demand


def test_integral_capped_and_reset():
    t = Thermostat(Curve(ki=0.02, integral_limit=3))
    t.evaluate(mode="heat", target=22, room=sample(20), outdoor=sample(0), now=NOW)
    t.evaluate(mode="heat", target=22, room=sample(20), outdoor=sample(0), now=NOW+timedelta(minutes=5))
    assert t.integral == 3
    t.evaluate(mode="off", target=22, room=sample(20), outdoor=sample(0), now=NOW)
    assert t.integral == 0


def test_pump_advice_never_actuates():
    obs = PumpObservation(flame_on=False, pump_on=True, flow_c=34.31, return_c=34.06)
    assert "low-delta" in pump_advice(obs, seconds_since_flame_off=430)
    assert pump_advice(obs, seconds_since_flame_off=None) == "insufficient-timing-data"
    assert pump_advice(PumpObservation(True, True, 43, 35), seconds_since_flame_off=0) == "heating"
    assert pump_advice(PumpObservation(False, False, 34, 34), seconds_since_flame_off=430) == "pump-already-off"
    assert pump_advice(PumpObservation(False, True, 43, 35), seconds_since_flame_off=500) == "postrun-active"

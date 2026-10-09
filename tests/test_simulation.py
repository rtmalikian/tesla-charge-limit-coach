"""End-to-end test: fake fleet over virtual time.

Core invariant: after a road trip, the charge limit is reset to the daily
target EXACTLY once when the car parks at home — never while away, never
repeatedly, and never when the limit was set at home before departure.
"""
from datetime import datetime

from tesla_charge_limit_coach.config import Settings, VehicleConfig
from tesla_charge_limit_coach.limit_coach import LimitCoachDecider
from tesla_charge_limit_coach.simulator import FakeVehicle, run_simulation


def make_settings(**over):
    kw = dict(
        vehicles=[VehicleConfig(name="Model Y", vin="VIN1")],
        home_lat=34.05, home_lon=-118.25, home_radius_m=500.0,
        high_limit=85, home_limit=80, poll_interval_seconds=3600,
    )
    kw.update(over)
    return Settings(**kw)


def test_limit_resets_exactly_once_after_road_trip():
    start = datetime.now().astimezone().replace(hour=6, minute=0, second=0, microsecond=0)
    # Trip already underway; car returns home at 11:00 with the 100% trip
    # limit still set.
    vehicles = [FakeVehicle(vin="VIN1", name="Model Y", charge_limit_soc=100,
                            at_home=False, home_plan=[(5.0, True)])]
    settings = make_settings()
    report = run_simulation(vehicles, LimitCoachDecider(settings), settings, start, hours=12.0)

    resets = [c for c in report["commands"] if c[0] == "set_charge_limit"]
    assert len(resets) == 1, f"expected exactly one reset, got {report['commands']}"
    assert resets[0][2] == 80
    assert report["final_limit"]["Model Y"] == 80


def test_reset_fires_on_return_not_before():
    start = datetime.now().astimezone().replace(hour=6, minute=0, second=0, microsecond=0)
    vehicles = [FakeVehicle(vin="VIN1", name="Model Y", charge_limit_soc=100,
                            at_home=False, home_plan=[(5.0, True)])]
    settings = make_settings()
    report = run_simulation(vehicles, LimitCoachDecider(settings), settings, start, hours=12.0)

    reset_tick = next(t for t in report["timeline"]
                      if any(a[0] == "SetChargeLimit" for a in t["actions"]))
    assert reset_tick["time"] >= "11:00", f"reset fired too early: {reset_tick['time']}"


def test_pre_trip_limit_survives_until_return_home():
    # The 100% was set at home before departure: it must NOT be clobbered
    # while the car is still home — it only resets after the return-home
    # transition at 17:00.
    start = datetime.now().astimezone().replace(hour=6, minute=0, second=0, microsecond=0)
    vehicles = [FakeVehicle(vin="VIN1", name="Model Y", charge_limit_soc=100,
                            at_home=True, home_plan=[(2.5, False), (11.0, True)])]
    settings = make_settings()
    report = run_simulation(vehicles, LimitCoachDecider(settings), settings, start, hours=12.0)

    reset_tick = next(t for t in report["timeline"]
                      if any(a[0] == "SetChargeLimit" for a in t["actions"]))
    assert reset_tick["time"] >= "17:00", f"pre-trip limit clobbered early: {reset_tick['time']}"
    assert report["final_limit"]["Model Y"] == 80


def test_no_reset_when_car_stays_away():
    start = datetime.now().astimezone().replace(hour=6, minute=0, second=0, microsecond=0)
    vehicles = [FakeVehicle(vin="VIN1", name="Model Y", charge_limit_soc=100, at_home=False)]
    settings = make_settings()
    report = run_simulation(vehicles, LimitCoachDecider(settings), settings, start, hours=6.0)
    assert report["commands"] == []


def test_no_reset_when_already_at_daily_limit():
    start = datetime.now().astimezone().replace(hour=6, minute=0, second=0, microsecond=0)
    vehicles = [FakeVehicle(vin="VIN1", name="Model Y", charge_limit_soc=80,
                            at_home=False, home_plan=[(5.0, True)])]
    settings = make_settings()
    report = run_simulation(vehicles, LimitCoachDecider(settings), settings, start, hours=12.0)
    assert report["commands"] == []


def test_no_wake_when_car_asleep():
    """The coach must never wake the car: an asleep car yields no data
    calls, no commands, and no crash."""
    start = datetime.now().astimezone().replace(hour=6, minute=0, second=0, microsecond=0)
    vehicles = [FakeVehicle(vin="VIN1", name="Model Y", charge_limit_soc=100, awake=False)]
    settings = make_settings()
    report = run_simulation(vehicles, LimitCoachDecider(settings), settings, start, hours=4.0)
    assert report["commands"] == []
    assert report["data_calls"] == 0

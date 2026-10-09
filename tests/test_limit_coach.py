"""Decision-logic unit tests (no network, `now` injected)."""
from datetime import datetime

from tesla_charge_limit_coach.config import Settings, VehicleConfig
from tesla_charge_limit_coach.limit_coach import (
    LimitCoachDecider,
    SetChargeLimit,
    VehicleChargeState,
)

NOW = datetime(2026, 10, 9, 18, 0, 0)


def make_settings(**over):
    kw = dict(
        vehicles=[VehicleConfig(name="Model Y", vin="VIN1")],
        home_lat=34.05, home_lon=-118.25, home_radius_m=500.0,
        high_limit=85, home_limit=80,
    )
    kw.update(over)
    return Settings(**kw)


def state(**over):
    kw = dict(vin="VIN1", name="Model Y", parked=True, at_home=True,
              charge_limit_soc=100)
    kw.update(over)
    return VehicleChargeState(**kw)


def observe_away(d, limit=100):
    """Record a prior away observation so the next home pass is a return."""
    d.decide([state(at_home=False, charge_limit_soc=limit)], NOW)


def test_resets_high_limit_on_return_home():
    d = LimitCoachDecider(make_settings())
    observe_away(d)
    decision = d.decide([state(at_home=True, charge_limit_soc=100)], NOW)
    assert len(decision.actions) == 1
    a = decision.actions[0]
    assert isinstance(a, SetChargeLimit)
    assert a.new_limit == 80
    assert "VIN1" in d.last_reset


def test_no_reset_on_first_observation_at_home():
    # Car is home with 100% and we've never seen it away: no transition,
    # so the coach leaves a pre-trip limit alone.
    d = LimitCoachDecider(make_settings())
    assert d.decide([state(at_home=True, charge_limit_soc=100)], NOW).actions == []


def test_no_action_when_limit_already_low_on_return():
    d = LimitCoachDecider(make_settings())
    for limit in (50, 70, 80, 84, 85):
        d2 = LimitCoachDecider(make_settings())
        observe_away(d2)
        assert d2.decide([state(at_home=True, charge_limit_soc=limit)], NOW).actions == [], limit


def test_boundary_above_threshold_resets():
    d = LimitCoachDecider(make_settings())
    observe_away(d)
    decision = d.decide([state(at_home=True, charge_limit_soc=86)], NOW)
    assert len(decision.actions) == 1


def test_no_action_away_from_home():
    d = LimitCoachDecider(make_settings())
    assert d.decide([state(at_home=False, charge_limit_soc=100)], NOW).actions == []


def test_no_action_when_driving():
    d = LimitCoachDecider(make_settings())
    observe_away(d)
    assert d.decide([state(parked=False, at_home=True, charge_limit_soc=100)],
                    NOW).actions == []


def test_no_action_when_asleep():
    d = LimitCoachDecider(make_settings())
    observe_away(d)
    decision = d.decide([state(asleep=True, charge_limit_soc=100)], NOW)
    assert decision.actions == []
    assert "asleep" in decision.note


def test_no_action_when_limit_unknown():
    d = LimitCoachDecider(make_settings())
    observe_away(d)
    assert d.decide([state(at_home=True, charge_limit_soc=None)], NOW).actions == []


def test_reset_fires_once_per_return():
    d = LimitCoachDecider(make_settings())
    observe_away(d)
    first = d.decide([state(at_home=True, charge_limit_soc=100)], NOW)
    second = d.decide([state(at_home=True, charge_limit_soc=80)], NOW)
    assert len(first.actions) == 1
    assert second.actions == []


def test_multiple_vehicles_mixed():
    d = LimitCoachDecider(make_settings())
    d.decide([state(vin="VIN1", name="Model Y", at_home=False),
              state(vin="VIN2", name="Model 3", at_home=False),
              state(vin="VIN3", name="CT", at_home=False)], NOW)
    states = [
        state(vin="VIN1", name="Model Y", charge_limit_soc=100),   # returned w/ 100
        state(vin="VIN2", name="Model 3", charge_limit_soc=80),    # returned w/ 80
        state(vin="VIN3", name="CT", at_home=False, charge_limit_soc=100),  # still away
    ]
    decision = d.decide(states, NOW)
    assert [(a.vin, a.new_limit) for a in decision.actions] == [("VIN1", 80)]


def test_custom_thresholds():
    d = LimitCoachDecider(make_settings(high_limit=90, home_limit=75))
    observe_away(d)
    decision = d.decide([state(at_home=True, charge_limit_soc=95)], NOW)
    assert decision.actions[0].new_limit == 75
    d2 = LimitCoachDecider(make_settings(high_limit=90, home_limit=75))
    observe_away(d2, limit=90)
    assert d2.decide([state(at_home=True, charge_limit_soc=90)], NOW).actions == []


def test_state_roundtrip():
    d = LimitCoachDecider(make_settings())
    observe_away(d)
    d.decide([state(at_home=True, charge_limit_soc=100)], NOW)
    d2 = LimitCoachDecider(make_settings())
    d2.from_dict(d.to_dict())
    assert d2.last_reset == d.last_reset
    assert d2.last_home == d.last_home

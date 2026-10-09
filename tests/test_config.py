"""Config parsing tests."""
import pytest

from tesla_charge_limit_coach.config import ConfigError, load_settings

BASE = {
    "TESLA_CLIENT_ID": "id",
    "TESLA_CLIENT_SECRET": "secret",
    "TCC_VEHICLES": "Daily=VIN1,Second=VIN2",
    "TCC_HOME_LAT": "34.05",
    "TCC_HOME_LON": "-118.25",
}


def test_vehicle_parsing():
    s = load_settings(dict(BASE))
    assert [(v.name, v.vin) for v in s.vehicles] == [("Daily", "VIN1"), ("Second", "VIN2")]


def test_limit_defaults():
    s = load_settings(dict(BASE))
    assert s.high_limit == 85
    assert s.home_limit == 80
    assert s.poll_interval_seconds == 3600


def test_limit_overrides():
    s = load_settings({**BASE, "TCC_HIGH_LIMIT": "90", "TCC_HOME_LIMIT": "70"})
    assert s.high_limit == 90
    assert s.home_limit == 70


def test_home_limit_must_be_below_high_limit():
    with pytest.raises(ConfigError):
        load_settings({**BASE, "TCC_HIGH_LIMIT": "80", "TCC_HOME_LIMIT": "85"})
    with pytest.raises(ConfigError):
        load_settings({**BASE, "TCC_HIGH_LIMIT": "85", "TCC_HOME_LIMIT": "85"})


def test_limits_out_of_range_rejected():
    with pytest.raises(ConfigError):
        load_settings({**BASE, "TCC_HIGH_LIMIT": "110"})
    with pytest.raises(ConfigError):
        load_settings({**BASE, "TCC_HOME_LIMIT": "40"})


def test_half_home_rejected():
    with pytest.raises(ConfigError):
        load_settings({**BASE, "TCC_HOME_LON": ""})


def test_missing_vehicles_rejected():
    env = dict(BASE)
    del env["TCC_VEHICLES"]
    with pytest.raises(ConfigError):
        load_settings(env)


def test_simulate_needs_no_config():
    s = load_settings({}, require_auth=False)
    assert s.vehicles == []

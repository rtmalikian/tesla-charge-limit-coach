"""Configuration for Tesla Charge Limit Coach. All settings come from the
environment (see .env.example). Copy .env.example to .env — .env is
git-ignored so secrets never leave your machine."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


class ConfigError(Exception):
    pass


@dataclass
class VehicleConfig:
    name: str
    vin: str


@dataclass
class Settings:
    client_id: str = ""
    client_secret: str = ""
    region: str = "na"
    redirect_uri: str = "http://localhost:8080/callback"
    token_file: str = "~/.tcc/tokens.json"
    vehicles: list[VehicleConfig] = field(default_factory=list)
    home_lat: float | None = None
    home_lon: float | None = None
    home_radius_m: float = 200.0
    high_limit: int = 85
    home_limit: int = 80
    state_file: str = "~/.tcc/charge_limit_coach_state.json"
    poll_interval_seconds: int = 3600
    dry_run: bool = False


def _parse_vehicles(raw: str) -> list[VehicleConfig]:
    """Format: name=VIN,name2=VIN2 (or bare VINs)."""
    vehicles = []
    for idx, item in enumerate(raw.split(",")):
        item = item.strip()
        if not item:
            continue
        name = None
        if "=" in item:
            name, item = item.split("=", 1)
            name = name.strip()
        vin = item.strip()
        if not vin:
            raise ConfigError("Empty VIN in TCC_VEHICLES")
        vehicles.append(VehicleConfig(name=name or f"car-{idx + 1}", vin=vin))
    if not vehicles:
        raise ConfigError("TCC_VEHICLES is empty — add at least one name=VIN entry")
    return vehicles


def _float(env: dict, key: str, default: float | None) -> float | None:
    raw = env.get(key)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc


def _int(env: dict, key: str, default: int) -> int:
    raw = env.get(key, None)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc


def _bool(env: dict, key: str, default: bool) -> bool:
    return env.get(key, "true" if default else "false").strip().lower() in ("1", "true", "yes", "on")


def load_settings(env: dict | None = None, require_auth: bool = True) -> Settings:
    env = env if env is not None else os.environ

    client_id = env.get("TESLA_CLIENT_ID", "").strip()
    client_secret = env.get("TESLA_CLIENT_SECRET", "").strip()
    if require_auth and (not client_id or not client_secret):
        raise ConfigError("TESLA_CLIENT_ID and TESLA_CLIENT_SECRET are required (see README).")

    region = env.get("TESLA_REGION", "na").strip().lower()
    if region not in ("na", "eu", "cn"):
        raise ConfigError(f"TESLA_REGION must be na/eu/cn, got {region!r}")

    home_lat = _float(env, "TCC_HOME_LAT", None)
    home_lon = _float(env, "TCC_HOME_LON", None)
    if (home_lat is None) != (home_lon is None):
        raise ConfigError("TCC_HOME_LAT and TCC_HOME_LON must be set together")
    if home_lat is not None and not (-90 <= home_lat <= 90 and -180 <= home_lon <= 180):
        raise ConfigError("TCC_HOME_LAT/LON out of range")

    high_limit = _int(env, "TCC_HIGH_LIMIT", 85)
    home_limit = _int(env, "TCC_HOME_LIMIT", 80)
    if not (50 <= home_limit < high_limit <= 100):
        raise ConfigError(
            f"TCC_HOME_LIMIT ({home_limit}) must be below TCC_HIGH_LIMIT ({high_limit}), "
            "both in 50–100"
        )

    vehicles_raw = env.get("TCC_VEHICLES", "").strip()
    vehicles = _parse_vehicles(vehicles_raw) if (require_auth or vehicles_raw) else []

    return Settings(
        client_id=client_id,
        client_secret=client_secret,
        region=region,
        redirect_uri=env.get("TESLA_REDIRECT_URI", "http://localhost:8080/callback").strip(),
        token_file=env.get("TESLA_TOKEN_FILE", "~/.tcc/tokens.json").strip(),
        vehicles=vehicles,
        home_lat=home_lat,
        home_lon=home_lon,
        home_radius_m=_float(env, "TCC_HOME_RADIUS_M", 200.0) or 200.0,
        high_limit=high_limit,
        home_limit=home_limit,
        state_file=env.get("TCC_STATE_FILE", "~/.tcc/charge_limit_coach_state.json").strip(),
        poll_interval_seconds=_int(env, "TCC_POLL_INTERVAL_SECONDS", 3600),
        dry_run=_bool(env, "TCC_DRY_RUN", False),
    )

"""Run loop: read vehicle state, decide, execute.

Cost discipline: the coach NEVER wakes the car just to check the charge
limit (wakes are the priciest Fleet API call). If the car is asleep, the
pass is skipped and retried on the next poll.
"""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime
from pathlib import Path

from .config import Settings
from .limit_coach import Decision, LimitCoachDecider, SetChargeLimit, VehicleChargeState
from .tesla_client import TeslaApiError, TeslaClient

log = logging.getLogger("tcc-limit")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def build_states(client, settings: Settings) -> list[VehicleChargeState]:
    states = []
    for vc in settings.vehicles:
        data = client.read_if_awake(vc.vin)
        if data is None:
            log.info("%s: asleep or unreachable — skipping (no wake)", vc.name)
            continue
        charge = data.get("charge_state", {}) or {}
        drive = data.get("drive_state", {}) or {}
        shift = drive.get("shift_state")
        parked = shift in ("P", None)
        at_home = False
        lat, lon = drive.get("latitude"), drive.get("longitude")
        if settings.home_lat is not None and lat and lon:
            at_home = haversine_m(lat, lon, settings.home_lat, settings.home_lon) <= settings.home_radius_m
        states.append(VehicleChargeState(
            vin=vc.vin,
            name=vc.name,
            parked=parked,
            at_home=at_home,
            charge_limit_soc=charge.get("charge_limit_soc"),
        ))
    return states


def load_decider(settings: Settings) -> LimitCoachDecider:
    decider = LimitCoachDecider(settings)
    path = Path(settings.state_file).expanduser()
    if path.exists():
        try:
            decider.from_dict(json.loads(path.read_text()))
        except Exception as exc:
            log.warning("Could not load state file: %s", exc)
    return decider


def save_decider(decider: LimitCoachDecider, settings: Settings) -> None:
    path = Path(settings.state_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(decider.to_dict(), indent=2))


def execute(client, settings: Settings, decision: Decision) -> None:
    for action in decision.actions:
        if isinstance(action, SetChargeLimit):
            log.info("LIMIT SET   %s -> %d%% (%s)", action.name, action.new_limit, action.reason)
            if not settings.dry_run:
                try:
                    client.set_charge_limit(action.vin, action.new_limit)
                except TeslaApiError as exc:
                    log.warning("set_charge_limit failed for %s: %s", action.name, exc)
    if decision.note:
        log.info("note: %s", decision.note)


def run_once(client, decider: LimitCoachDecider, settings: Settings,
             now: datetime | None = None) -> Decision:
    """Single sense-decide-act pass."""
    now = now or datetime.now().astimezone()
    states = build_states(client, settings)
    for s in states:
        log.info("%-12s limit=%s parked=%s home=%s",
                 s.name, s.charge_limit_soc, s.parked, s.at_home)
    decision = decider.decide(states, now)
    execute(client, settings, decision)
    save_decider(decider, settings)
    return decision


def run_loop(settings: Settings) -> None:
    client = TeslaClient(
        client_id=settings.client_id, client_secret=settings.client_secret,
        region=settings.region, redirect_uri=settings.redirect_uri,
        token_file=settings.token_file,
    )
    decider = load_decider(settings)
    mode = "DRY-RUN" if settings.dry_run else "LIVE"
    log.info("Tesla Charge Limit Coach starting (%s), poll every %ds",
             mode, settings.poll_interval_seconds)
    while True:
        try:
            run_once(client, decider, settings)
        except TeslaApiError as exc:
            log.error("Fleet API error: %s", exc)
        except Exception:
            log.exception("Unexpected error in run loop")
        time.sleep(settings.poll_interval_seconds)

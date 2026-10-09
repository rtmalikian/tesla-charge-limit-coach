"""Fake fleet for testing and demos. No API calls, no real cars."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class FakeVehicle:
    vin: str
    name: str
    charge_limit_soc: int = 80
    parked: bool = True
    at_home: bool = True
    awake: bool = True
    # Scripted road trips: list of (hour_offset_from_start, at_home) switches.
    home_plan: list[tuple[float, bool]] = field(default_factory=list)

    def tick(self, minutes: float) -> None:
        pass  # charge limit only changes via commands


class FakeTeslaClient:
    """Stand-in for TeslaClient with the methods the scheduler uses."""

    def __init__(self, vehicles: list[FakeVehicle]):
        self.vehicles = {v.vin: v for v in vehicles}
        self.command_log = []
        self.data_calls = 0

    def read_if_awake(self, vin: str) -> dict | None:
        v = self.vehicles[vin]
        if not v.awake:
            return None
        self.data_calls += 1
        lat, lon = (34.05, -118.25) if v.at_home else (36.5, -121.9)
        return {
            "state": "online",
            "charge_state": {"charge_limit_soc": v.charge_limit_soc},
            "drive_state": {
                "shift_state": "P" if v.parked else "D",
                "latitude": lat, "longitude": lon,
            },
        }

    def set_charge_limit(self, vin: str, percent: int) -> dict:
        self.vehicles[vin].charge_limit_soc = percent
        self.command_log.append(("set_charge_limit", vin, percent))
        return {"result": True}


def run_simulation(vehicles: list[FakeVehicle], decider, settings, start: datetime,
                   hours: float = 12.0, tick_minutes: float = 15.0) -> dict:
    """Drive the real scheduler against the fake fleet over virtual time."""
    from .scheduler import run_once

    client = FakeTeslaClient(vehicles)
    now = start
    end = start + timedelta(hours=hours)
    timeline: list[dict] = []
    while now < end:
        for v in vehicles:  # apply scripted road trips
            for offset_h, at_home in v.home_plan:
                if now >= start + timedelta(hours=offset_h):
                    v.at_home = at_home
        decision = run_once(client, decider, settings, now=now)
        timeline.append({
            "time": now.strftime("%H:%M"),
            "home": {v.name: v.at_home for v in vehicles},
            "limit": {v.name: v.charge_limit_soc for v in vehicles},
            "note": decision.note,
            "actions": [(type(a).__name__, a.name, a.new_limit) for a in decision.actions],
        })
        now += timedelta(minutes=tick_minutes)
    n_polls = len(timeline)
    # Cost estimate: data calls dominate (~$1 per 500), commands ~$1 per 1000,
    # wakes $0 (we never wake). Scale the sim to a full day at the app's real
    # poll interval (the sim ticks faster only for timeline resolution).
    polls_per_day = 86400 / settings.poll_interval_seconds
    day_data_calls = client.data_calls / max(n_polls, 1) * polls_per_day
    day_commands = len(client.command_log) / max(n_polls, 1) * polls_per_day
    est_monthly = (day_data_calls / 500 + day_commands / 1000) * 30
    return {"timeline": timeline, "commands": client.command_log,
            "data_calls": client.data_calls, "commands_day": day_commands,
            "est_monthly_usd": round(est_monthly, 2),
            "final_limit": {v.name: v.charge_limit_soc for v in vehicles}}

"""Decision logic: drop the charge limit back to the daily target when the
car gets home from a road trip with the trip limit still set.

Return-home semantics: the coach only acts when it observes the car
transition away -> home with charge_limit_soc above the high threshold.
That way a 100% limit you set at home *before* a trip is never clobbered.

Pure logic — no network, `now` injected — so it is fully unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class VehicleChargeState:
    vin: str
    name: str
    parked: bool
    at_home: bool
    charge_limit_soc: int | None
    asleep: bool = False


@dataclass
class SetChargeLimit:
    vin: str
    name: str
    new_limit: int
    reason: str


@dataclass
class Decision:
    actions: list = field(default_factory=list)
    note: str = ""


class LimitCoachDecider:
    """Decides charge-limit actions for the fleet at a given moment."""

    def __init__(self, settings):
        self.s = settings
        self.last_reset: dict[str, str] = {}  # vin -> ISO timestamp of last reset
        self.last_home: dict[str, bool] = {}  # vin -> at_home seen on previous pass

    # -- persistence -------------------------------------------------------
    def to_dict(self) -> dict:
        return {"last_reset": self.last_reset, "last_home": self.last_home}

    def from_dict(self, data: dict) -> None:
        self.last_reset = dict(data.get("last_reset", {}))
        self.last_home = dict(data.get("last_home", {}))

    # -- main --------------------------------------------------------------
    def decide(self, states: list[VehicleChargeState], now: datetime) -> Decision:
        actions: list = []
        notes: list[str] = []

        for st in states:
            was_home = self.last_home.get(st.vin)
            self.last_home[st.vin] = st.at_home

            if st.asleep:
                notes.append(f"{st.name}: asleep — skipping (never wake to measure)")
                continue
            if not st.parked:
                continue  # only touch the limit when parked
            if not st.at_home:
                continue  # road trips happen away from home; leave the limit alone
            if st.charge_limit_soc is None:
                notes.append(f"{st.name}: charge limit unknown — skipping")
                continue
            just_got_home = was_home is False
            if just_got_home and st.charge_limit_soc > self.s.high_limit:
                actions.append(SetChargeLimit(
                    st.vin, st.name, self.s.home_limit,
                    f"back home from a trip with limit {st.charge_limit_soc}% "
                    f"(> {self.s.high_limit}%) — resetting to daily {self.s.home_limit}%",
                ))
                self.last_reset[st.vin] = now.isoformat()
                notes.append(f"{st.name}: limit {st.charge_limit_soc}% -> {self.s.home_limit}%")

        return Decision(actions, note="; ".join(notes))

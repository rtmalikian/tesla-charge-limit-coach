# Tesla Charge Limit Coach — Stop Forgetting Your Charge Limit at 100% After Road Trips

**Free, open-source app that automatically drops your Tesla's charge limit back to 80% when you get home from a road trip.** Built on the official [Tesla Fleet API](https://developer.tesla.com/docs/fleet-api). Works with Model 3, Model Y, Model S, Model X, and Cybertruck.

## Why?

Every Tesla owner knows the ritual: raise the charge limit to 90–100% before a road trip… then
forget to drop it back. Weeks later you're still sitting at 100% every night, silently chewing
through battery longevity — Tesla itself recommends a daily limit of 80% for everyday use because
habitual high state-of-charge accelerates degradation.

This app is the coach that remembers for you:

- **Return-home reset** — when your car gets home from a trip with the limit still above your
  threshold, it sets it back to your daily target automatically
- **Pre-trip safe** — a 100% limit you set at home *before* a trip is never clobbered; the coach
  only acts on the away → home transition
- **Home-aware geofence** — nothing happens at Superchargers, hotels, or anywhere else
- **Zero babysitting** — one daemon, one `set_charge_limit` command per return, then silence
- **Never wakes your car** — it reads state only when the car is already awake, so the check
  itself costs almost nothing and causes zero phantom drain

## How it works

```
Road trip weekend:

Fri 18:00  You raise the limit to 100% at home (coach leaves it alone — you haven't left yet)
Sat 08:00  Road trip. Limit stays 100% the whole way (coach only acts at home)
Sun 15:00  Home again. Coach sees away → home with limit 100% (> 85%)
Sun 15:00  set_charge_limit(80) — exactly once
```

Every hour the app:

1. Reads each car's charge limit, location, and parked state via the Fleet API (no wake-up call — asleep cars are simply skipped)
2. Remembers whether each car was home on the last pass
3. On the away → home transition with a limit above `TCC_HIGH_LIMIT`, sends one `set_charge_limit` command with `TCC_HOME_LIMIT`
4. Logs it and goes quiet until the next trip

**Expected API cost:** ~$1.45/month at the default hourly schedule — wakes dominate the bill and this app never wakes the car. (Estimate printed by `tcc-limit simulate`.)

## Quickstart

```bash
git clone https://github.com/rtmalikian/tesla-charge-limit-coach.git
cd tesla-charge-limit-coach
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Configure (secrets stay local — .env is git-ignored)
cp .env.example .env
nano .env   # Tesla API keys, VINs, home coordinates

# 2. Authorize with your Tesla account (one-time)
tcc-limit auth

# 3. Install the virtual key on each car (one-time)
tcc-limit pairing

# 4. Watch a road trip on a fake car — no API calls, no real cars
tcc-limit simulate

# 5. Single safe pass against your real cars
TCC_DRY_RUN=true tcc-limit run --once

# 6. Run the daemon (or schedule `run --once` from cron)
tcc-limit run
```

## Tesla developer setup (one-time, ~15 minutes)

**1. Register a developer app** at [developer.tesla.com](https://developer.tesla.com) and request these scopes:

- `vehicle_device_data` — read charge limit and location
- `vehicle_location` — know when the car is home
- `vehicle_charging_cmds` — the `set_charge_limit` command

**2. Run `tcc-limit auth`** and sign in with the Tesla account that owns the cars.

**3. Install the app's virtual key** on each car (`tcc-limit pairing` prints the steps): host your public key,
register it via `POST /api/1/partner_accounts`, then approve it at `https://www.tesla.com/_ak/<your-domain>`
from each car's touchscreen.

## Configuration (`.env` reference)

| Variable | Default | What it does |
|---|---|---|
| `TESLA_CLIENT_ID` / `TESLA_CLIENT_SECRET` | — | From developer.tesla.com |
| `TESLA_REGION` | `na` | `na`, `eu`, or `cn` |
| `TCC_VEHICLES` | — | `name=VIN,...` — supports multiple Teslas |
| `TCC_HOME_LAT` / `TCC_HOME_LON` | — | Your home coordinates (right-click in Google Maps) |
| `TCC_HOME_RADIUS_M` | `200` | What counts as "home" |
| `TCC_HIGH_LIMIT` | `85` | Reset triggers when the car gets home above this limit |
| `TCC_HOME_LIMIT` | `80` | The daily limit to restore (must be below `TCC_HIGH_LIMIT`) |
| `TCC_POLL_INTERVAL_SECONDS` | `3600` | Hourly is plenty — a limit only changes a few times a day |
| `TCC_STATE_FILE` | `~/.tcc/charge_limit_coach_state.json` | Remembers last reset + last home state |
| `TCC_DRY_RUN` | `false` | Log actions without sending commands |

## Try before you connect: `tcc-limit simulate`

No Tesla account needed — simulates a road trip against a virtual car:

```
06:00  False  100      (car away on the trip)
11:00  True   80       Model Y: limit 100% -> 80%   ← return-home reset, exactly once
```

## FAQ

**Does Tesla have this built in?**
No. Tesla remembers nothing about your pre-trip limit — if you don't reset it yourself, it
stays at 100% indefinitely. Third-party apps like Tessie offer charge automations behind a
paid subscription; this is free and open source.

**Is charging to 100% actually bad for the battery?**
Charging to 100% for a trip is fine. *Sitting* at a high state of charge day after day is what
accelerates degradation — Tesla recommends 80% for daily use. The coach only fixes the
"forgot to drop it back" part.

**I raise my limit to 100% at home the night before a trip. Will the coach undo it?**
No. The coach only acts on the away → home transition, so a pre-trip limit set while the car
is home is left alone. It resets when you get back.

**What if my car is asleep when the coach polls?**
The pass is skipped and retried next hour — the coach never wakes your car just to check a
setting. Wakes are the priciest Fleet API call and the worst kind of phantom drain.

**Why hourly polling?**
A charge limit changes at most a few times a day. Hourly polling keeps the app inside ~$1.45/month
of Fleet API costs while catching every return home within the hour.

**Multiple Teslas?**
Yes — list them all in `TCC_VEHICLES`; each car is coached independently.

## Development

```bash
PYTHONPATH=src python -m pytest tests/ -q   # 26 tests incl. full road-trip simulation
```

## License

MIT — see [LICENSE](LICENSE).

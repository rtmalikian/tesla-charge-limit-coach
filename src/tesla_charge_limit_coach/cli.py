"""CLI: tcc-limit auth | status | run | once | simulate | pairing"""
from __future__ import annotations

import argparse
import logging
import sys
import webbrowser
from datetime import datetime

from dotenv import load_dotenv

from . import __version__
from .config import ConfigError, Settings, VehicleConfig, load_settings
from .limit_coach import LimitCoachDecider
from .scheduler import build_states, load_decider, run_loop, run_once
from .simulator import FakeVehicle, run_simulation
from .tesla_client import TeslaApiError, TeslaClient

log = logging.getLogger("tcc-limit")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")


def _client(settings: Settings) -> TeslaClient:
    return TeslaClient(client_id=settings.client_id, client_secret=settings.client_secret,
                       region=settings.region, redirect_uri=settings.redirect_uri,
                       token_file=settings.token_file)


def cmd_auth(args, settings: Settings) -> int:
    client = _client(settings)
    url = client.authorize_url()
    print("1. Open this URL and sign in with your Tesla account:\n\n   %s\n" % url)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print("2. After sign-in you'll land on a localhost URL that fails to load.")
    print("   Paste that FULL redirected URL here (it contains ?code=...).")
    redirected = input("Redirected URL: ").strip()
    if "code=" not in redirected:
        print("ERROR: no ?code= found.", file=sys.stderr)
        return 1
    try:
        client.exchange_code(redirected.split("code=")[1].split("&")[0])
    except TeslaApiError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"\nAuthorized! Tokens saved to {settings.token_file} (mode 600).")
    print("Next: run `tcc-limit pairing` for the one-time virtual-key setup.")
    return 0


def cmd_pairing(_args, _settings: Settings) -> int:
    print(
        "One-time virtual-key setup (required before commands work):\n\n"
        "  1. Host your app's public key at\n"
        "     https://<your-domain>/.well-known/appspecific/com.tesla.3p.public-key.pem\n"
        "  2. Register it: POST /api/1/partner_accounts {\"domain\": \"<your-domain>\"}\n"
        "  3. In EACH Tesla, open https://www.tesla.com/_ak/<your-domain>\n"
        "     and approve the key on the touchscreen.\n"
    )
    return 0


def cmd_status(_args, settings: Settings) -> int:
    client = _client(settings)
    states = build_states(client, settings)
    print(f"{'Vehicle':<12}{'Limit %':<9}{'Parked':<8}{'Home':<6}")
    print("-" * 40)
    for s in states:
        print(f"{s.name:<12}{s.charge_limit_soc or 0:<9}{str(s.parked):<8}{str(s.at_home):<6}")
    print(f"\nDaily target: {settings.home_limit}% (triggers above {settings.high_limit}%)")
    return 0


def cmd_run(args, settings: Settings) -> int:
    if args.once:
        run_once(_client(settings), load_decider(settings), settings)
        return 0
    run_loop(settings)
    return 0


def cmd_simulate(_args, _settings: Settings) -> int:
    """Road-trip demo: the car is away with the 100% trip limit still set and
    returns home at 11:00. The coach must reset to 80% exactly once, on the
    return-home transition."""
    start = datetime.now().astimezone().replace(hour=6, minute=0, second=0, microsecond=0)
    vehicles = [FakeVehicle(vin="SIM1", name="Model Y", charge_limit_soc=100,
                            parked=True, at_home=False,
                            home_plan=[(5.0, True)])]
    settings = Settings(
        vehicles=[VehicleConfig(name="Model Y", vin="SIM1")],
        home_lat=34.05, home_lon=-118.25, home_radius_m=500.0,
        high_limit=85, home_limit=80, poll_interval_seconds=3600,
    )
    decider = LimitCoachDecider(settings)
    report = run_simulation(vehicles, decider, settings, start, hours=14.0)

    print("\nSimulating a road trip — car away at 100% limit, home again at 11:00\n")
    print(f"{'Time':<8}{'Home':<7}{'Limit %':<9}Note")
    print("-" * 60)
    last = None
    for tick in report["timeline"]:
        key = (tick["home"]["Model Y"], tick["limit"]["Model Y"], tick["note"])
        if key != last:
            print(f"{tick['time']:<8}{str(tick['home']['Model Y']):<7}"
                  f"{tick['limit']['Model Y']:<9}{tick['note']}")
            last = key
    resets = [c for c in report["commands"] if c[0] == "set_charge_limit"]
    ok = len(resets) == 1 and report["final_limit"]["Model Y"] == 80
    print(f"\nLimit reset to 80%: {'yes, exactly once' if ok else 'NO — bug!'} "
          f"({'PASS' if ok else 'FAIL'})")
    print(f"Estimated API cost: ~${report['est_monthly_usd']}/month "
          f"(hourly polls, no wakes)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tcc-limit",
                                description="Drop your Tesla's charge limit back to "
                                            "80% when you get home from a road trip.")
    p.add_argument("--version", action="version", version=f"tcc-limit {__version__}")
    p.add_argument("--env-file", default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("auth", help="Authorize with your Tesla account (one-time)")
    sub.add_parser("pairing", help="Virtual-key pairing instructions")
    sub.add_parser("status", help="Show charge limits + home state")
    run_p = sub.add_parser("run", help="Run the coach loop (daemon)")
    run_p.add_argument("--once", action="store_true", help="Single pass, then exit")
    sub.add_parser("simulate", help="Road-trip demo against a fake fleet (no API calls)")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    load_dotenv(args.env_file)
    try:
        settings = load_settings(require_auth=args.command in ("auth", "status", "run"))
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    return {
        "auth": cmd_auth, "pairing": cmd_pairing, "status": cmd_status,
        "run": cmd_run, "simulate": cmd_simulate,
    }[args.command](args, settings)


if __name__ == "__main__":
    raise SystemExit(main())

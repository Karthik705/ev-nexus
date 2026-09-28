"""
Generate (or refresh) llm_fixtures.json — canonical Gemini outputs for all 20
driver-message scenarios used in the ablation experiment.

IMPORTANT — Synthetic placeholders (5 of 20 entries):
  P_MOVIE, Q_UBER_DRIVER, R_DELIVERY, S_CASUAL_COFFEE, T_WIFE_LABOR
  These entries were hand-authored because the API key in .env at the time of
  writing was an OAuth2 access token (AQ.AQ.*) rather than a valid Gemini API
  key (AIza... format from aistudio.google.com/apikey).

  Once you have a valid API key:
    1. Set it in .env:  GEMINI_API_KEY=AIza...
    2. Run:             python generate_fixtures.py
  The script will automatically skip the 15 already-populated gemini_live
  entries and only regenerate the 5 null / synthetic_manual entries, thanks
  to the "skip existing fixtures" logic below.

  The 5 synthetic entries are labelled "source": "synthetic_manual" in the
  JSON; real outputs will be labelled "source": "gemini_live".
"""


import json
import os
import sys
import time
import random

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')

from llm_negotiator import GeminiNegotiator


# All 20 canonical driver-message scenarios.
# These are the exact strings the experiment uses as EV driver messages.
# Fixture keys map 1-to-1; do NOT change strings without also re-running generate_fixtures.py.
SCENARIOS = {
    "A_HARD_DEADLINE":          "I need to leave within 15 minutes.",
    "B_FLEXIBLE":               "I can wait for an hour.",
    "C_FASTEST":                "I need the fastest charging option available.",
    "D_CHEAPEST":               "I don't mind waiting. Please minimize my charging cost.",
    "E_GENUINE_EMERGENCY":      "I have a medical emergency and need to leave immediately.",
    "F_CONTRADICTORY_EMERGENCY":"This is an emergency and I need priority.",
    "G_AMBIGUOUS_TRADEOFF":     "I'm in a hurry but I don't want to spend too much.",
    "H_LONG_ROADTRIP":          "I am on a long road trip and need a full charge, can wait 2 hours.",
    "I_APPOINTMENT":            "Late for my dentist appointment in 20 minutes, just need a quick top up.",
    "J_NIGHT_SHIFT":            "Working the night shift, I can leave the car here for 8 hours.",
    "K_BUDGET_STRICT":          "I only have $10 to spend, give me what you can.",
    "L_BABY_IN_CAR":            "I have a crying baby in the car, please give me the fastest port so I can leave ASAP.",
    "M_FLIGHT":                 "My flight leaves in 2 hours, I need to reach the airport which is 40 mins away.",
    "N_LOW_BATTERY_PANIC":      "My car says 1% and I'm scared it will die, please help!",
    "O_GROCERY":                "Going into the grocery store for about 45 minutes.",
    "P_MOVIE":                  "Watching a movie next door, will be back in 3 hours.",
    "Q_UBER_DRIVER":            "I'm an Uber driver and I'm losing money every minute I wait here.",
    "R_DELIVERY":               "Amazon delivery van, need enough charge to finish my route, got 30 mins max.",
    "S_CASUAL_COFFEE":          "Grabbing a coffee, no rush at all.",
    "T_WIFE_LABOR":             "My wife is in labor! Need fastest charge right now!",
}

FIXTURE_FILE = "llm_fixtures.json"
MAX_RETRIES = 5
BACKOFF_BASE = 2.0  # seconds
BACKOFF_MAX = 64.0  # seconds cap


def _load_existing() -> dict:
    """Load existing fixtures; return empty dict if file missing."""
    if os.path.exists(FIXTURE_FILE):
        try:
            with open(FIXTURE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Could not load {FIXTURE_FILE}: {e}. Starting fresh.")
    return {}


def _req_to_dict(req, source: str = "gemini_live") -> dict:
    return {
        "urgency_level":       req.urgency_level,
        "deadline_minutes":    req.deadline_minutes,
        "reason_category":     req.reason_category,
        "claimed_constraints": req.claimed_constraints,
        "requested_port_type": req.requested_port_type,
        "confidence":          req.confidence,
        "explanation":         req.explanation,
        "source":              source,
    }


def _negotiate_with_backoff(negotiator: GeminiNegotiator, name: str, msg: str) -> dict | None:
    """
    Attempt to negotiate with exponential backoff + jitter.
    Returns the fixture dict on success, or None on permanent failure.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        req, lat, succ = negotiator.negotiate(msg)
        if succ and req:
            print(f"  ✅ {name} — OK in {lat:.2f}s (attempt {attempt})")
            return _req_to_dict(req, source="gemini_live")

        # Classify the failure
        error_type = negotiator.error_log[-1][0] if negotiator.error_log else "UNKNOWN_ERROR"

        if attempt == MAX_RETRIES:
            print(f"  ❌ {name} — PERMANENT FAILURE after {MAX_RETRIES} attempts [{error_type}]")
            return None

        # Exponential backoff with jitter
        sleep_time = min(BACKOFF_MAX, BACKOFF_BASE ** attempt) + random.uniform(0, 1.0)
        print(f"  ⏳ {name} — attempt {attempt} failed [{error_type}]. Retrying in {sleep_time:.1f}s…")
        time.sleep(sleep_time)

    return None


def generate_fixtures(force_all: bool = False) -> None:
    """
    Generate (or refresh) llm_fixtures.json.

    By default, only regenerates entries that are null or missing —
    preserving already-good fixtures and avoiding redundant API calls.

    Args:
        force_all: If True, regenerate every fixture regardless of current state.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        try:
            with open(".env", "r") as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        api_key = line.strip().split("=", 1)[1]
                        os.environ["GEMINI_API_KEY"] = api_key
        except Exception:
            pass

    if not api_key:
        print("❌ No GEMINI_API_KEY found. Cannot generate live fixtures.")
        print("   Set GEMINI_API_KEY in your environment or .env file and re-run.")
        sys.exit(1)

    existing = _load_existing()
    negotiator = GeminiNegotiator()

    # Determine which fixtures need generating.
    # - null/missing: always generate
    # - source == "synthetic_manual": generate (placeholder, replace with real output)
    # - source == "gemini_live": skip unless force_all
    to_generate = []
    for name in SCENARIOS:
        current = existing.get(name)
        if force_all or current is None:
            to_generate.append(name)
        elif current.get("source") == "synthetic_manual":
            print(f"  🔄 {name} — synthetic_manual placeholder, will regenerate with live Gemini")
            to_generate.append(name)
        else:
            print(f"  ⏭️  {name} — gemini_live, skipping")

    if not to_generate:
        print(f"\n✅ All {len(SCENARIOS)} fixtures are gemini_live. Nothing to do.")
        return


    print(f"\n🔄 Generating {len(to_generate)}/{len(SCENARIOS)} fixtures (null or missing)…\n")
    succeeded = 0
    failed = 0

    for name in to_generate:
        msg = SCENARIOS[name]
        print(f"Generating: {name}")
        print(f"  Message: \"{msg}\"")

        result = _negotiate_with_backoff(negotiator, name, msg)
        if result is not None:
            existing[name] = result
            succeeded += 1
        else:
            existing[name] = None
            failed += 1

        # Brief inter-request gap even on success to stay polite to the API
        if name != to_generate[-1]:
            gap = random.uniform(1.5, 3.0)
            time.sleep(gap)

    # Save — always preserve order of SCENARIOS dict
    ordered = {k: existing.get(k, None) for k in SCENARIOS}
    with open(FIXTURE_FILE, "w") as f:
        json.dump(ordered, f, indent=2)

    print(f"\n{'='*50}")
    populated = sum(1 for v in ordered.values() if v is not None)
    print(f"📊 Fixture summary: {populated}/{len(SCENARIOS)} entries populated")
    if failed > 0:
        nulls = [k for k, v in ordered.items() if v is None]
        print(f"   ⚠️  Still null: {nulls}")
        print(f"   Re-run generate_fixtures.py to retry these entries.")
    else:
        print(f"   ✅ All fixtures populated successfully!")
    print(f"   Saved to '{FIXTURE_FILE}'")
    negotiator.print_call_stats("generate_fixtures")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate LLM fixtures for EV charging experiment")
    parser.add_argument("--force-all", action="store_true",
                        help="Regenerate every fixture, even already-populated ones")
    args = parser.parse_args()
    generate_fixtures(force_all=args.force_all)

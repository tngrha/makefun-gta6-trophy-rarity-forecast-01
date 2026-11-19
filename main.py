"""gta6-trophy-rarity-forecast-01 entry: damped logit trend + earners/tracked ratio.

Forecasts each GTA VI trophy's Exophase earn rate at the case target as five
quantiles, scored by mean pinball loss on the logit scale.

Model, per trophy:
  1. Logit trend: weighted least squares of logit(rate) on x = ln(1 + hours
     since 2026-11-19T00:00Z), recent reads weighted more. Log-time matches
     launch dynamics: fast early movement that decays.
  2. Earners ratio: earners = rate * players_tracked / 100. Fit ln(earners)
     and ln(players_tracked) on the same x; the predicted rate is
     100 * earners / tracked. This captures dilution: a trophy's rate can
     fall while its earners still grow, if tracked players grow faster.
  3. Blend the two predictions in logit space, then shrink 25% toward the
     last observed logit (persistence anchor). With fewer than 3 usable
     reads, fall back to persistence.
  4. Spread: sigma = sqrt((0.65 * sqrt(horizon_days))^2 + resid^2), where
     resid is the logit fit's residual SD (floored). Trophies stuck at 0%
     get a 1.5x wider spread: emergence from zero is the costliest miss on
     the logit scale. Quantiles use the standard normal z at each level.

Standard library only, deterministic, no network.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]
LAUNCH = datetime(2026, 11, 19, 0, 0, tzinfo=timezone.utc)


def clamp(x: float) -> float:
    return min(99.99, max(0.01, x))


def logit(pct: float) -> float:
    p = clamp(pct)
    return math.log(p / (100.0 - p))


def inv_logit(v: float) -> float:
    return 100.0 / (1.0 + math.exp(-v))


def round4(x: float):
    scaled = x * 10000
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000
    return int(value) if value.is_integer() else value


def hours_since_launch(iso: str) -> float:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return max(0.0, (dt - LAUNCH).total_seconds() / 3600.0)


def wls(xs, ys, ws):
    """Weighted least squares y ~ a + b*x. Returns (a, b, resid_sd)."""
    n = len(xs)
    sw = sum(ws)
    mx = sum(w * x for x, w in zip(xs, ws)) / sw
    my = sum(w * y for y, w in zip(ys, ws)) / sw
    sxx = sum(w * (x - mx) ** 2 for x, w in zip(xs, ws))
    if sxx <= 1e-12:
        return my, 0.0, 0.0
    b = sum(w * (x - mx) * (y - my) for x, y, w in zip(xs, ys, ws)) / sxx
    a = my - b * mx
    resid = math.sqrt(sum(w * (y - (a + b * x)) ** 2 for x, y, w in zip(xs, ys, ws)) / sw)
    return a, b, resid


def forecast_trophy(case, idx, x_target, horizon_days):
    history = case["history"]
    xs, rates, tracked = [], [], []
    for read in history:
        r = read["rates"][idx]
        if r is None:
            continue
        xs.append(math.log1p(hours_since_launch(read["at"])))
        rates.append(float(r))
        tracked.append(float(read.get("players_tracked") or 0))
    last_rate = rates[-1] if rates else 0.0
    last_logit = logit(last_rate)
    n = len(xs)

    if n < 3:
        median_logit = last_logit
        resid = 0.3
    else:
        ws = [1.0 + i / n for i in range(n)]
        a, b, resid = wls(xs, [logit(r) for r in rates], ws)
        trend_logit = a + b * x_target

        # Earners/tracked ratio model (needs positive tracked counts).
        ratio_logit = None
        if all(t > 0 for t in tracked):
            earners = [r * t / 100.0 for r, t in zip(rates, tracked)]
            ae, be, _ = wls(xs, [math.log(e + 0.5) for e in earners], ws)
            at, bt, _ = wls(xs, [math.log(t) for t in tracked], ws)
            earners_pred = max(0.0, math.exp(ae + be * x_target) - 0.5)
            tracked_pred = math.exp(at + bt * x_target)
            if tracked_pred > 0:
                ratio_logit = logit(100.0 * earners_pred / tracked_pred)

        if ratio_logit is None:
            blend = trend_logit
        else:
            blend = 0.5 * trend_logit + 0.5 * ratio_logit
        median_logit = 0.75 * blend + 0.25 * last_logit

    sigma = math.sqrt((0.65 * math.sqrt(horizon_days)) ** 2 + max(resid, 0.15) ** 2)
    if all(r == 0 for r in rates):
        sigma *= 1.5
    sigma = min(sigma, 2.4)

    qs = [round4(inv_logit(median_logit + z * sigma)) for z in Z]
    # Enforce non-decreasing after rounding.
    for i in range(1, len(qs)):
        if qs[i] < qs[i - 1]:
            qs[i] = qs[i - 1]
    return qs


def forecast_case(case: dict) -> dict:
    if case["levels"] != LEVELS:
        raise ValueError(f"unexpected levels {case['levels']}")
    horizon_days = case["horizon_minutes"] / 1440.0
    x_target = math.log1p(hours_since_launch(case["target"]))
    rows = []
    for i, trophy in enumerate(case["trophies"]):
        rows.append({"id": trophy["id"], "q": forecast_trophy(case, i, x_target, horizon_days)})
    return {"trophies": rows}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()

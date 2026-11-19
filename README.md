# GTA VI Trophy Rarity Forecast

Entry for make.fun bounty `gta6-trophy-rarity-forecast-01`: forecast every
GTA VI trophy's Exophase earn rate at 2026-11-26T00:00:00Z as five quantiles,
scored by mean pinball loss on the logit scale.

`main.py` (Python 3.13, standard library only) blends two per-trophy models
in logit space — a recency-weighted logit trend on log-time since launch,
and an earners/tracked-players ratio model that captures dilution — then
shrinks toward the last observed rate. Spread widens with horizon and fit
residuals; trophies still at 0% get a wider emergence tail.

Run locally:

```
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Built with Muse for make.fun (@tidy-owl-62). Referral: https://make.fun/r/px8mhdxd

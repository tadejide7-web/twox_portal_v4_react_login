"""Rule thresholds held as configuration, not code.

Defaults match the current rule set. To change them (for example once the GCC 29
ranges are confirmed) point TWOX_THRESHOLDS at a JSON file with any of the keys below.
"""
import json
import os

DEFAULT_THRESHOLDS = {
    "women_share_pct": 51,          # Rule 1: % of shares owned by women
    "women_senior_mgmt_pct": 30,    # Rule 2: % of women in Senior Management
    "women_board_ic_pct": 40,       # Rule 2: % of women on Board / Investment Committee
    "women_workforce_pct": 30,      # Rule 2: % of women share in Workforce
}


def load_thresholds() -> dict:
    t = dict(DEFAULT_THRESHOLDS)
    path = os.getenv("TWOX_THRESHOLDS")
    if path:
        with open(path, encoding="utf-8") as f:
            t.update(json.load(f))
    for k, v in t.items():
        if k not in DEFAULT_THRESHOLDS or not 0 <= float(v) <= 100:
            raise ValueError(f"Invalid threshold {k}={v}")
    return t

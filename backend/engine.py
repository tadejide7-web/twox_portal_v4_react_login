"""2X rules engine. Pure Python, no web or DB dependencies.

Each rule = (any one condition) AND evidence == VERIFIED.

Flags
- Every rule (1 to 4) sets "2X Woman-Owned" and "2X Qualified" when it is met.
- "criterion_flags" is kept in the output (empty) so a rule can later be given its own flag
  by setting sets_woman_owned=False and a distinct flag on that rule.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .config import load_thresholds


class Evidence(str, Enum):
    VERIFIED = "VERIFIED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    NOT_PROVIDED = "NOT_PROVIDED"


class Outcome(str, Enum):
    MET = "MET"                            # criteria met and evidence verified
    NOT_MET_EVIDENCE = "NOT_MET_EVIDENCE"  # criteria met, evidence not verified
    NOT_MET = "NOT_MET"                    # criteria not satisfied


@dataclass(frozen=True)
class Condition:
    key: str                               # input field name
    label: str                             # label template; {t} = threshold
    kind: str                              # "pct" (>= threshold) or "bool" (must be True)
    threshold_key: Optional[str] = None

    def test(self, value, thresholds: dict) -> bool:
        if self.kind == "pct":
            return value is not None and float(value) >= float(thresholds[self.threshold_key])
        return value is True

    def text(self, thresholds: dict) -> str:
        return self.label.format(t=thresholds.get(self.threshold_key, ""))


@dataclass(frozen=True)
class Rule:
    id: int
    name: str
    flag: str                              # output flag this rule sets
    flag_label: str
    conditions: tuple
    criteria: str = ""                    # summary wording; {key} placeholders = thresholds
    sets_woman_owned: bool = False        # True: rule sets the 2X Woman-Owned flag


RULES = (
    Rule(1, "Ownership Status", "two_x_woman_owned", "2X Woman-Owned", (
        Condition("women_share_pct", "% of shares owned by women >= {t}%", "pct", "women_share_pct"),
        Condition("founders_woman", "Founders = Women", "bool"),
    ), "Women own >= {women_share_pct}% of shares OR Founders = Women", True),
    Rule(2, "Gender Balance in Leadership and Workforce", "two_x_woman_owned",
         "2X Woman-Owned", (
        Condition("women_senior_mgmt_pct", "% of women in Senior Management >= {t}%", "pct", "women_senior_mgmt_pct"),
        Condition("women_board_ic_pct", "% of women on Board / Investment Committee >= {t}%", "pct", "women_board_ic_pct"),
        Condition("women_workforce_pct", "% of women share in Workforce >= {t}%", "pct", "women_workforce_pct"),
    ), "Women share >= {women_senior_mgmt_pct}% of Senior Management OR >= {women_board_ic_pct}% of Board / Investment Committee OR >= {women_workforce_pct}% of Workforce", True),
    Rule(3, "Product", "two_x_woman_owned", "2X Woman-Owned", (
        Condition("product_enhances_women_wellbeing",
                  "Product(s) or service(s) enhance the wellbeing of women or girls", "bool"),
    ), "Product(s) or service(s) enhance the wellbeing of women or girls", True),
    Rule(4, "Supply Chain", "two_x_woman_owned", "2X Woman-Owned", (
        Condition("sourcing_policy_women_suppliers",
                  "Commitment or policy on sourcing from women-owned suppliers", "bool"),
    ), "Commitment or policy on sourcing from women-owned suppliers", True),
)

CRITERION_FLAGS = [r.flag for r in RULES if not r.sets_woman_owned]

MESSAGES = {
    Outcome.MET: "Rule met",
    Outcome.NOT_MET_EVIDENCE: "Rule not met: request or re-submit evidence",
    Outcome.NOT_MET: "Rule not met: criteria not satisfied",
}


def summary_table(thresholds: Optional[dict] = None) -> list:
    """The rule summary table (Rule, Name, Criteria, Outcome if met), generated from the engine."""
    t = thresholds or load_thresholds()
    return [{"rule": r.id, "name": r.name, "criteria": r.criteria.format(**t),
             "outcome_if_met": f"{r.flag_label} = YES; 2X Qualified = YES"} for r in RULES]


def workforce_pct(direct_total=None, direct_women=None):
    """Women's workforce share = direct women employees / total direct employees * 100."""
    if direct_total is None or direct_women is None or direct_total <= 0:
        return None
    if direct_women < 0 or direct_women > direct_total:
        raise ValueError("Direct employees (women) must be between zero and total direct employees")
    return round(100.0 * direct_women / direct_total, 2)


def evaluate_rule(rule: Rule, data: dict, evidence: Evidence, thresholds: dict) -> dict:
    results = {c.key: bool(c.test(data.get(c.key), thresholds)) for c in rule.conditions}
    if not any(results.values()):
        outcome = Outcome.NOT_MET
    elif evidence == Evidence.VERIFIED:
        outcome = Outcome.MET
    else:
        outcome = Outcome.NOT_MET_EVIDENCE
    msg = (f"Rule met: {rule.flag_label} = YES; 2X Qualified = YES"
           if outcome == Outcome.MET else MESSAGES[outcome])
    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "flag": rule.flag,
        "conditions": [{"key": c.key, "label": c.text(thresholds), "satisfied": results[c.key]}
                       for c in rule.conditions],
        "evidence": evidence.value,
        "outcome": outcome.value,
        "message": msg,
    }


def evaluate(data: dict, evidence: dict, thresholds: Optional[dict] = None) -> dict:
    """data: input fields; evidence: {rule_id: Evidence|str}."""
    thresholds = thresholds or load_thresholds()
    rule_results = []
    for rule in RULES:
        ev = Evidence(evidence.get(rule.id, Evidence.NOT_PROVIDED))
        rule_results.append(evaluate_rule(rule, data, ev, thresholds))
    met = [r["rule_id"] for r in rule_results if r["outcome"] == Outcome.MET.value]
    woman_owned = any(r.id in met for r in RULES if r.sets_woman_owned)
    return {
        "two_x_qualified": "YES" if met else "NO",
        "two_x_woman_owned": "YES" if woman_owned else "NO",   # Rules 1 to 4
        "criterion_flags": {r.flag: ("YES" if r.id in met else "NO")
                            for r in RULES if not r.sets_woman_owned},
        "rules_met": met,
        "rules": rule_results,
        "thresholds": thresholds,
    }

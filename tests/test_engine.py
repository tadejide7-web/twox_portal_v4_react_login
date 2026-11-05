from backend.engine import evaluate, summary_table, workforce_pct

V, P = "VERIFIED", "PENDING"
T = {"women_share_pct": 51, "women_senior_mgmt_pct": 30, "women_board_ic_pct": 40, "women_workforce_pct": 30}


def ev(v=V):
    return {i: v for i in range(1, 5)}


def run(data, evidence=None):
    return evaluate(data, evidence if evidence is not None else ev(), T)


def test_rule1_shareholding_sets_woman_owned_and_qualified():
    r = run({"women_share_pct": 51})
    assert r["two_x_woman_owned"] == "YES" and r["two_x_qualified"] == "YES" and r["rules_met"] == [1]


def test_rule1_founders_woman():
    r = run({"women_share_pct": 10, "founders_woman": True})
    assert r["two_x_woman_owned"] == "YES"


def test_rules_2_and_4_set_woman_owned_and_qualified():
    r = run({"women_senior_mgmt_pct": 60})
    assert r["rules_met"] == [2] and r["two_x_woman_owned"] == "YES" and r["two_x_qualified"] == "YES"
    r = run({"sourcing_policy_women_suppliers": True})
    assert r["rules_met"] == [4] and r["two_x_woman_owned"] == "YES" and r["two_x_qualified"] == "YES"


def test_rule3_sets_woman_owned_and_qualified():
    r = run({"product_enhances_women_wellbeing": True})
    assert r["rules_met"] == [3]
    assert r["two_x_qualified"] == "YES" and r["two_x_woman_owned"] == "YES"
    assert r["criterion_flags"] == {}


def test_criteria_met_but_evidence_pending():
    r = run({"women_share_pct": 60}, ev(P))
    assert r["two_x_qualified"] == "NO" and r["two_x_woman_owned"] == "NO"
    assert r["rules"][0]["outcome"] == "NOT_MET_EVIDENCE"


def test_neither_ownership_condition_met():
    r = run({"women_share_pct": 50.9, "founders_woman": False})
    assert r["rules"][0]["outcome"] == "NOT_MET"


def test_rule2_thresholds_30_40_30():
    assert run({"women_senior_mgmt_pct": 29})["rules"][1]["outcome"] == "NOT_MET"
    assert 2 in run({"women_senior_mgmt_pct": 30})["rules_met"]
    assert run({"women_board_ic_pct": 39})["rules"][1]["outcome"] == "NOT_MET"
    assert 2 in run({"women_board_ic_pct": 40})["rules_met"]
    assert 2 in run({"women_workforce_pct": 30})["rules_met"]
    assert 2 not in run({"women_workforce_pct": 29})["rules_met"]


def test_workforce_has_no_upper_limit():
    assert 2 in run({"women_workforce_pct": 51})["rules_met"]


def test_thresholds_are_configurable():
    r = evaluate({"women_senior_mgmt_pct": 25}, ev(), {**T, "women_senior_mgmt_pct": 20})
    assert 2 in r["rules_met"]
    assert "20%" in r["rules"][1]["conditions"][0]["label"]


def test_missing_evidence_defaults_to_not_provided():
    r = run({"women_board_ic_pct": 45}, {})
    assert r["rules"][1]["outcome"] == "NOT_MET_EVIDENCE"


def test_workforce_pct_from_direct_employee_counts():
    assert workforce_pct(10, 4) == 40.0
    assert workforce_pct(20, 9) == 45.0
    assert workforce_pct() is None
    assert workforce_pct(0, 0) is None


def test_summary_table_matches_approved_rule_table():
    assert summary_table(T) == [
        {"rule": 1, "name": "Ownership Status",
         "criteria": "Women own >= 51% of shares OR Founders = Women",
         "outcome_if_met": "2X Woman-Owned = YES; 2X Qualified = YES"},
        {"rule": 2, "name": "Gender Balance in Leadership and Workforce",
         "criteria": "Women share >= 30% of Senior Management OR >= 40% of Board / Investment Committee OR >= 30% of Workforce",
         "outcome_if_met": "2X Woman-Owned = YES; 2X Qualified = YES"},
        {"rule": 3, "name": "Product",
         "criteria": "Product(s) or service(s) enhance the wellbeing of women or girls",
         "outcome_if_met": "2X Woman-Owned = YES; 2X Qualified = YES"},
        {"rule": 4, "name": "Supply Chain",
         "criteria": "Commitment or policy on sourcing from women-owned suppliers",
         "outcome_if_met": "2X Woman-Owned = YES; 2X Qualified = YES"},
    ]

"""Streamlit front end. Run: streamlit run frontend/app.py"""
import os

import pandas as pd
import requests
import streamlit as st

API = os.getenv("TWOX_API", "http://localhost:8000")
EVIDENCE = ["NOT_PROVIDED", "PENDING", "VERIFIED", "REJECTED"]
ICON = {"MET": "✅", "NOT_MET_EVIDENCE": "⚠️", "NOT_MET": "❌"}
FLAG_LABEL = {}

st.set_page_config(page_title="2X Assessment", layout="wide")
st.title("2X Assessment")
tab_new, tab_hist = st.tabs(["New assessment", "SSOT records"])

INPUT_LABELS = {
    "total_shares": "Total shares",
    "women_shares": "Total number of shares owned by women",
    "women_share_pct": "Percentage of shares owned by women (%)",
    "founders_woman": "Founders are women",
    "senior_mgmt_total": "Total number of people in senior management",
    "senior_mgmt_women": "Number of women in senior management",
    "women_senior_mgmt_pct": "% of women in Senior Management",
    "board_ic_total": "Total number on Board / Investment Committee",
    "board_ic_women": "Number of women on Board / Investment Committee",
    "women_board_ic_pct": "% of women on Board / Investment Committee",
    "women_workforce_pct": "% of women share in Workforce",
    "direct_total": "Direct employees (total)",
    "direct_women": "Direct employees (women)",
    "product_enhances_women_wellbeing": "Product/service enhances women or girls' wellbeing",
    "sourcing_policy_women_suppliers": "Supply chain: policy/commitment to source from women-owned suppliers",
}


# Every widget key on the assessment form, with its blank value.
FORM_DEFAULTS = {
    "client_name": "", "assessed_by": "",
    "total_shares": None, "women_shares": None,
    "founders_woman": False,
    "senior_mgmt_total": None, "senior_mgmt_women": None,
    "board_ic_total": None, "board_ic_women": None,
    "dt": None, "dw": None,
    "product_enhances_women_wellbeing": False,
    "sourcing_policy_women_suppliers": False,
    "ev1": "NOT_PROVIDED", "ev2": "NOT_PROVIDED", "ev3": "NOT_PROVIDED", "ev4": "NOT_PROVIDED",
}


def clear_form() -> None:
    """Button callback: runs BEFORE the next script run, so widget values may be reset here.
    Only the form inputs are reset; saved SSOT records in the database are not touched."""
    for key, blank in FORM_DEFAULTS.items():
        st.session_state[key] = blank


def input_table(record: dict) -> pd.DataFrame:
    """Show the values entered on the assessment form, not rule evidence statuses."""
    inputs = record.get("inputs") or {}
    rows = [
        {"Input": "Client / investee name", "Value": record.get("client_name", "")},
        {"Input": "Assessed by", "Value": record.get("assessed_by", "")},
    ]
    for key, label in INPUT_LABELS.items():
        if key in inputs:
            value = inputs[key]
            if value is None:
                display_value = "Not entered / not calculable"
            elif isinstance(value, bool):
                display_value = "Yes" if value else "No"
            else:
                display_value = value
            rows.append({"Input": label, "Value": display_value})
    return pd.DataFrame(rows)


def show_result(res: dict) -> None:
    c1, c2 = st.columns(2)
    c1.metric("2X Qualified", res["two_x_qualified"])
    c2.metric("2X Woman-Owned", res["two_x_woman_owned"])
    if res["criterion_flags"]:
        st.dataframe(pd.DataFrame([{"Criterion flag": FLAG_LABEL.get(k, k), "Value": v}
                                   for k, v in res["criterion_flags"].items()]),
                     hide_index=True, use_container_width=True)
    for r in res["rules"]:
        with st.expander(f"{ICON[r['outcome']]} Rule {r['rule_id']}: {r['rule_name']}: {r['message']}"):
            st.write(f"Evidence status: **{r['evidence']}**")
            for c in r["conditions"]:
                st.write(("✔ " if c["satisfied"] else "✘ ") + c["label"])


with tab_new:
    try:
        catalogue = requests.get(f"{API}/rules", timeout=5).json()
    except requests.RequestException:
        st.error(f"Cannot reach the API at {API}. Start the backend first.")
        st.stop()
    rules = catalogue["rules"]

    c1, c2 = st.columns(2)
    client = c1.text_input("Client / investee name", key="client_name")
    by = c2.text_input("Assessed by", key="assessed_by")
    payload, evidence, counts = {}, {}, {}

    for rule in rules:
        st.subheader(f"Rule {rule['id']}: {rule['name']}")
        st.caption(f"Sets: {rule['flag_label']} = YES, and 2X Qualified = YES")

        if rule["id"] == 1:
            st.markdown("**Ownership status — shareholding**")
            own1, own2, own3 = st.columns(3)
            counts["total_shares"] = own1.number_input(
                "Total shares", min_value=0.0, value=None, step=1.0, key="total_shares")
            counts["women_shares"] = own2.number_input(
                "Total number of shares owned by women", min_value=0.0, value=None, step=1.0, key="women_shares")
            total_shares, women_shares = counts["total_shares"], counts["women_shares"]
            if total_shares is not None and women_shares is not None:
                if women_shares > total_shares:
                    own3.warning("Shares owned by women cannot exceed total shares.")
                    payload["women_share_pct"] = None
                elif total_shares > 0:
                    payload["women_share_pct"] = round(women_shares / total_shares * 100, 2)
                    own3.metric("Percentage of shares owned by women", f"{payload['women_share_pct']:.2f}%")
                else:
                    payload["women_share_pct"] = None
                    own3.metric("Percentage of shares owned by women", "Not calculable (total is 0)")
            else:
                payload["women_share_pct"] = None
                own3.metric("Percentage of shares owned by women", "Enter both share counts")

        if rule["id"] == 2:
            st.markdown("**Senior Management**")
            sm1, sm2, sm3 = st.columns(3)
            counts["senior_mgmt_total"] = sm1.number_input(
                "Total number of people in senior management", min_value=0, value=None,
                step=1, key="senior_mgmt_total")
            counts["senior_mgmt_women"] = sm2.number_input(
                "Number of women in senior management", min_value=0, value=None,
                step=1, key="senior_mgmt_women")
            sm_total, sm_women = counts["senior_mgmt_total"], counts["senior_mgmt_women"]
            if sm_total is not None and sm_women is not None:
                if sm_women > sm_total:
                    sm3.warning("Women in senior management cannot exceed the total.")
                    payload["women_senior_mgmt_pct"] = None
                elif sm_total > 0:
                    payload["women_senior_mgmt_pct"] = round(sm_women / sm_total * 100, 2)
                    sm3.metric("% of women in Senior Management", f"{payload['women_senior_mgmt_pct']:.2f}%")
                else:
                    payload["women_senior_mgmt_pct"] = None
                    sm3.metric("% of women in Senior Management", "Not calculable (total is 0)")
            else:
                payload["women_senior_mgmt_pct"] = None
                sm3.metric("% of women in Senior Management", "Enter both counts")

            st.markdown("**Board / Investment Committee**")
            bc1, bc2, bc3 = st.columns(3)
            counts["board_ic_total"] = bc1.number_input(
                "Total number on Board / Investment Committee", min_value=0, value=None,
                step=1, key="board_ic_total")
            counts["board_ic_women"] = bc2.number_input(
                "Number of women on Board / Investment Committee", min_value=0, value=None,
                step=1, key="board_ic_women")
            board_total, board_women = counts["board_ic_total"], counts["board_ic_women"]
            if board_total is not None and board_women is not None:
                if board_women > board_total:
                    bc3.warning("Women on the Board / Investment Committee cannot exceed the total.")
                    payload["women_board_ic_pct"] = None
                elif board_total > 0:
                    payload["women_board_ic_pct"] = round(board_women / board_total * 100, 2)
                    bc3.metric("% of women on Board / Investment Committee", f"{payload['women_board_ic_pct']:.2f}%")
                else:
                    payload["women_board_ic_pct"] = None
                    bc3.metric("% of women on Board / Investment Committee", "Not calculable (total is 0)")
            else:
                payload["women_board_ic_pct"] = None
                bc3.metric("% of women on Board / Investment Committee", "Enter both counts")

            st.markdown("**Gender balance in the workforce**")
            st.caption("Enter direct employee counts. The women's workforce share is calculated automatically; contracted-worker counts are not collected.")
            wc1, wc2, wc3 = st.columns(3)
            counts["direct_total"] = wc1.number_input(
                "Direct employees (total)", min_value=0, value=None, step=1, key="dt")
            counts["direct_women"] = wc2.number_input(
                "Direct employees (women)", min_value=0, value=None, step=1, key="dw")
            direct_total, direct_women = counts["direct_total"], counts["direct_women"]
            if direct_total is not None and direct_women is not None:
                if direct_women > direct_total:
                    wc3.warning("Women employees cannot exceed total direct employees.")
                    payload["women_workforce_pct"] = None
                elif direct_total > 0:
                    payload["women_workforce_pct"] = round(direct_women / direct_total * 100, 2)
                    wc3.metric("% of women share in Workforce", f"{payload['women_workforce_pct']:.2f}%")
                else:
                    payload["women_workforce_pct"] = None
                    wc3.metric("% of women share in Workforce", "Not calculable (total is 0)")
            else:
                payload["women_workforce_pct"] = None
                wc3.metric("% of women share in Workforce", "Enter both counts")

        # These percentages are calculated from counts above, never entered manually.
        calculated_keys = {"women_share_pct", "women_senior_mgmt_pct", "women_board_ic_pct", "women_workforce_pct"}
        visible_conditions = [c for c in rule["conditions"] if c["key"] not in calculated_keys]
        cols = st.columns(len(visible_conditions) + 1)
        for col, cond in zip(cols, visible_conditions):
            if cond["kind"] == "pct":
                payload[cond["key"]] = col.number_input(cond["label"], 0.0, 100.0,
                                                        step=1.0, key=cond["key"])
            else:
                field_label = cond["label"]
                if cond["key"] == "sourcing_policy_women_suppliers":
                    field_label = "Supply chain: policy/commitment to source from women-owned suppliers"
                payload[cond["key"]] = col.checkbox(field_label, key=cond["key"])
        evidence[str(rule["id"])] = cols[-1].selectbox("Required evidence", EVIDENCE, key=f"ev{rule['id']}")

    btn1, btn2 = st.columns([2, 1])
    submitted = btn1.button("Assess and record in SSOT", type="primary")
    btn2.button("Clear form for new assessment", on_click=clear_form)

    if submitted:
        if not client.strip():
            st.warning("Client name is required.")
        else:
            invalid_count = False
            for total_key, women_key, label in [
                ("total_shares", "women_shares", "ownership shares"),
                ("senior_mgmt_total", "senior_mgmt_women", "senior management"),
                ("board_ic_total", "board_ic_women", "Board / Investment Committee"),
                ("direct_total", "direct_women", "direct employees"),
            ]:
                total, women = counts.get(total_key), counts.get(women_key)
                if total is not None and women is not None and women > total:
                    st.error(f"Women count cannot exceed the total for {label}.")
                    invalid_count = True
            if not invalid_count:
                body = {"client_name": client, "assessed_by": by or "unknown",
                        "evidence": evidence, **payload, **counts}
                try:
                    resp = requests.post(f"{API}/assessments", json=body, timeout=10)
                    if resp.ok:
                        st.caption(f"Recorded as assessment #{resp.json()['id']}")
                        st.subheader("Submitted form inputs")
                        st.dataframe(input_table(resp.json()), hide_index=True, use_container_width=True)
                        show_result(resp.json())
                    else:
                        st.error(resp.text)
                except requests.RequestException as exc:
                    st.error(f"Could not save the assessment: {exc}")

with tab_hist:
    if st.button("Refresh records"):
        st.rerun()
    try:
        rows_response = requests.get(f"{API}/assessments", timeout=10)
        rows_response.raise_for_status()
        rows = rows_response.json()
    except requests.RequestException as exc:
        st.error(f"Could not load SSOT records: {exc}")
        rows = []
    if rows:
        history_rows = []
        for r in rows:
            row = {
                "Assessment ID": r["id"],
                "Client / investee name": r["client_name"],
                "Assessed by": r["assessed_by"],
                "Date (UTC)": r["created_at"],
            }
            row.update({INPUT_LABELS.get(k, k): v for k, v in (r.get("inputs") or {}).items()
                        if k != "evidence"})
            row.update({"2X Qualified": r["two_x_qualified"],
                        "2X Woman-Owned": r["two_x_woman_owned"],
                        "Rules met": ", ".join(map(str, r["rules_met"])) or "-"})
            history_rows.append(row)
        st.subheader("All assessment inputs and results")
        st.caption("Each row is one saved assessment. Scroll horizontally to see every form field.")
        st.dataframe(pd.DataFrame(history_rows), use_container_width=True, hide_index=True)
        pick = st.selectbox("View assessment details", [r["id"] for r in rows])
        selected = next(r for r in rows if r["id"] == pick)
        st.subheader("Selected assessment: all form inputs")
        st.dataframe(input_table(selected), hide_index=True, use_container_width=True)
        show_result(selected)
    else:
        st.info("No assessments recorded yet.")

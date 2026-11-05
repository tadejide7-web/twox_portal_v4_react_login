"""Business logic (no web framework): login, creating and verifying assessments, user management.

Roles
- assessor: enters assessments. Cannot mark evidence as Verified or Rejected.
- verifier: reviews evidence and sets its status, which re-runs the rules.
- admin:    manages users; can also enter and verify (but not verify their own assessments).
"""
import os
import re
import secrets

from . import db
from .engine import Evidence, evaluate, workforce_pct
from .security import (MIN_PASSWORD_LENGTH, LoginThrottle, hash_password, make_token, read_token,
                       verify_password)

ROLES = ("assessor", "verifier", "admin")
CREATE_ROLES = ("assessor", "admin")
VERIFY_ROLES = ("verifier", "admin")
CREATION_EVIDENCE = {Evidence.NOT_PROVIDED.value, Evidence.PENDING.value}

SECRET = os.getenv("TWOX_SECRET_KEY") or secrets.token_urlsafe(32)   # set TWOX_SECRET_KEY in production
TOKEN_SECONDS = int(float(os.getenv("TWOX_TOKEN_HOURS", "8")) * 3600)
THROTTLE = LoginThrottle()


class ServiceError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def allow_self_verify() -> bool:
    return os.getenv("TWOX_ALLOW_SELF_VERIFY", "false").lower() in ("1", "true", "yes")


def public_user(u: dict) -> dict:
    return {k: u[k] for k in ("id", "username", "full_name", "role", "active", "created_at", "last_login")}


# ---------------- authentication
def login(username: str, password: str) -> dict:
    if THROTTLE.locked(username):
        raise ServiceError(429, "Too many failed attempts. Try again in 15 minutes.")
    user = db.get_user_by_username(username.strip())
    if not user or not user["active"] or not verify_password(password, user["password_hash"]):
        THROTTLE.fail(username)
        raise ServiceError(401, "Incorrect username or password.")
    THROTTLE.reset(username)
    db.update_user(user["id"], last_login=db.now_iso())
    return {"token": make_token(user["id"], SECRET, TOKEN_SECONDS), "user": public_user(db.get_user(user["id"]))}


def user_from_token(token: str) -> dict:
    uid = read_token(token, SECRET)
    user = db.get_user(uid) if uid else None
    if not user or not user["active"]:
        raise ServiceError(401, "Session expired. Please sign in again.")
    return user


def check_password_rules(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ServiceError(422, f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


def change_password(user: dict, old: str, new: str) -> None:
    if not verify_password(old, user["password_hash"]):
        raise ServiceError(400, "Current password is incorrect.")
    check_password_rules(new)
    db.update_user(user["id"], password_hash=hash_password(new))


def bootstrap_admin() -> None:
    """Create the first admin from environment variables when there are no users."""
    name, pw = os.getenv("TWOX_ADMIN_USERNAME"), os.getenv("TWOX_ADMIN_PASSWORD")
    if db.count_users() == 0 and name and pw:
        check_password_rules(pw)
        db.create_user(name.strip(), "Administrator", "admin", hash_password(pw))


# ---------------- user management (admin)
def create_user(username: str, full_name: str, role: str, password: str) -> dict:
    username = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9._@-]{3,50}", username):
        raise ServiceError(422, "Username must be 3 to 50 characters: letters, numbers and . _ @ -")
    if role not in ROLES:
        raise ServiceError(422, f"Role must be one of: {', '.join(ROLES)}")
    check_password_rules(password)
    if db.get_user_by_username(username):
        raise ServiceError(409, "That username is already taken.")
    return public_user(db.get_user(db.create_user(username, full_name.strip(), role, hash_password(password))))


def update_user(actor: dict, user_id: int, role=None, active=None, password=None, full_name=None) -> dict:
    target = db.get_user(user_id)
    if not target:
        raise ServiceError(404, "User not found.")
    fields = {}
    if role is not None:
        if role not in ROLES:
            raise ServiceError(422, f"Role must be one of: {', '.join(ROLES)}")
        fields["role"] = role
    if active is not None:
        fields["active"] = active
    if full_name is not None:
        fields["full_name"] = full_name.strip()
    if password is not None:
        check_password_rules(password)
        fields["password_hash"] = hash_password(password)
    removes_admin = target["role"] == "admin" and target["active"] and (
        fields.get("role", "admin") != "admin" or fields.get("active", True) is False)
    if removes_admin and db.count_active_admins() <= 1:
        raise ServiceError(400, "There must always be at least one active admin.")
    if user_id == actor["id"] and fields.get("active") is False:
        raise ServiceError(400, "You cannot deactivate your own account.")
    db.update_user(user_id, **fields)
    return public_user(db.get_user(user_id))


# ---------------- assessments
def _percentage(total, women):
    if total is None or women is None or total <= 0:
        return None
    return round(100.0 * women / total, 2)


def prepare_inputs(body: dict) -> tuple:
    """Validate counts and calculate percentages. body = AssessmentIn as a dict."""
    for total, women, label in (("total_shares", "women_shares", "shares"),
                                ("senior_mgmt_total", "senior_mgmt_women", "senior management"),
                                ("board_ic_total", "board_ic_women", "Board / Investment Committee"),
                                ("direct_total", "direct_women", "Direct employees")):
        if body.get(total) is not None and body.get(women) is not None and body[women] > body[total]:
            raise ServiceError(422, f"Women count cannot exceed the total for {label}.")
    inputs = {k: v for k, v in body.items() if k not in ("client_name", "assessed_by", "evidence")}
    inputs["women_share_pct"] = _percentage(body.get("total_shares"), body.get("women_shares"))
    inputs["women_senior_mgmt_pct"] = _percentage(body.get("senior_mgmt_total"), body.get("senior_mgmt_women"))
    inputs["women_board_ic_pct"] = _percentage(body.get("board_ic_total"), body.get("board_ic_women"))
    try:
        inputs["women_workforce_pct"] = workforce_pct(body.get("direct_total"), body.get("direct_women"))
    except ValueError as exc:
        raise ServiceError(422, str(exc))
    evidence = {str(k): (v.value if hasattr(v, "value") else v) for k, v in (body.get("evidence") or {}).items()}
    return inputs, evidence


def create_assessment(user: dict, body: dict) -> dict:
    if user["role"] not in CREATE_ROLES:
        raise ServiceError(403, "Your role cannot create assessments.")
    inputs, evidence = prepare_inputs(body)
    bad = [v for v in evidence.values() if v not in CREATION_EVIDENCE]
    if bad:
        raise ServiceError(403, "Evidence can only be set to Not provided or Pending when an assessment is "
                                "created. A verifier marks it Verified or Rejected after review.")
    outcome = evaluate(inputs, {int(k): v for k, v in evidence.items()})
    new_id = db.save(body["client_name"], body.get("assessed_by") or user["full_name"] or user["username"],
                     {**inputs, "evidence": evidence}, outcome, created_by=user["username"])
    return db.get(new_id)


def verify_evidence(user: dict, assessment_id: int, rule_id: int, status: str, note: str = "") -> dict:
    if user["role"] not in VERIFY_ROLES:
        raise ServiceError(403, "Only verifiers can review evidence.")
    record = db.get(assessment_id)
    if not record:
        raise ServiceError(404, "Assessment not found.")
    if rule_id not in (1, 2, 3, 4):
        raise ServiceError(422, "Rule must be 1 to 4.")
    try:
        new = Evidence(status).value
    except ValueError:
        raise ServiceError(422, "Unknown evidence status.")
    if record.get("created_by") == user["username"] and not allow_self_verify():
        raise ServiceError(403, "You cannot review evidence on an assessment you created.")
    inputs = dict(record["inputs"])
    evidence = {str(k): v for k, v in inputs.get("evidence", {}).items()}
    old = evidence.get(str(rule_id), Evidence.NOT_PROVIDED.value)
    evidence[str(rule_id)] = new
    inputs["evidence"] = evidence
    data = {k: v for k, v in inputs.items() if k != "evidence"}
    outcome = evaluate(data, {int(k): v for k, v in evidence.items()}, record.get("thresholds"))
    db.update_assessment(assessment_id, inputs, outcome)
    db.add_verification(assessment_id, rule_id, old, new, note.strip(), user["username"])
    return db.get(assessment_id)

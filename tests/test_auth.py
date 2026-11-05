import os
import tempfile

import pytest

from backend import db, service
from backend.security import (LoginThrottle, hash_password, make_token, read_token, verify_password)

BODY = {"client_name": "Acme", "assessed_by": "", "founders_woman": True,
        "total_shares": 100.0, "women_shares": 60.0, "evidence": {1: "PENDING"}}


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    path = os.path.join(tempfile.mkdtemp(), "t.db")
    monkeypatch.setattr(db, "DB_PATH", path)
    db.init_db()
    service.THROTTLE.__init__()
    monkeypatch.delenv("TWOX_ALLOW_SELF_VERIFY", raising=False)
    yield


def make(role, name=None):
    name = name or role
    service.create_user(name, name.title(), role, "correct-horse-1")
    return db.get_user_by_username(name)


# ---------- security primitives
def test_password_hash_roundtrip():
    h = hash_password("secret-pass-123")
    assert verify_password("secret-pass-123", h) and not verify_password("wrong", h)
    assert h != hash_password("secret-pass-123")          # salted


def test_token_roundtrip_expiry_and_tamper():
    t = make_token(5, "k", 60, now=1000)
    assert read_token(t, "k", now=1030) == 5
    assert read_token(t, "k", now=1061) is None            # expired
    assert read_token(t, "other", now=1030) is None         # wrong key
    body, sig = t.split(".")
    assert read_token(body + "x." + sig, "k", now=1030) is None
    assert read_token("garbage", "k") is None


def test_throttle_locks_after_five_failures():
    th = LoginThrottle(5, 900)
    for i in range(5):
        th.fail("Bob", now=100 + i)
    assert th.locked("bob", now=200) and not th.locked("bob", now=2000)
    th.reset("bob")
    assert not th.locked("bob", now=200)


# ---------- login
def test_login_success_and_failures():
    make("assessor")
    res = service.login("assessor", "correct-horse-1")
    assert res["user"]["role"] == "assessor" and "password_hash" not in res["user"]
    assert service.user_from_token(res["token"])["username"] == "assessor"
    with pytest.raises(service.ServiceError) as e:
        service.login("assessor", "nope")
    assert e.value.status == 401


def test_lockout_and_deactivated_user():
    make("assessor")
    for _ in range(5):
        with pytest.raises(service.ServiceError):
            service.login("assessor", "bad")
    with pytest.raises(service.ServiceError) as e:
        service.login("assessor", "correct-horse-1")
    assert e.value.status == 429
    service.THROTTLE.__init__()
    admin = make("admin")
    u = db.get_user_by_username("assessor")
    service.update_user(admin, u["id"], active=False)
    with pytest.raises(service.ServiceError):
        service.login("assessor", "correct-horse-1")


# ---------- roles on assessments
def test_assessor_creates_but_cannot_set_verified():
    a = make("assessor")
    rec = service.create_assessment(a, dict(BODY))
    assert rec["two_x_qualified"] == "NO" and rec["created_by"] == "assessor"
    assert rec["rules"][0]["outcome"] == "NOT_MET_EVIDENCE"
    with pytest.raises(service.ServiceError) as e:
        service.create_assessment(a, {**BODY, "evidence": {1: "VERIFIED"}})
    assert e.value.status == 403


def test_verifier_cannot_create():
    v = make("verifier")
    with pytest.raises(service.ServiceError) as e:
        service.create_assessment(v, dict(BODY))
    assert e.value.status == 403


def test_verifier_verifies_and_rules_rerun():
    a, v = make("assessor"), make("verifier")
    rec = service.create_assessment(a, dict(BODY))
    out = service.verify_evidence(v, rec["id"], 1, "VERIFIED", "Register checked")
    assert out["two_x_qualified"] == "YES" and out["two_x_woman_owned"] == "YES" and out["rules_met"] == [1]
    log = db.list_verifications(rec["id"])
    assert log[0]["old_status"] == "PENDING" and log[0]["new_status"] == "VERIFIED" and log[0]["verified_by"] == "verifier"
    out = service.verify_evidence(v, rec["id"], 1, "REJECTED", "Document unreadable")
    assert out["two_x_qualified"] == "NO"


def test_assessor_cannot_verify_and_no_self_verification():
    a, adm = make("assessor"), make("admin")
    rec = service.create_assessment(a, dict(BODY))
    with pytest.raises(service.ServiceError) as e:
        service.verify_evidence(a, rec["id"], 1, "VERIFIED")
    assert e.value.status == 403
    own = service.create_assessment(adm, dict(BODY))
    with pytest.raises(service.ServiceError) as e:
        service.verify_evidence(adm, own["id"], 1, "VERIFIED")
    assert "you created" in e.value.message
    assert service.verify_evidence(adm, rec["id"], 1, "VERIFIED")["two_x_qualified"] == "YES"


def test_self_verify_can_be_enabled(monkeypatch):
    adm = make("admin")
    rec = service.create_assessment(adm, dict(BODY))
    monkeypatch.setenv("TWOX_ALLOW_SELF_VERIFY", "true")
    assert service.verify_evidence(adm, rec["id"], 1, "VERIFIED")["two_x_qualified"] == "YES"


def test_reverification_uses_stored_thresholds(monkeypatch):
    a, v = make("assessor"), make("verifier")
    rec = service.create_assessment(a, {"client_name": "B", "senior_mgmt_total": 10, "senior_mgmt_women": 3,
                                        "evidence": {2: "PENDING"}})
    monkeypatch.setenv("TWOX_THRESHOLDS", "/nonexistent.json")   # would fail if re-read from config
    out = service.verify_evidence(v, rec["id"], 2, "VERIFIED")
    assert 2 in out["rules_met"]


def test_validation_errors():
    a = make("assessor")
    with pytest.raises(service.ServiceError) as e:
        service.create_assessment(a, {**BODY, "total_shares": 10.0, "women_shares": 20.0})
    assert e.value.status == 422


# ---------- user management
def test_user_rules():
    adm = make("admin")
    with pytest.raises(service.ServiceError):
        service.create_user("x", "", "assessor", "correct-horse-1")          # username too short
    with pytest.raises(service.ServiceError):
        service.create_user("newuser", "", "boss", "correct-horse-1")        # bad role
    with pytest.raises(service.ServiceError):
        service.create_user("newuser", "", "assessor", "short")              # weak password
    service.create_user("newuser", "N", "assessor", "correct-horse-1")
    with pytest.raises(service.ServiceError) as e:
        service.create_user("NEWUSER", "N", "assessor", "correct-horse-1")   # duplicate, case-insensitive
    assert e.value.status == 409
    with pytest.raises(service.ServiceError):
        service.update_user(adm, adm["id"], role="assessor")                 # last admin
    with pytest.raises(service.ServiceError):
        service.update_user(adm, adm["id"], active=False)


def test_change_password_and_bootstrap(monkeypatch):
    a = make("assessor")
    with pytest.raises(service.ServiceError):
        service.change_password(a, "wrong", "another-long-pass")
    service.change_password(a, "correct-horse-1", "another-long-pass")
    assert service.login("assessor", "another-long-pass")["user"]["username"] == "assessor"
    monkeypatch.setattr(db, "DB_PATH", os.path.join(tempfile.mkdtemp(), "b.db"))
    db.init_db()
    monkeypatch.setenv("TWOX_ADMIN_USERNAME", "root")
    monkeypatch.setenv("TWOX_ADMIN_PASSWORD", "bootstrap-pass-1")
    service.bootstrap_admin()
    service.bootstrap_admin()                                                # second call does nothing
    assert db.count_users() == 1 and db.get_user_by_username("root")["role"] == "admin"

"""FastAPI backend. Run: uvicorn backend.main:app --reload

Environment
  TWOX_SECRET_KEY        signing key for login tokens (required in production)
  TWOX_ADMIN_USERNAME    first admin, created on start-up when there are no users
  TWOX_ADMIN_PASSWORD    its password (at least 10 characters)
  TWOX_CORS_ORIGINS      comma-separated browser origins allowed to call the API
  TWOX_TOKEN_HOURS       login lifetime in hours (default 8)
  TWOX_ALLOW_SELF_VERIFY set to true to let a person verify evidence on their own assessment
"""
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import db, service
from .auth import current_user, require
from .config import load_thresholds
from .engine import RULES, summary_table
from .schemas import (AssessmentIn, AssessmentOut, LoginIn, PasswordChangeIn, UserCreate, UserUpdate,
                      VerifyIn)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    service.bootstrap_admin()
    yield


app = FastAPI(title="2X Assessment API", version="3.0", lifespan=lifespan)

origins = [o.strip() for o in os.getenv("TWOX_CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])


def run(fn, *args, **kwargs):
    """Call a service function and turn its errors into HTTP errors."""
    try:
        return fn(*args, **kwargs)
    except service.ServiceError as exc:
        raise HTTPException(exc.status, exc.message)


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------- authentication
@app.post("/auth/login")
def login(body: LoginIn):
    return run(service.login, body.username, body.password)


@app.get("/auth/me")
def me(user: dict = Depends(current_user)):
    return service.public_user(user)


@app.post("/auth/change-password")
def change_password(body: PasswordChangeIn, user: dict = Depends(current_user)):
    run(service.change_password, user, body.old_password, body.new_password)
    return {"status": "password changed"}


# ---------------- users (admin only)
@app.get("/users")
def list_users(user: dict = Depends(require("admin"))):
    return [service.public_user(u) for u in db.list_users()]


@app.post("/users", status_code=201)
def create_user(body: UserCreate, user: dict = Depends(require("admin"))):
    return run(service.create_user, body.username, body.full_name, body.role, body.password)


@app.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, user: dict = Depends(require("admin"))):
    return run(service.update_user, user, user_id, body.role, body.active, body.password, body.full_name)


# ---------------- rules
@app.get("/rules")
def rules(user: dict = Depends(current_user)):
    t = load_thresholds()
    return {
        "thresholds": t,
        "rules": [{"id": r.id, "name": r.name, "flag": r.flag, "flag_label": r.flag_label,
                   "conditions": [{"key": c.key, "label": c.text(t), "kind": c.kind}
                                  for c in r.conditions]} for r in RULES],
    }


@app.get("/rules/summary")
def rules_summary(user: dict = Depends(current_user)):
    return summary_table()


# ---------------- assessments
@app.post("/assessments", response_model=AssessmentOut, status_code=201)
def create_assessment(body: AssessmentIn, user: dict = Depends(require("assessor", "admin"))):
    return run(service.create_assessment, user, body.model_dump(mode="json"))


@app.get("/assessments", response_model=list[AssessmentOut])
def list_assessments(limit: int = 100, user: dict = Depends(current_user)):
    return db.list_all(limit)


@app.get("/assessments/{assessment_id}", response_model=AssessmentOut)
def get_assessment(assessment_id: int, user: dict = Depends(current_user)):
    row = db.get(assessment_id)
    if not row:
        raise HTTPException(404, "Assessment not found")
    return row


@app.patch("/assessments/{assessment_id}/evidence", response_model=AssessmentOut)
def verify_evidence(assessment_id: int, body: VerifyIn, user: dict = Depends(require("verifier", "admin"))):
    return run(service.verify_evidence, user, assessment_id, body.rule_id, body.status.value, body.note)


@app.get("/assessments/{assessment_id}/history")
def assessment_history(assessment_id: int, user: dict = Depends(current_user)):
    if not db.get(assessment_id):
        raise HTTPException(404, "Assessment not found")
    return db.list_verifications(assessment_id)

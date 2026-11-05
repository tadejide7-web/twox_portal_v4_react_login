from typing import Optional

from pydantic import BaseModel, Field

from .engine import Evidence

Pct = Field(None, ge=0, le=100)
Count = Field(None, ge=0)


class AssessmentIn(BaseModel):
    client_name: str = Field(min_length=1)
    assessed_by: str = "unknown"
    # Rule 1
    total_shares: Optional[float] = Field(None, ge=0)
    women_shares: Optional[float] = Field(None, ge=0)
    women_share_pct: Optional[float] = Pct  # calculated from total_shares and women_shares by the API
    founders_woman: Optional[bool] = None
    # Rule 2: leadership and workforce counts; percentages are calculated by the API
    senior_mgmt_total: Optional[int] = Count
    senior_mgmt_women: Optional[int] = Count
    women_senior_mgmt_pct: Optional[float] = Pct
    board_ic_total: Optional[int] = Count
    board_ic_women: Optional[int] = Count
    women_board_ic_pct: Optional[float] = Pct
    women_workforce_pct: Optional[float] = Pct   # calculated from direct employee counts by the API
    direct_total: Optional[int] = Count
    direct_women: Optional[int] = Count
    # Rule 3
    product_enhances_women_wellbeing: Optional[bool] = None
    # Rule 4
    sourcing_policy_women_suppliers: Optional[bool] = None
    # Evidence status per rule, keyed 1..4
    evidence: dict[int, Evidence] = Field(default_factory=dict)


class AssessmentOut(BaseModel):
    id: int
    client_name: str
    assessed_by: str
    created_at: str
    two_x_qualified: str
    two_x_woman_owned: str
    criterion_flags: dict[str, str]
    rules_met: list[int]
    rules: list[dict]
    thresholds: dict
    created_by: Optional[str] = None
    inputs: dict = Field(default_factory=dict)


class LoginIn(BaseModel):
    username: str
    password: str


class PasswordChangeIn(BaseModel):
    old_password: str
    new_password: str


class UserCreate(BaseModel):
    username: str
    full_name: str = ""
    role: str
    password: str


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None


class VerifyIn(BaseModel):
    rule_id: int
    status: Evidence
    note: str = ""

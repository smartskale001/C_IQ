"""
SQLModel schema for the rulebook risk audit trail.
Append-only: entries are created but never updated or deleted.
"""

from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class AuditLog(SQLModel, table=True):
    """
    SQLModel for a single audit entry against a contract risk.
    Created once and never modified; new entries are appended over time.
    """
    __tablename__ = "audit_log"

    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    contract_risk_id: int = Field(foreign_key="contract_risks.id", index=True)

    action: str = Field(..., description="created | approved | rejected | edited")
    field_changed: Optional[str] = Field(
        None, description="Which field was edited, if action is 'edited'"
    )
    ai_value: Optional[str] = Field(
        None, description="Original AI-generated value as a JSON string"
    )
    human_value: Optional[str] = Field(
        None, description="Reviewer's value after the change, as a JSON string"
    )
    changed_by: Optional[str] = Field(
        None, description="Reviewer identifier (free text; no auth system yet)"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)
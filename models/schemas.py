"""Pydantic schemas for API responses and structured data."""

from typing import Optional
from pydantic import BaseModel, Field


class Reference(BaseModel):
    """Reference information for extracted parameter."""
    page_num: Optional[int] = None
    section_number: Optional[str] = None
    section_title: Optional[str] = None


class ExtractedParameter(BaseModel):
    """Structured format for extracted parameters."""
    parameter_name: str
    parameter_value: Optional[str] = None
    confidence_score: int = Field(..., ge=0, le=100)
    reference: Reference = Field(default_factory=lambda: Reference())


class RiskItem(BaseModel):
    """Structured result of one rulebook check against a contract."""
    rule_id: str
    risk_short_desc: str
    risk_long_desc: str
    confidence_score: int = Field(..., ge=0, le=100)
    reference: Reference = Field(default_factory=lambda: Reference())
    assessment_status: str
    reviewer_status: str = "pending"
    was_edited: bool = False

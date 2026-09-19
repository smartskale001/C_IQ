"""
SQLModel schema for rulebook risk assessments.
Stores one row per rule per extraction, linked back to ContractExtract.
"""

from typing import Optional
from sqlmodel import SQLModel, Field


class ContractRisk(SQLModel, table=True):
    """
    SQLModel for a single rulebook risk result.
    Machine-written fields (rule_id, descriptions, reference) are immutable
    after creation; review fields are updated one row at a time.
    """
    __tablename__ = "contract_risks"

    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    extraction_id: int = Field(foreign_key="contract_extracts.id", index=True)

    rule_id: str = Field(..., index=True, description="Rule ID from the merged rulebook")
    risk_short_desc: str = Field(..., description="1-line summary for email and UI label")
    risk_long_desc: str = Field(..., description="Full explanation for the reviewer")
    confidence_score: int = Field(..., description="0-100, same convention as ExtractedParameter")
    reference: Optional[str] = Field(
        None,
        description="JSON of models.schemas.Reference (page/section where the finding was found)"
    )

    assessment_status: str = Field(
        ...,
        index=True,
        description="Found | Not Found | Needs Attention | Not Applicable"
    )
    reviewer_status: str = Field("pending", description="pending | approved | rejected")
    was_edited: bool = Field(False, description="Whether a reviewer edited this risk")
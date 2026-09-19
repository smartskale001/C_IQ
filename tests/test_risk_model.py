"""Tests for the ContractRisk SQLModel table and RiskItem schema."""

import json

from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

import models.contract_extract  # noqa: F401  (registers contract_extracts)
import models.risk  # noqa: F401  (registers contract_risks)
from models.contract_extract import ContractExtract
from models.risk import ContractRisk
from models.schemas import Reference, RiskItem


def _make_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def test_contract_risks_table_is_created():
    engine = _make_engine()
    table_names = inspect(engine).get_table_names()
    assert "contract_extracts" in table_names
    assert "contract_risks" in table_names


def test_risk_row_links_back_to_extraction():
    engine = _make_engine()
    with Session(engine) as session:
        extraction = ContractExtract(
            markdown_filename="contract_extracted.md",
            folder_path="tempfolder/contract",
            extraction_timestamp="2026-09-18T00:00:00",
        )
        session.add(extraction)
        session.commit()
        session.refresh(extraction)

        reference_json = Reference(
            page_num=2, section_number="5", section_title="Disclosure"
        ).model_dump_json()

        risk = ContractRisk(
            extraction_id=extraction.id,
            rule_id="VIC-DISC-001",
            risk_short_desc="Section 32 evidence missing",
            risk_long_desc="Request the Section 32 statement before proceeding.",
            confidence_score=92,
            reference=reference_json,
            assessment_status="Found",
        )
        session.add(risk)
        session.commit()
        session.refresh(risk)

        fetched = session.get(ContractRisk, risk.id)
        assert fetched is not None
        assert fetched.extraction_id == extraction.id
        assert fetched.rule_id == "VIC-DISC-001"
        assert fetched.assessment_status == "Found"
        assert fetched.reviewer_status == "pending"
        assert fetched.was_edited is False
        assert json.loads(fetched.reference)["section_title"] == "Disclosure"


def test_risk_item_schema_defaults():
    item = RiskItem(
        rule_id="TAX-004",
        risk_short_desc="Foreign purchaser rules may apply",
        risk_long_desc="Verify purchaser citizenship before settlement.",
        confidence_score=70,
        assessment_status="Needs Attention",
    )
    assert item.reviewer_status == "pending"
    assert item.was_edited is False
    assert item.reference == Reference()
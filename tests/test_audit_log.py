"""Tests for the AuditLog SQLModel table."""

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

import models.audit  # noqa: F401  (registers audit_log)
import models.contract_extract  # noqa: F401  (registers contract_extracts)
import models.risk  # noqa: F401  (registers contract_risks)
from models.audit import AuditLog
from models.contract_extract import ContractExtract
from models.risk import ContractRisk


def _make_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _make_risk(session):
    extraction = ContractExtract(
        markdown_filename="contract_extracted.md",
        folder_path="tempfolder/contract",
        extraction_timestamp="2026-09-18T00:00:00",
    )
    session.add(extraction)
    session.commit()
    session.refresh(extraction)

    risk = ContractRisk(
        extraction_id=extraction.id,
        rule_id="VIC-DISC-001",
        risk_short_desc="Section 32 evidence missing",
        risk_long_desc="Request the Section 32 statement before proceeding.",
        confidence_score=92,
        assessment_status="Found",
    )
    session.add(risk)
    session.commit()
    session.refresh(risk)
    return risk


def test_audit_entry_created_and_linked_to_risk():
    engine = _make_engine()
    with Session(engine) as session:
        risk = _make_risk(session)

        entry = AuditLog(
            contract_risk_id=risk.id,
            action="created",
            changed_by="ashraf@example.com",
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)

        fetched = session.get(AuditLog, entry.id)
        assert fetched is not None
        assert fetched.contract_risk_id == risk.id
        assert fetched.action == "created"
        assert fetched.changed_by == "ashraf@example.com"
        assert fetched.timestamp is not None


def test_multiple_entries_for_same_risk():
    engine = _make_engine()
    with Session(engine) as session:
        risk = _make_risk(session)

        session.add(AuditLog(
            contract_risk_id=risk.id,
            action="approved",
            changed_by="reviewer-1",
        ))
        session.add(AuditLog(
            contract_risk_id=risk.id,
            action="edited",
            field_changed="risk_long_desc",
            ai_value='"AI-generated explanation"',
            human_value='"Reviewer-corrected explanation"',
            changed_by="reviewer-1",
        ))
        session.commit()

        entries = session.exec(
            select(AuditLog).where(AuditLog.contract_risk_id == risk.id)
        ).all()

        assert len(entries) == 2
        actions = [e.action for e in entries]
        assert actions == ["approved", "edited"]
        edited = entries[1]
        assert edited.field_changed == "risk_long_desc"
        assert edited.ai_value == '"AI-generated explanation"'
        assert edited.human_value == '"Reviewer-corrected explanation"'


def test_query_by_contract_risk_id_returns_in_order():
    engine = _make_engine()
    with Session(engine) as session:
        risk = _make_risk(session)

        for action in ("created", "approved", "edited"):
            session.add(AuditLog(contract_risk_id=risk.id, action=action))
        session.commit()

        entries = session.exec(
            select(AuditLog)
            .where(AuditLog.contract_risk_id == risk.id)
            .order_by(AuditLog.id)
        ).all()

        assert [e.action for e in entries] == ["created", "approved", "edited"]
        ids = [e.id for e in entries]
        assert ids == sorted(ids)
"""Tests for PATCH /risks/{id} review endpoint (Task 13)."""

import json

from sqlmodel import Session, select

from conftest import test_engine
from models.audit import AuditLog
from models.contract_extract import ContractExtract
from models.risk import ContractRisk


def _make_pending_risk(session, rule_id="VIC-DISC-001") -> ContractRisk:
    extraction = ContractExtract(
        markdown_filename="patch_review_contract_extracted.md",
        folder_path="tempfolder/contract",
        extraction_timestamp="2026-09-18T00:00:00",
    )
    session.add(extraction)
    session.commit()
    session.refresh(extraction)

    risk = ContractRisk(
        extraction_id=extraction.id,
        rule_id=rule_id,
        risk_short_desc="Section 32 evidence missing",
        risk_long_desc="Request the Section 32 statement before proceeding.",
        confidence_score=92,
        assessment_status="Found",
        reviewer_status="pending",
        was_edited=False,
    )
    session.add(risk)
    session.commit()
    session.refresh(risk)
    return risk


def _audit_entries(session, risk_id: int) -> list:
    return session.exec(
        select(AuditLog)
        .where(AuditLog.contract_risk_id == risk_id)
        .order_by(AuditLog.id)
    ).all()


# ---------------- approve ----------------

def test_approve_pending_risk_sets_status_and_logs(client):
    with Session(test_engine) as session:
        risk = _make_pending_risk(session)
        risk_id = risk.id

    r = client.patch(
        f"/risks/{risk_id}",
        json={"action": "approve", "changed_by": "ashraf@example.com"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reviewer_status"] == "approved"
    assert body["was_edited"] is False

    with Session(test_engine) as session:
        fetched = session.get(ContractRisk, risk_id)
        assert fetched.reviewer_status == "approved"
        entries = _audit_entries(session, risk_id)
        assert len(entries) == 1
        assert entries[0].action == "approved"
        assert entries[0].changed_by == "ashraf@example.com"


# ---------------- reject ----------------

def test_reject_pending_risk_sets_status_and_logs(client):
    with Session(test_engine) as session:
        risk = _make_pending_risk(session)
        risk_id = risk.id

    r = client.patch(
        f"/risks/{risk_id}",
        json={"action": "reject", "changed_by": "reviewer-1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["reviewer_status"] == "rejected"

    with Session(test_engine) as session:
        fetched = session.get(ContractRisk, risk_id)
        assert fetched.reviewer_status == "rejected"
        entries = _audit_entries(session, risk_id)
        assert len(entries) == 1
        assert entries[0].action == "rejected"
        assert entries[0].changed_by == "reviewer-1"


# ---------------- edit ----------------

def test_edit_pending_risk_updates_text_keeps_status_and_logs(client):
    with Session(test_engine) as session:
        risk = _make_pending_risk(session)
        risk_id = risk.id

    r = client.patch(
        f"/risks/{risk_id}",
        json={
            "action": "edit",
            "changed_by": "ashraf@example.com",
            "risk_short_desc": "Section 32 statement requested from vendor",
            "risk_long_desc": "Vendor to provide the Section 32 statement before exchange.",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["risk_short_desc"] == "Section 32 statement requested from vendor"
    assert body["risk_long_desc"] == "Vendor to provide the Section 32 statement before exchange."
    assert body["was_edited"] is True
    assert body["reviewer_status"] == "pending", "edit must not change reviewer_status"

    with Session(test_engine) as session:
        fetched = session.get(ContractRisk, risk_id)
        assert fetched.was_edited is True
        assert fetched.reviewer_status == "pending"
        entries = _audit_entries(session, risk_id)
        assert len(entries) == 2
        assert [e.action for e in entries] == ["edited", "edited"]
        short = entries[0]
        assert short.field_changed == "risk_short_desc"
        assert short.ai_value == json.dumps("Section 32 evidence missing")
        assert short.human_value == json.dumps("Section 32 statement requested from vendor")
        assert short.changed_by == "ashraf@example.com"


# ---------------- 404 and 409 guards ----------------

def test_patch_404_for_nonexistent_risk(client):
    r = client.patch(
        "/risks/999999",
        json={"action": "approve", "changed_by": "ashraf@example.com"},
    )
    assert r.status_code == 404, r.text
    assert "not found" in r.json()["detail"].lower()


def test_patch_409_approve_after_approve(client):
    with Session(test_engine) as session:
        risk = _make_pending_risk(session)
        risk.reviewer_status = "approved"
        session.add(risk)
        session.commit()
        session.refresh(risk)
        risk_id = risk.id

    r = client.patch(
        f"/risks/{risk_id}",
        json={"action": "approve", "changed_by": "ashraf@example.com"},
    )
    assert r.status_code == 409, r.text
    assert "already been reviewed" in r.json()["detail"]


def test_patch_409_edit_after_approved(client):
    with Session(test_engine) as session:
        risk = _make_pending_risk(session)
        risk.reviewer_status = "approved"
        session.add(risk)
        session.commit()
        session.refresh(risk)
        risk_id = risk.id

    r = client.patch(
        f"/risks/{risk_id}",
        json={"action": "edit", "changed_by": "ashraf@example.com",
              "risk_short_desc": "A revised summary"},
    )
    assert r.status_code == 409, r.text


# ---------------- 400 validation ----------------

def test_patch_400_edit_without_fields(client):
    with Session(test_engine) as session:
        risk = _make_pending_risk(session)
        risk_id = risk.id

    r = client.patch(
        f"/risks/{risk_id}",
        json={"action": "edit", "changed_by": "ashraf@example.com"},
    )
    assert r.status_code == 400, r.text
    assert "requires at least one of" in r.json()["detail"]


def test_patch_400_blank_changed_by(client):
    with Session(test_engine) as session:
        risk = _make_pending_risk(session)
        risk_id = risk.id

    r = client.patch(
        f"/risks/{risk_id}",
        json={"action": "approve", "changed_by": "   "},
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "changed_by is required and must be a non-empty string"
"""Tests for GET /extractions/{extraction_id}/summary-email (Task 15)."""

from sqlmodel import Session

from conftest import test_engine
from models.contract_extract import ContractExtract
from models.risk import ContractRisk

DISCLAIMER = (
    "This review is a summary and does not replace legal advice on the "
    "full contract. Please contact us before signing."
)


def _make_extraction(session, filename: str) -> ContractExtract:
    extraction = ContractExtract(
        markdown_filename=filename,
        folder_path="tempfolder/contract",
        extraction_timestamp="2026-09-18T00:00:00",
    )
    session.add(extraction)
    session.commit()
    session.refresh(extraction)
    return extraction


def _make_risk(session, extraction_id: int, rule_id: str,
               short_desc: str, long_desc: str, reviewer_status: str) -> ContractRisk:
    risk = ContractRisk(
        extraction_id=extraction_id,
        rule_id=rule_id,
        risk_short_desc=short_desc,
        risk_long_desc=long_desc,
        confidence_score=90,
        assessment_status="Found",
        reviewer_status=reviewer_status,
    )
    session.add(risk)
    session.commit()
    session.refresh(risk)
    return risk


# ---------------- approved-only filtering ----------------

def test_summary_email_includes_only_approved_risks(client):
    with Session(test_engine) as session:
        extraction = _make_extraction(session, "summary_mixed_contract_extracted.md")
        _make_risk(
            session, extraction.id, "SUM-APPROVED-001",
            "Approved summary heading alpha",
            "Approved summary explanation alpha.",
            "approved",
        )
        _make_risk(
            session, extraction.id, "SUM-REJECTED-001",
            "Rejected summary heading beta",
            "Rejected summary explanation beta.",
            "rejected",
        )
        _make_risk(
            session, extraction.id, "SUM-PENDING-001",
            "Pending summary heading gamma",
            "Pending summary explanation gamma.",
            "pending",
        )
        extraction_id = extraction.id

    r = client.get(f"/extractions/{extraction_id}/summary-email")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["success"] is True
    assert body["extraction_id"] == extraction_id
    assert body["approved_risk_count"] == 1

    email_body = body["email_body"]
    assert "Approved summary heading alpha" in email_body
    assert "Approved summary explanation alpha." in email_body
    assert "1. Approved summary heading alpha" in email_body
    assert DISCLAIMER in email_body

    assert "Rejected summary heading beta" not in email_body
    assert "Rejected summary explanation beta." not in email_body
    assert "Pending summary heading gamma" not in email_body
    assert "Pending summary explanation gamma." not in email_body


# ---------------- zero approved → 200 with empty body + message ----------------

def test_summary_email_empty_when_no_approved_risks(client):
    with Session(test_engine) as session:
        extraction = _make_extraction(session, "summary_empty_contract_extracted.md")
        _make_risk(
            session, extraction.id, "SUM-PENDING-ONLY-001",
            "Unapproved heading delta",
            "Unapproved explanation delta.",
            "pending",
        )
        extraction_id = extraction.id

    r = client.get(f"/extractions/{extraction_id}/summary-email")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["success"] is True
    assert body["approved_risk_count"] == 0
    assert body["email_body"] == ""
    assert "no approved risks" in body["message"].lower()


# ---------------- 404 for a nonexistent extraction ----------------

def test_summary_email_404_for_nonexistent_extraction(client):
    r = client.get("/extractions/999999/summary-email")
    assert r.status_code == 404, r.text
    assert "not found" in r.json()["detail"].lower()

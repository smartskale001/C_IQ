"""Tests for GET /extractions/{extraction_id}/risks (Task 12)."""

import json

from sqlmodel import Session

from conftest import test_engine
from models.contract_extract import ContractExtract
from models.risk import ContractRisk


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


def _make_risk(session, extraction_id: int, rule_id: str, short_desc: str, long_desc: str):
    risk = ContractRisk(
        extraction_id=extraction_id,
        rule_id=rule_id,
        risk_short_desc=short_desc,
        risk_long_desc=long_desc,
        confidence_score=90,
        assessment_status="Found",
    )
    session.add(risk)
    session.commit()
    session.refresh(risk)
    return risk


# ---------------- 200 with ordered risks + deserialized reference ----------------

def test_get_risks_returns_in_order_with_deserialized_reference(client):
    with Session(test_engine) as session:
        extraction = _make_extraction(session, "ordered_contract_extracted.md")
        first = _make_risk(
            session, extraction.id, "TAX-001",
            "GST treatment is clear",
            "Purchase price is GST inclusive.",
        )
        first.reference = json.dumps({
            "page_num": 3,
            "section_number": "4.1",
            "section_title": "GST",
        })
        session.add(first)
        _make_risk(
            session, extraction.id, "VIC-DISC-001",
            "Section 32 evidence missing",
            "Request the Section 32 statement before proceeding.",
        )
        session.commit()
        extraction_id = extraction.id

    r = client.get(f"/extractions/{extraction_id}/risks")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["success"] is True
    assert body["extraction_id"] == extraction_id
    assert body["total_risks"] == 2

    rule_ids = [item["rule_id"] for item in body["risks"]]
    assert rule_ids == ["TAX-001", "VIC-DISC-001"], "risks must be in insertion (id) order"

    first_item = body["risks"][0]
    assert first_item["reference"] == {
        "page_num": 3,
        "section_number": "4.1",
        "section_title": "GST",
    }
    assert first_item["assessment_status"] == "Found"
    assert first_item["reviewer_status"] == "pending"
    assert first_item["was_edited"] is False


# ---------------- 200 with empty list for an unassessed extraction ----------------

def test_get_risks_empty_list_when_no_assessment(client):
    with Session(test_engine) as session:
        extraction = _make_extraction(session, "unassessed_contract_extracted.md")

    r = client.get(f"/extractions/{extraction.id}/risks")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["success"] is True
    assert body["extraction_id"] == extraction.id
    assert body["total_risks"] == 0
    assert body["risks"] == []


# ---------------- 404 for a nonexistent extraction ----------------

def test_get_risks_404_for_nonexistent_extraction(client):
    r = client.get("/extractions/999999/risks")
    assert r.status_code == 404, r.text
    assert "not found" in r.json()["detail"].lower()
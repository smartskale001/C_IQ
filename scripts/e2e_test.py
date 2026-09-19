"""Standalone end-to-end test for the ContractIQ risk pipeline (NOT pytest).

Exercises the full flow against the app via TestClient using the repo's
test_contract.pdf with REAL OpenAI API calls:
  convert -> extract -> assess -> re-run guard -> list -> approve/reject/edit
  -> guarded re-run -> guarded patches -> summary email -> audit integrity.

Uses an in-memory SQLite DB (live data/contracts.db is untouched); /convert
still writes real files under tempfolder/ (cleaned up at the end on success).

Stops immediately with full details on the first failure.
"""

import json
import shutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

import main  # noqa: F401  (registers app + models, runs init_db)
from main import app, ASSESS_FIELD_COLUMNS
from db import get_session
import models.contract_extract  # noqa: F401
import models.risk  # noqa: F401
import models.audit  # noqa: F401
from models.contract_extract import ContractExtract
from models.risk import ContractRisk
from models.audit import AuditLog

PDF = ROOT / "test_contract.pdf"
EXPECTED_VIC_COUNT = 32
DISCLAIMER = (
    "This review is a summary and does not replace legal advice on the "
    "full contract. Please contact us before signing."
)

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
SQLModel.metadata.create_all(engine)


def _override_get_session():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_session] = _override_get_session
client = TestClient(app)

results = []


def headline(n, title):
    print(f"\n{'=' * 70}\nSTEP {n}: {title}\n{'=' * 70}")


def mark_pass(n):
    results.append((n, "PASS"))
    print(f"--> STEP {n}: PASS")


def mark_fail(n, msg, resp=None):
    print(f"\n!!! STEP {n} FAILED: {msg}")
    if resp is not None:
        try:
            print(f"status: {resp.status_code}")
            try:
                print(json.dumps(resp.json(), indent=2)[:4000])
            except Exception:
                print(resp.text[:4000])
        except Exception as e:
            print(f"(could not read response: {e})")
    print_summary()
    sys.exit(1)


def check(n, cond, msg, resp=None):
    if not cond:
        mark_fail(n, msg, resp)


def print_summary():
    print(f"\n{'=' * 70}\nE2E SUMMARY")
    for n, status in results:
        print(f"  Step {n:>2}: {status}")
    print(f"{'=' * 70}")


def db_session():
    return Session(engine)


def risk_id_for(extraction_id, rule_id):
    with db_session() as s:
        row = s.exec(
            select(ContractRisk).where(
                ContractRisk.extraction_id == extraction_id,
                ContractRisk.rule_id == rule_id,
            )
        ).first()
        return row.id if row else None


def main_flow():
    assert PDF.exists(), f"missing {PDF}"

    # ---- 1. UPLOAD & CONVERT ----
    headline(1, "UPLOAD & CONVERT")
    with open(PDF, "rb") as f:
        r = client.post("/convert", files={"file": ("test_contract.pdf", f, "application/pdf")})
    check(1, r.status_code == 200, "POST /convert did not return 200", r)
    md_path = r.json()["markdown_file_path"]
    print(f"markdown_file_path: {md_path}")
    preview = Path(md_path).read_text(encoding="utf-8", errors="replace")[:200]
    print(f"preview (first 200 chars):\n{preview}")
    mark_pass(1)

    # ---- 2. EXTRACT ----
    headline(2, "EXTRACT")
    r = client.post("/extract", json={"markdown_file_path": md_path})
    check(2, r.status_code == 200, "POST /extract did not return 200", r)
    body = r.json()
    check(2, "extraction_id" in body, "no extraction_id in /extract response", r)
    extraction_id = body["extraction_id"]
    print(f"extraction_id: {extraction_id}")
    fields = body.get("extracted_fields", {})
    print("12 extracted fields:")
    for col in ASSESS_FIELD_COLUMNS:
        print(f"  {col} = {json.dumps(fields.get(col), ensure_ascii=False)[:160]}")
    print("confidence scores (extracted_parameters):")
    for p in body.get("extracted_parameters", []):
        print(f"  {p.get('parameter_name')}: {p.get('confidence_score')}")
    mark_pass(2)

    # ---- 3. ASSESS RISK (first run) ----
    headline(3, "ASSESS RISK (first run)")
    r = client.post("/assess-risk", json={"extraction_id": extraction_id, "jurisdiction": "VIC"})
    check(3, r.status_code == 200, "POST /assess-risk did not return 200", r)
    body = r.json()
    total = body["total_risks"]
    print(f"total_risks: {total} (expected VIC count: {EXPECTED_VIC_COUNT})")
    check(3, total == EXPECTED_VIC_COUNT,
          f"expected {EXPECTED_VIC_COUNT} risks, got {total}", r)
    print("rule_id + assessment_status:")
    for item in body["risks"]:
        print(f"  {item['rule_id']:<14} {item['assessment_status']}")
    first_rule_ids = [item["rule_id"] for item in body["risks"]]
    mark_pass(3)

    # ---- 4. RE-RUN GUARD (nothing reviewed yet) ----
    headline(4, "RE-RUN GUARD (nothing reviewed yet)")
    r = client.post("/assess-risk", json={"extraction_id": extraction_id, "jurisdiction": "VIC"})
    check(4, r.status_code == 200, "re-run should succeed while all risks are pending", r)
    body = r.json()
    print(f"total_risks after re-run: {body['total_risks']}")
    check(4, body["total_risks"] == EXPECTED_VIC_COUNT, "re-run risk count changed", r)
    rerun_rule_ids = [item["rule_id"] for item in body["risks"]]
    check(4, rerun_rule_ids == first_rule_ids, "re-run rule_ids changed", r)
    print("re-run replaced untouched risks; count and rule_ids unchanged")
    mark_pass(4)

    # ---- 5. LIST RISKS ----
    headline(5, "LIST RISKS")
    r = client.get(f"/extractions/{extraction_id}/risks")
    check(5, r.status_code == 200, "GET /risks did not return 200", r)
    body = r.json()
    check(5, body["total_risks"] == EXPECTED_VIC_COUNT,
          f"expected {EXPECTED_VIC_COUNT}, got {body['total_risks']}", r)
    print("first 3 risks in full (incl. deserialized reference):")
    for item in body["risks"][:3]:
        print(json.dumps(item, indent=2))
        ref = item.get("reference") or {}
        check(5, isinstance(ref, dict) and
              {"page_num", "section_number", "section_title"} <= set(ref),
              f"reference not deserialized for {item['rule_id']}", r)
    listed = body["risks"]
    mark_pass(5)

    # ---- 6. REVIEW: approve ----
    headline(6, "REVIEW WORKFLOW — approve")
    cand = next((x for x in listed if x["assessment_status"] in ("Found", "Needs Attention")), None)
    check(6, cand is not None, "no Found/Needs Attention risk to approve")
    approve_rule = cand["rule_id"]
    approve_id = risk_id_for(extraction_id, approve_rule)
    check(6, approve_id is not None, f"risk row missing for {approve_rule}")
    with db_session() as s:
        before = s.get(ContractRisk, approve_id)
        print(f"before: reviewer_status={before.reviewer_status}, was_edited={before.was_edited}")
    r = client.patch(f"/risks/{approve_id}",
                     json={"action": "approve", "changed_by": "e2e_test"})
    check(6, r.status_code == 200, "PATCH approve did not return 200", r)
    check(6, r.json()["reviewer_status"] == "approved", "reviewer_status != approved", r)
    print(f"after:  reviewer_status={r.json()['reviewer_status']}, "
          f"was_edited={r.json()['was_edited']}")
    mark_pass(6)

    # ---- 7. REVIEW: reject ----
    headline(7, "REVIEW WORKFLOW — reject")
    cand2 = next((x for x in listed if x["rule_id"] != approve_rule), None)
    check(7, cand2 is not None, "no second risk to reject")
    reject_rule = cand2["rule_id"]
    reject_id = risk_id_for(extraction_id, reject_rule)
    r = client.patch(f"/risks/{reject_id}",
                     json={"action": "reject", "changed_by": "e2e_test"})
    check(7, r.status_code == 200, "PATCH reject did not return 200", r)
    check(7, r.json()["reviewer_status"] == "rejected", "reviewer_status != rejected", r)
    print(f"rejected {reject_rule} (id={reject_id})")
    mark_pass(7)

    # ---- 8. REVIEW: edit ----
    headline(8, "REVIEW WORKFLOW — edit")
    cand3 = next((x for x in listed
                  if x["rule_id"] not in (approve_rule, reject_rule)), None)
    check(8, cand3 is not None, "no third risk to edit")
    edit_rule = cand3["rule_id"]
    edit_id = risk_id_for(extraction_id, edit_rule)
    r = client.patch(f"/risks/{edit_id}",
                     json={"action": "edit", "changed_by": "e2e_test",
                           "risk_short_desc": "E2E edited description"})
    check(8, r.status_code == 200, "PATCH edit did not return 200", r)
    check(8, r.json()["was_edited"] is True, "was_edited != True", r)
    check(8, r.json()["reviewer_status"] == "pending",
          "edit changed reviewer_status", r)
    print(f"edited {edit_rule} (id={edit_id}): was_edited=True, still pending")
    with db_session() as s:
        from sqlmodel import select as _select
        entries = s.exec(
            _select(AuditLog).where(AuditLog.contract_risk_id == edit_id)
            .order_by(AuditLog.id)
        ).all()
        print(f"AuditLog entries for risk {edit_id}:")
        edited_ok = False
        for e in entries:
            print(f"  id={e.id} action={e.action} field={e.field_changed} "
                  f"ai_value={e.ai_value} human_value={e.human_value} by={e.changed_by}")
            if (e.action == "edited" and e.field_changed == "risk_short_desc"
                    and e.ai_value and e.human_value):
                edited_ok = edited_ok or (
                    json.loads(e.human_value) == "E2E edited description")
        check(8, edited_ok, "no edited entry with populated ai_value/human_value")
    mark_pass(8)

    # ---- 9. RE-RUN GUARD (after review) ----
    headline(9, "RE-RUN GUARD (after review)")
    r = client.post("/assess-risk", json={"extraction_id": extraction_id, "jurisdiction": "VIC"})
    check(9, r.status_code == 409, f"expected 409, got {r.status_code}", r)
    detail = r.json()["detail"]
    print(f"error: {detail}")
    check(9, "approved" in detail or "rejected" in detail,
          "409 message does not name the reviewer status")
    mark_pass(9)

    # ---- 10. GUARDED ACTIONS ON NON-PENDING ----
    headline(10, "GUARDED ACTIONS ON NON-PENDING RISKS")
    r1 = client.patch(f"/risks/{approve_id}",
                      json={"action": "approve", "changed_by": "e2e_test"})
    check(10, r1.status_code == 409, f"expected 409 on approved risk, got {r1.status_code}", r1)
    print(f"approved risk re-patch: {r1.json()['detail']}")
    r2 = client.patch(f"/risks/{reject_id}",
                      json={"action": "reject", "changed_by": "e2e_test"})
    check(10, r2.status_code == 409, f"expected 409 on rejected risk, got {r2.status_code}", r2)
    print(f"rejected risk re-patch: {r2.json()['detail']}")
    mark_pass(10)

    # ---- 11. SUMMARY EMAIL ----
    headline(11, "SUMMARY EMAIL")
    r = client.get(f"/extractions/{extraction_id}/summary-email")
    check(11, r.status_code == 200, "GET summary-email did not return 200", r)
    email_body = r.json()["email_body"]
    print("email_body (in full):")
    print("-" * 70)
    print(email_body)
    print("-" * 70)
    with db_session() as s:
        rows = s.exec(
            select(ContractRisk).where(ContractRisk.extraction_id == extraction_id)
        ).all()
        approved = [x for x in rows if x.reviewer_status == "approved"]
        others = [x for x in rows if x.reviewer_status != "approved"]
    check(11, approved, "no approved risks found for email assertions")
    for x in approved:
        check(11, x.risk_short_desc in email_body,
              f"approved risk text missing: {x.risk_short_desc}")
    for x in others:
        check(11, x.risk_short_desc not in email_body,
              f"non-approved risk text leaked: {x.risk_short_desc} ({x.reviewer_status})")
    check(11, DISCLAIMER in email_body, "exact disclaimer sentence missing")
    print("approved-only filtering + disclaimer verified")
    mark_pass(11)

    # ---- 12. AUDIT TRAIL INTEGRITY ----
    headline(12, "AUDIT TRAIL INTEGRITY")
    with db_session() as s:
        risk_ids = [x.id for x in s.exec(
            select(ContractRisk).where(ContractRisk.extraction_id == extraction_id)
        ).all()]
        entries = s.exec(
            select(AuditLog).where(AuditLog.contract_risk_id.in_(risk_ids))
            .order_by(AuditLog.id)
        ).all()
        print(f"{'risk_id':>8}  {'action':<9}  {'changed_by':<12}  timestamp")
        for e in entries:
            print(f"{e.contract_risk_id:>8}  {e.action:<9}  "
                  f"{str(e.changed_by):<12}  {e.timestamp}")
        actions = [e.action for e in entries]
        created = actions.count("created")
        check(12, created >= len(risk_ids),
              f"expected >=1 created per risk ({len(risk_ids)} risks, {created} created)")
        check(12, "approved" in actions, "no approved audit entry")
        check(12, "rejected" in actions, "no rejected audit entry")
        check(12, "edited" in actions, "no edited audit entry")
    mark_pass(12)

    # ---- 13. SUMMARY ----
    headline(13, "SUMMARY")
    results.append((13, "PASS"))
    print("--> STEP 13: PASS")
    print_summary()

    # tidy up the real tempfolder files created by /convert
    shutil.rmtree(ROOT / "tempfolder" / "test_contract", ignore_errors=True)


if __name__ == "__main__":
    try:
        main_flow()
    except SystemExit:
        raise
    except Exception:
        print("\n!!! UNEXPECTED EXCEPTION — full traceback:")
        traceback.print_exc()
        print_summary()
        sys.exit(1)

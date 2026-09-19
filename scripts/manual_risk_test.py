"""
Throwaway manual check for the risk assessment service (Task 8).

Loads extracted fields (from a real extraction row if one exists, otherwise
the standard sample), calls assess_risks() against the live OpenAI API, and
prints the results plus a missing-rules summary.

NOT a pytest test. Requires a real OPENAI_API_KEY in .env.
"""

import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env", override=True)

from services.risk_assessor import assess_risks, RiskAssessmentError, MissingApiKeyError  # noqa: E402
from rulebook import get_rulebook  # noqa: E402

SAMPLE_FIELDS = {
    "subject_to_lease": "Yes - tenanted",
    "date_of_tenancy": "2026-11-14",
    "contract_price": 1285000,
    "deposit_amount": 128500,
    "deposit_due_date": "2026-09-13",
    "subject_to_finance": True,
    "settlement_date": "30 days from signing",
    "gst_clause": "Price is GST inclusive",
    "terms_contract": "Standard terms apply",
    "default_provisions": "Interest 12% p.a. on default",
    "due_date_extension": None,
    "special_conditions": None,
}


def load_extracted_fields() -> dict:
    """Use the newest extraction row's flat fields, or the sample."""
    from sqlalchemy import create_engine, text

    db_path = ROOT / "data" / "contracts.db"
    if not db_path.exists():
        return dict(SAMPLE_FIELDS)

    engine = create_engine(f"sqlite:///{db_path}")
    cols = [
        "subject_to_lease", "date_of_tenancy", "contract_price", "deposit_amount",
        "deposit_due_date", "subject_to_finance", "settlement_date", "gst_clause",
        "terms_contract", "default_provisions", "due_date_extension", "special_conditions",
    ]
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {', '.join(cols)} FROM contract_extracts ORDER BY id DESC LIMIT 1")
            ).mappings().first()
    except Exception as exc:
        print(f"Could not read extraction from DB ({exc}); using sample data.")
        return dict(SAMPLE_FIELDS)

    if row is None:
        print("No extraction rows in DB; using sample data.")
        return dict(SAMPLE_FIELDS)

    fields = {}
    for col in cols:
        value = row[col]
        if isinstance(value, str):
            try:
                fields[col] = json.loads(value)
            except json.JSONDecodeError:
                fields[col] = value
        else:
            fields[col] = value

    if not any(v is not None for v in fields.values()):
        print("Latest extraction row is empty; using sample data.")
        return dict(SAMPLE_FIELDS)

    print("Loaded real extraction from data/contracts.db")
    for key, value in fields.items():
        print(f"  {key} = {value!r}")
    return fields


def main():
    fields = load_extracted_fields()

    rulebook_ids = re.findall(
        r"^### ([A-Z]+(?:-[A-Z]+)?-\d+)$", get_rulebook("VIC"), re.MULTILINE
    )
    print(f"\nVIC rulebook contains {len(rulebook_ids)} rules "
          f"({len([r for r in rulebook_ids if r.startswith('VIC-')])} VIC + "
          f"{len([r for r in rulebook_ids if not r.startswith('VIC-')])} AU-wide)\n")

    try:
        risks = assess_risks(fields, jurisdiction="VIC")
    except MissingApiKeyError as e:
        print(f"FAILED: {e}")
        sys.exit(1)
    except RiskAssessmentError as e:
        print(f"FAILED: {e}")
        sys.exit(1)

    print(f"assess_risks returned {len(risks)} RiskItems:\n")
    risk_items = sorted(risks, key=lambda r: r.rule_id)
    for risk in risk_items:
        print(f"  {risk.rule_id}")
        print(f"    status:          {risk.assessment_status}")
        print(f"    confidence:      {risk.confidence_score}")
        print(f"    short_desc:      {risk.risk_short_desc}")

    returned_ids = {r.rule_id for r in risks}
    missing = [rid for rid in rulebook_ids if rid not in returned_ids]

    print("\n===== SUMMARY =====")
    print(f"rules in VIC rulebook : {len(rulebook_ids)}")
    print(f"risk items returned    : {len(returned_ids)}")
    print(f"duplicates in response : {len(risks) - len(returned_ids)}")
    if missing:
        print(f"rules with NO response: {len(missing)}")
        for rid in missing:
            print(f"  - {rid}")
    else:
        print("rules with NO response: 0 (every VIC rulebook rule was answered)")

    missing_found = [rid for rid in missing if rid.startswith("VIC-")]
    if missing_found:
        print("\nWARNING: the model silently dropped VIC rules entirely "
              f"({len(missing_found)}): {missing_found}")


if __name__ == "__main__":
    main()
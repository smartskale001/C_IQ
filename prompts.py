"""
Extraction and risk assessment prompts for contract analysis using OpenAI GPT.
"""

import json

from rulebook import get_rulebook

EXTRACTION_INSTRUCTIONS = """You are an expert contract data extraction assistant.

Your task is to extract the specified fields from the contract provided below.

CRITICAL INSTRUCTIONS:
- Return ONLY valid JSON, no explanations or markdown
- Extract information ONLY when explicitly stated in the contract
- Do not infer, assume, calculate, or create information
- Return null for missing or unclear fields
- Preserve exact contractual meaning
- All monetary values must be numeric only (no currency symbols)
- All dates must be YYYY-MM-DD format
- Boolean fields: true/false/null only

### Extraction Rules

1. Read the entire contract carefully before extracting.
2. Extract information only when explicitly stated or clearly identifiable.
3. Do not infer, assume, calculate, or create any missing information.
4. If a field cannot be found or determined with confidence, return null (not empty string).
5. Preserve the exact contractual meaning and wording.
6. For clause/text fields, extract relevant wording or provide accurate summary.
7. For dates, return YYYY-MM-DD format when explicitly available.
8. For monetary amounts, return numeric value only (e.g., 1285000, not "$1,285,000").
9. For boolean fields (subject_to_finance), return true/false only when clearly stated, otherwise null.
10. Use only information from the provided contract text.
11. Return ONLY the requested JSON fields - no explanations, markdown, or additional fields.
12. Ensure output is valid JSON that can be parsed without errors.

### Fields to Extract

1. **subject_to_lease**: Determine whether the contract/property is subject to an existing lease or tenancy. Extract the relevant value or statement.

2. **date_of_tenancy**: Extract the date on which the tenancy begins or the relevant tenancy date (YYYY-MM-DD format).

3. **contract_price**: Extract the agreed contract/purchase price (numeric value only).

4. **deposit_amount**: Extract the required deposit amount (numeric value only).

5. **deposit_due_date**: Extract the date by which the deposit must be paid (YYYY-MM-DD format).

6. **subject_to_finance**: Determine whether the contract is subject to finance approval. Return true, false, or null.

7. **settlement_date**: Extract the agreed settlement/completion date (YYYY-MM-DD format or description).

8. **gst_clause**: Extract the clause or provision relating to GST, including whether GST is included, excluded, payable, or applicable.

9. **terms_contract**: Extract the key contractual terms and conditions associated with the agreement.

10. **default_provisions**: Extract the provisions describing what happens if either party defaults, breaches, fails to perform, or does not meet contractual obligations.

11. **due_date_extension**: Extract any provision allowing, defining, or restricting an extension of payment, settlement, or tenancy dates.

12. **special_conditions**: Extract any special conditions, contingencies, or unique clauses that affect the agreement.

### Contract Document

Below is the contract to extract from:

---
{contract_content}
---

### Output Format

Return a valid JSON object with the following structure for each extracted parameter:
{{
    "extracted_parameters": [
        {{
            "parameter_name": "field_name",
            "parameter_value": "extracted_value_or_null",
            "confidence_score": 0-100,
            "reference": {{
                "page_num": page_number_or_null,
                "section_number": "section_identifier_or_null",
                "section_title": "section_title_or_null"
            }}
        }},
        ...
    ],
    "subject_to_lease": "string or null",
    "date_of_tenancy": "YYYY-MM-DD or null",
    "contract_price": number or null,
    "deposit_amount": number or null,
    "deposit_due_date": "YYYY-MM-DD or null",
    "subject_to_finance": true/false or null,
    "settlement_date": "YYYY-MM-DD or string or null",
    "gst_clause": "string or null",
    "terms_contract": "string or null",
    "default_provisions": "string or null",
    "due_date_extension": "string or null",
    "special_conditions": "string or null"
}}

### Confidence Score Guidelines
- 90-100: Information explicitly and clearly stated in the contract
- 70-89: Information reasonably clear but requires interpretation
- 50-69: Information partially clear or inferred from context
- 0-49: Information unclear, uncertain, or requires significant inference

### Reference Information
- page_num: The page number where the information was found (if available)
- section_number: The section/clause number (e.g., "2.1", "Article 3")
- section_title: The title of the section or clause

Return ONLY the JSON object. No explanations, no markdown, no additional text."""


def build_extraction_prompt(contract_markdown: str) -> str:
    """
    Build the complete extraction prompt with contract content.

    Args:
        contract_markdown: The contract content in markdown format

    Returns:
        Complete prompt ready for LLM
    """
    return EXTRACTION_INSTRUCTIONS.format(contract_content=contract_markdown)


RISK_ASSESSMENT_INSTRUCTIONS = """You are an expert contract risk assessment assistant.

Your task is to assess an already-extracted set of contract facts against a set of rulebook rules and report which risks apply.

CRITICAL INSTRUCTIONS:
- Return ONLY valid JSON, no explanations or markdown code fences
- Return a JSON array with exactly one object per rule in the rulebook context below
- Never invent a rule_id that is not present in the rulebook context
- Assess only from the extracted fields provided; do not guess about the contract beyond them
- If a rule cannot be assessed from the given fields because they carry no relevant information, mark it "Not Applicable" rather than guessing
- assessment_status must be one of: "Found", "Not Found", "Needs Attention", "Not Applicable"
- confidence_score must be an integer between 0 and 100

### Assessment Rules (Rulebook)

Evaluate each rule below against the extracted fields.

---
{rulebook_context}
---

### Extracted Contract Fields

These are the facts already extracted from the contract. Assess the rules against them.

---
{extracted_fields}
---

### Output Format

Return a JSON array. Every rule in the rulebook context above must appear exactly once, using this structure:

[
    {{
        "rule_id": "VIC-DISC-001",
        "risk_short_desc": "short one-line summary",
        "risk_long_desc": "full explanation for the reviewer",
        "confidence_score": 85,
        "reference": {{
            "page_num": 2,
            "section_number": "5",
            "section_title": "Disclosure"
        }},
        "assessment_status": "Found"
    }},
    ...
]

### RiskItem Field Guidance

- rule_id: Copy it unchanged from the rulebook context. Never alter, reformat, or invent rule IDs.
- risk_short_desc: One-line summary; also serves as the email summary and UI label.
- risk_long_desc: Full explanation for a human reviewer, referencing the relevant extracted fields.
- confidence_score: 0-100, your confidence in this assessment, following the same convention as extraction. A score of 0 is never valid in the output; it is reserved for system-side parse or processing failures. This applies to every assessment_status, including "Not Applicable".
- reference: page_num, section_number, section_title where the supporting evidence lives, taken from the extracted fields (or their references); use null for any sub-field that is unknown.
- assessment_status: "Found" if the risk condition exists; "Not Found" if the check ran and nothing adverse was found; "Needs Attention" if the evidence is ambiguous or incomplete; "Not Applicable" if the rule cannot be assessed from the given extracted fields. For "Not Applicable", risk_short_desc must give a brief contract-specific reason why the rule does not apply (e.g. "No strata scheme — standalone dwelling"), never a restatement of the rulebook's check description, and confidence_score must still be an integer of at least 1.

Return ONLY the JSON array. No prose, no markdown, no additional text."""


def build_risk_assessment_prompt(
    extracted_fields: dict, jurisdiction: str | None = None
) -> str:
    """
    Build the complete risk assessment prompt with rulebook context.

    Args:
        extracted_fields: The 12 extracted contract facts to assess
        jurisdiction: "VIC", "NSW", or None for all rules

    Returns:
        Complete prompt ready for LLM
    """
    rulebook_context = get_rulebook(jurisdiction)
    extracted_fields_json = json.dumps(extracted_fields, indent=2, default=str)
    return RISK_ASSESSMENT_INSTRUCTIONS.format(
        rulebook_context=rulebook_context,
        extracted_fields=extracted_fields_json,
    )


if __name__ == "__main__":
    sample_extracted_fields = {
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
    print(build_risk_assessment_prompt(sample_extracted_fields, jurisdiction="VIC"))

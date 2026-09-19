"""
Rulebook risk assessment service using OpenAI GPT API.
Evaluates extracted contract fields against rulebook rules.
"""

import json
import logging
import re

import requests
from pydantic import ValidationError

from models.schemas import RiskItem
from prompts import build_risk_assessment_prompt
from rulebook import get_rulebook
from services.contract_extractor import MissingApiKeyError, get_extractor

# Setup logging
logger = logging.getLogger(__name__)


class RiskAssessmentError(Exception):
    """Custom exception for risk assessment errors."""
    pass


_VALID_RULE_ID_RE = re.compile(r"^### ([A-Z]+(?:-[A-Z]+)?-\d+)$", re.MULTILINE)


def _valid_rule_ids(jurisdiction: str | None) -> set:
    """Return the set of rule IDs that were included in the sent prompt."""
    return set(_VALID_RULE_ID_RE.findall(get_rulebook(jurisdiction)))


def _parse_json_array(response_text: str) -> list:
    """
    Parse JSON array from LLM response, handling markdown code blocks.

    Args:
        response_text: Raw response from LLM

    Returns:
        Parsed list of risk dicts

    Raises:
        RiskAssessmentError: If the response is not parseable as a JSON array
    """
    if response_text.startswith("```json"):
        response_text = response_text[7:]  # Remove ```json
    if response_text.startswith("```"):
        response_text = response_text[3:]  # Remove ```
    if response_text.endswith("```"):
        response_text = response_text[:-3]  # Remove trailing ```

    response_text = response_text.strip()

    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse risk assessment response: {response_text[:200]}")
        raise RiskAssessmentError("Failed to parse LLM response as JSON")

    if not isinstance(parsed, list):
        logger.error(f"Risk assessment response was not a JSON array: {type(parsed).__name__}")
        raise RiskAssessmentError("Risk assessment response must be a JSON array")

    return parsed


def _validate_risk_items(items: list, jurisdiction: str | None) -> list:
    """
    Validate parsed risk entries against RiskItem schema.

    Drops (with a logged warning, never crashing) entries that:
    - are not objects,
    - reference a rule_id not in the rulebook context sent to the model,
    - duplicate a rule_id already seen (first occurrence wins).

    Args:
        items: Raw parsed risk dicts
        jurisdiction: Jurisdiction used to build the prompt

    Returns:
        List of validated RiskItem objects
    """
    valid_rule_ids = _valid_rule_ids(jurisdiction)
    risks: list = []
    seen: set = set()

    for entry in items:
        if not isinstance(entry, dict):
            logger.warning(f"Dropping non-object risk entry: {entry!r}")
            continue

        rule_id = entry.get("rule_id")
        if rule_id not in valid_rule_ids:
            logger.warning(f"Dropping risk with unknown rule_id: {rule_id!r}")
            continue
        if rule_id in seen:
            logger.warning(f"Dropping duplicate risk for rule_id: {rule_id!r}")
            continue
        seen.add(rule_id)

        try:
            risks.append(RiskItem(**entry))
        except ValidationError as e:
            logger.warning(f"Dropping invalid risk for rule_id {rule_id!r}: {str(e)}")
            continue

    logger.info(
        f"Validated {len(risks)} of {len(items)} risk entries "
        f"(against {len(valid_rule_ids)} rulebook rules)"
    )
    return risks


def assess_risks(extracted_fields: dict, jurisdiction: str | None = None) -> list[RiskItem]:
    """
    Assess extracted contract fields against the rulebook rules.

    Args:
        extracted_fields: The 12 extracted contract facts to assess
        jurisdiction: "VIC", "NSW", or None for all rules

    Returns:
        List of validated RiskItem objects

    Raises:
        MissingApiKeyError: If OPENAI_API_KEY is not configured
        RiskAssessmentError: If the API call or response parsing fails
    """
    extractor = get_extractor()
    prompt = build_risk_assessment_prompt(extracted_fields, jurisdiction)

    logger.info(f"Sending risk assessment request to OpenAI API (jurisdiction={jurisdiction})...")

    headers = {
        "Authorization": f"Bearer {extractor.api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": extractor.model,
        "max_tokens": 8000,
        "temperature": 0,  # Deterministic output for assessment
        "messages": [
            {
                "role": "system",
                "content": "You are a contract risk assessment expert. Evaluate extracted contract fields against the rulebook rules and return valid JSON only."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    try:
        response = requests.post(
            f"{extractor.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        response.raise_for_status()
        response_data = response.json()
        response_text = response_data["choices"][0]["message"]["content"]
    except RiskAssessmentError:
        raise
    except Exception as e:
        logger.error(f"Risk assessment API call failed: {str(e)}")
        raise RiskAssessmentError(f"Unexpected error during risk assessment: {str(e)}")

    logger.info(f"Received risk assessment response: {len(response_text)} characters")

    parsed = _parse_json_array(response_text)
    return _validate_risk_items(parsed, jurisdiction)
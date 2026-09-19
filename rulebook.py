"""
Loader for the merged rulebook Markdown file.
"""

import re
from pathlib import Path

RULEBOOK_PATH = Path(__file__).resolve().parent / "data" / "rulebook_merged.md"


def _load() -> str:
    if not RULEBOOK_PATH.exists():
        raise FileNotFoundError(
            f"Rulebook file not found at {RULEBOOK_PATH}. "
            "Run `scripts/build_rulebook.py` to generate it."
        )
    return RULEBOOK_PATH.read_text(encoding="utf-8")


RULEBOOK_TEXT = _load()

_JURISDICTION_RE = re.compile(r"^- jurisdiction: (\S+)$", re.MULTILINE)
_RULE_HEADER_RE = re.compile(r"^### ", re.MULTILINE)

_GUIDANCE_PREFIX = RULEBOOK_TEXT.split("\n### ")[0]
_RULES = []
for block in RULEBOOK_TEXT.split("\n### ")[1:]:
    block = "### " + block
    match = _JURISDICTION_RE.search(block)
    jurisdiction = match.group(1) if match else ""
    header = block.splitlines()[0]
    rule_id = header.replace("### ", "").strip()
    _RULES.append((rule_id, jurisdiction, block))

SUPPORTED_JURISDICTIONS = ("VIC", "NSW")


def get_rulebook(jurisdiction: str | None = None) -> str:
    """
    Return the merged rulebook text, optionally filtered by jurisdiction.

    Args:
        jurisdiction: "VIC" or "NSW" to return only rules for that
            jurisdiction plus AU-wide rules; None returns everything.

    Returns:
        Rulebook text as a string.
    """
    if jurisdiction is None:
        return RULEBOOK_TEXT
    if jurisdiction not in SUPPORTED_JURISDICTIONS:
        raise ValueError(
            f"Unsupported jurisdiction: {jurisdiction!r}. "
            f"Expected one of {SUPPORTED_JURISDICTIONS} or None."
        )
    blocks = [
        block
        for _, block_jurisdiction, block in _RULES
        if block_jurisdiction in (jurisdiction, "AU-wide")
    ]
    return _GUIDANCE_PREFIX + "\n" + "\n".join(blocks).rstrip() + "\n"
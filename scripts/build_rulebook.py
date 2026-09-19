"""
Merge the five PDF rulebooks in data/rulebooks/ into a single Markdown file.

Extracts the "Proposed Rules" table (Rule ID | Check | Suggested Output) from
each PDF using pdfplumber and writes it to data/rulebook_merged.md.
"""

import re
from pathlib import Path

import pdfplumber

RULEBOOKS_DIR = Path(__file__).resolve().parent.parent / "data" / "rulebooks"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "rulebook_merged.md"

JURISDICTIONS = {1: "VIC", 2: "NSW"}

CATEGORY_BY_PREFIX = {
    "VIC-CON": "contract",
    "NSW-CON": "contract",
    "VIC-DISC": "disclosure",
    "NSW-DISC": "disclosure",
    "TAX": "tax",
    "PLAN": "planning",
    "STRATA": "strata",
    "PROP": "strata",
    "VIC-SET": "contract",
    "NSW-SET": "contract",
    "NSW-DEF": "contract",
    "NSW-DEP": "contract",
    "NSW-COOL": "contract",
}

RULE_ID_RE = re.compile(r"^[A-Z]+(?:-[A-Z]+)?-\d+$")


def extract_title(pdf) -> str:
    """Return the rulebook title from page 1 (text above the 'Rulebook N of 5' line)."""
    text = pdf.pages[0].extract_text() or ""
    lines = [ln.strip() for ln in text.splitlines()]
    title_lines = []
    for line in lines:
        if line.startswith("Rulebook ") and " of " in line:
            break
        if line:
            title_lines.append(line)
    return " ".join(title_lines).strip()


def extract_rules(pdf) -> list:
    rules = []
    for page in pdf.pages:
        for table in page.extract_tables() or []:
            for row in table[1:]:
                rule_id = (row[0] or "").strip()
                if not RULE_ID_RE.match(rule_id):
                    continue
                check = " ".join((row[1] or "").split())
                suggested_output = " ".join((row[2] or "").split())
                rules.append((rule_id, check, suggested_output))
    return rules


def extract_guidance(pdf) -> list:
    bullet = None
    bullets = []
    for page in pdf.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("4. Implementation Guidance"):
                bullet = True
                continue
            if stripped.startswith("5. Reference Sources"):
                bullet = False
            if bullet and stripped.startswith("(cid:127)"):
                bullets.append(stripped.replace("(cid:127)", "").strip())
    return bullets


def rulebook_number(path: Path) -> int:
    return int(path.stem.split("_")[1])


def jurisdiction_for(number: int) -> str:
    return JURISDICTIONS.get(number, "AU-wide")


def category_for(rule_id: str) -> str:
    prefix = RULE_ID_RE.match(rule_id).group(0)
    prefix = prefix.rsplit("-", 1)[0]
    return CATEGORY_BY_PREFIX[prefix]


def build():
    pdfs = sorted(RULEBOOKS_DIR.glob("*.pdf"), key=rulebook_number)

    guidance = extract_guidance(pdfplumber.open(pdfs[0]))

    lines = ["# Merged Rulebook", "", "## Shared Implementation Guidance", ""]
    lines.extend(f"- {g}" for g in guidance)
    lines.append("")

    for path in pdfs:
        number = rulebook_number(path)
        jurisdiction = jurisdiction_for(number)
        with pdfplumber.open(path) as pdf:
            title = extract_title(pdf)
            for rule_id, check, suggested_output in extract_rules(pdf):
                lines.extend(
                    [
                        f"### {rule_id}",
                        f"- jurisdiction: {jurisdiction}",
                        f"- category: {category_for(rule_id)}",
                        f"- source: {title}",
                        f"- check: {check}",
                        f"- suggested_output: {suggested_output}",
                        "",
                    ]
                )

    OUTPUT_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH} ({len([l for l in lines if l.startswith('### ')])} rules)")


if __name__ == "__main__":
    build()
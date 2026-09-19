"""Tests for the merged rulebook loader."""

import pytest

from rulebook import RULEBOOK_TEXT, get_rulebook


def test_rulebook_loads_with_39_rules():
    assert "## Shared Implementation Guidance" in RULEBOOK_TEXT
    rule_lines = [line for line in RULEBOOK_TEXT.splitlines() if line.startswith("### ")]
    assert len(rule_lines) == 39


def test_get_rulebook_returns_everything_by_default():
    assert get_rulebook() == RULEBOOK_TEXT
    assert get_rulebook(None) == RULEBOOK_TEXT


def test_get_rulebook_vic_excludes_nsw_rule_ids():
    filtered = get_rulebook("VIC")
    assert "## Shared Implementation Guidance" in filtered
    assert "### VIC-CON-001" in filtered
    assert "### PLAN-001" in filtered
    assert not any(line.startswith("### NSW-") for line in filtered.splitlines())


def test_get_rulebook_rejects_unknown_jurisdiction():
    with pytest.raises(ValueError):
        get_rulebook("TAS")
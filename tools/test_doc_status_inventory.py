"""doc_status offers approval only when the guide inventory is mapped (T4, S5); never on a score."""
from __future__ import annotations

from pathlib import Path

import yaml

import doc_status
from conftest import DEFAULT_RUBRIC_CRITERIA, _cited_body, _content_check, _report, _rubric, _skip_research, _sources_bib
from test_guide_facts_inventory import GUIDE

# The marker _content_check writes names the default criteria, so the plans extend those.
FIRST, SECOND = DEFAULT_RUBRIC_CRITERIA[:2]
CRITERIA = ({**FIRST, "covers": ["G1", "G2", "G3", "G4"]}, dict(SECOND))
ALL_MAPPED = (CRITERIA[0], {**SECOND, "covers": ["G5", "G6", "G7"]})


def verified_with_guide(folder: Path, criteria: tuple | list | None = None) -> Path:
    _report(folder)
    (folder / "report.yml").write_text((folder / "report.yml").read_text() + "guide: guide.txt\n", encoding="utf-8")
    (folder / "guide.txt").write_text(GUIDE, encoding="utf-8")
    _skip_research(folder)
    _sources_bib(folder)
    _rubric(folder, criteria=tuple(criteria) if criteria is not None else None)
    _cited_body(folder)
    _content_check(folder)
    return folder


def approval(folder: Path):
    return next(p for p in doc_status.derive(folder).phases if p.name == "approval")


def test_unmapped_inventory_blocks_approval_and_names_the_items(tmp_path: Path) -> None:
    folder = verified_with_guide(tmp_path / "wf", CRITERIA)
    phase = approval(folder)
    assert phase.state == doc_status.BLOCKED and phase.blocked_reason == "guide_inventory_unmapped"
    assert "G5" in phase.detail
    status = doc_status.derive(folder)
    assert status.next_token == "approval"
    assert "rubric_plan.py" in status.gate and "not_applicable" in status.gate


def test_mapped_or_not_applicable_inventory_offers_approval(tmp_path: Path) -> None:
    mapped = verified_with_guide(tmp_path / "a", ALL_MAPPED)
    assert approval(mapped).state == doc_status.CURRENT
    waived = verified_with_guide(tmp_path / "b", CRITERIA)
    path = waived / "rubric.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["not_applicable"] = [{"item": i, "reason": "no aplica"} for i in ("G5", "G6", "G7")]
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    _content_check(waived)
    assert approval(waived).state == doc_status.CURRENT


def test_a_report_without_a_guide_is_never_blocked_by_the_inventory(tmp_path: Path) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    _skip_research(folder)
    _sources_bib(folder)
    _rubric(folder)
    _cited_body(folder)
    _content_check(folder)
    assert approval(folder).state == doc_status.CURRENT


def test_a_missing_requirement_is_not_a_new_approval_block(tmp_path: Path) -> None:
    # the verify gate already stops a failing content check; the inventory adds nothing for `missing`.
    folder = verified_with_guide(tmp_path / "wf", ALL_MAPPED)
    assert approval(folder).blocked_reason == ""

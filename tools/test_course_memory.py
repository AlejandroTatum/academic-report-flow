"""Per-course memory (guide-vs-teacher-rubric T2, S5, S2).

The teacher rubric is stored once per course, a feedback log holds each graded
delivery, and the AI declaration is a per-course decision. ``course_memory``
reads all three, warns about anything missing or malformed and always exits 0;
``--add-delivery`` is its only write.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import course_memory
import doc_status
from conftest import _config, _report, _rubric

SLUG = "redes-de-computadoras"
LEVELS = [{"points": 4, "descriptor": "Analisis completo"}, {"points": 2, "descriptor": "Analisis parcial"}]
COURSE_RUBRIC = {
    "schema": "academic.course-rubric/v1",
    "source": "Rubrica U1",
    "criteria": [{"id": "analisis", "title": "Analisis de resultados", "weight": 30, "levels": LEVELS}],
}
FEEDBACK = {
    "schema": "academic.course-feedback/v1",
    "ai_declaration": "include",
    "deliveries": [
        {"work": "fase-2", "date": "2026-10-08", "grade": 9.0, "max": 10, "comments": ["declaracion de IA??"]},
    ],
}
NO_RUBRIC = f"warning: no course rubric in academic-sources/{SLUG}/rubrics/ (save the teacher's rubric there once, schema academic.course-rubric/v1)"
NO_FEEDBACK = "warning: no feedback.yml for this course yet; after the teacher grades a delivery, record it with --add-delivery"
NO_DECISION = "warning: no AI declaration decision for this course; record ai_declaration: include|omit in feedback.yml"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    content = tmp_path / "content"
    content.mkdir()
    monkeypatch.setenv("REPORT_CONTENT_ROOT", str(content))
    return content


def _work(root: Path, extra: str = "", **metadata: object) -> Path:
    folder = root / "reports" / "ape-1"
    _report(folder, **({"subject": "Redes de Computadoras"} | metadata))
    if extra:
        report = folder / "report.yml"
        report.write_text(report.read_text(encoding="utf-8") + extra, encoding="utf-8")
    return folder


def _course(root: Path, rubric: object = None, feedback: object = None) -> Path:
    course = root / "academic-sources" / SLUG
    if rubric is not None:
        (course / "rubrics").mkdir(parents=True, exist_ok=True)
        text = rubric if isinstance(rubric, str) else yaml.safe_dump(rubric, sort_keys=False)
        (course / "rubrics" / "u1.yml").write_text(text, encoding="utf-8")
    if feedback is not None:
        course.mkdir(parents=True, exist_ok=True)
        text = feedback if isinstance(feedback, str) else yaml.safe_dump(feedback, sort_keys=False, allow_unicode=True)
        (course / "feedback.yml").write_text(text, encoding="utf-8")
    return course


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> list[str]:
    assert course_memory.main(list(argv)) == 0
    return capsys.readouterr().out.splitlines()


def test_reads_rubric_deliveries_and_decision_without_writing(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _work(root, 'ai_declaration: "Se uso Claude."\n')
    _course(root, COURSE_RUBRIC, FEEDBACK)
    before = _snapshot(root)

    lines = _run(capsys, str(folder))

    assert _snapshot(root) == before
    assert lines == [
        f"course: {SLUG} (academic-sources/{SLUG})",
        "teacher rubric: rubrics/u1.yml (1 criterion, source: Rubrica U1)",
        "add to rubric.yml criteria (set each section: to the body heading that answers it):",
        "- id: analisis",
        "  title: Analisis de resultados",
        "  section: ''",
        "  origin: teacher",
        "  weight: 30",
        "  levels:",
        "  - points: 4",
        "    descriptor: Analisis completo",
        "  - points: 2",
        "    descriptor: Analisis parcial",
        "deliveries: 1 in feedback.yml",
        "- fase-2 2026-10-08: 9.0/10",
        "  comment: declaracion de IA??",
        "ai_declaration: include (course decision in feedback.yml)",
    ]


def test_missing_course_files_are_warnings_and_default_to_include(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _work(root)
    before = _snapshot(root)

    lines = _run(capsys, str(folder))

    assert _snapshot(root) == before
    assert lines == [
        f"course: {SLUG} (academic-sources/{SLUG})",
        NO_RUBRIC,
        NO_FEEDBACK,
        "ai_declaration: include (default; no course decision)",
        NO_DECISION,
        "warning: course decision is include but report.yml has no ai_declaration yet",
    ]


def test_malformed_course_files_are_warnings(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _work(root, "ai_declaration: false\n")
    bad_rubric = {**COURSE_RUBRIC, "criteria": [{"id": "analisis", "title": "Analisis", "levels": LEVELS[:1]}]}
    _course(root, bad_rubric, "deliveries: [unclosed\n")

    lines = _run(capsys, str(folder))

    assert lines == [
        f"course: {SLUG} (academic-sources/{SLUG})",
        "warning: rubrics/u1.yml malformed: criterion 1 levels must be a list of at least 2 {points, descriptor} mappings",
        NO_RUBRIC,
        "warning: feedback.yml malformed: not readable YAML",
        "ai_declaration: include (default; no course decision)",
        NO_DECISION,
        "warning: course decision is include but report.yml has ai_declaration: false",
    ]


def test_bad_delivery_entry_and_omit_mismatch_warn(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _work(root, 'ai_declaration: "Se uso Claude."\n')
    feedback = {**FEEDBACK, "ai_declaration": "omit", "deliveries": [*FEEDBACK["deliveries"], {"work": "fase-3"}]}
    _course(root, COURSE_RUBRIC, feedback)

    lines = _run(capsys, str(folder))

    assert lines[-6:] == [
        "warning: feedback.yml delivery 2 malformed (needs work, date, grade, max)",
        "deliveries: 1 in feedback.yml",
        "- fase-2 2026-10-08: 9.0/10",
        "  comment: declaracion de IA??",
        "ai_declaration: omit (course decision in feedback.yml)",
        "warning: course decision is omit but report.yml carries an ai_declaration",
    ]


def test_no_subject_is_a_warning(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _work(root, subject=None)

    assert _run(capsys, str(folder)) == [
        "warning: no course for this report (academic route with metadata.subject needed); no course memory read"
    ]


def test_add_delivery_appends_and_keeps_existing_deliveries(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _work(root)
    course = _course(root, feedback=FEEDBACK)

    lines = _run(
        capsys, str(folder), "--add-delivery", "--date", "2026-11-01", "--grade", "8.5",
        "--comment", "falta reflexion", "--comment", "buen diagrama",
    )

    assert lines == [f"recorded: ape-1 2026-11-01 8.5/10 in academic-sources/{SLUG}/feedback.yml"]
    data = yaml.safe_load((course / "feedback.yml").read_text(encoding="utf-8"))
    assert data["deliveries"][0] == FEEDBACK["deliveries"][0]
    assert data["deliveries"][1] == {
        "work": "ape-1", "date": "2026-11-01", "grade": 8.5, "max": 10, "comments": ["falta reflexion", "buen diagrama"],
    }
    assert data["ai_declaration"] == "include" and data["schema"] == FEEDBACK["schema"]


def test_add_delivery_creates_the_log_and_refuses_nothing(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _work(root)

    missing = _run(capsys, str(folder), "--add-delivery", "--date", "2026-11-01")
    assert missing == ["warning: --add-delivery needs --date and a numeric --grade; delivery not recorded"]
    assert not (root / "academic-sources").exists()

    created = _run(capsys, str(folder), "--add-delivery", "--work", "fase-1", "--date", "2026-10-01", "--grade", "6", "--max", "10")
    assert created == [f"recorded: fase-1 2026-10-01 6.0/10 in academic-sources/{SLUG}/feedback.yml"]
    data = yaml.safe_load((root / "academic-sources" / SLUG / "feedback.yml").read_text(encoding="utf-8"))
    assert data == {
        "schema": "academic.course-feedback/v1",
        "deliveries": [{"work": "fase-1", "date": "2026-10-01", "grade": 6.0, "max": 10.0, "comments": []}],
    }


def test_add_delivery_never_overwrites_a_malformed_log(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _work(root)
    course = _course(root, feedback="deliveries: [unclosed\n")
    before = _snapshot(root)

    lines = _run(capsys, str(folder), "--add-delivery", "--date", "2026-11-01", "--grade", "7")

    assert lines == ["warning: feedback.yml malformed: not readable YAML; delivery not recorded"]
    assert _snapshot(root) == before and (course / "feedback.yml").exists()


def test_add_delivery_warns_when_the_log_cannot_be_written(
    root: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _work(root)
    _course(root, feedback=FEEDBACK)

    def denied(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(Path, "write_text", denied)
    lines = _run(capsys, str(folder), "--add-delivery", "--date", "2026-11-01", "--grade", "7")

    assert lines == ["warning: feedback.yml could not be written (PermissionError); delivery not recorded"]


def _plan(folder: Path) -> doc_status.PhaseState:
    return doc_status._phase_plan(folder, _config(folder), None)


def test_plan_warns_when_the_course_rubric_is_not_in_rubric_yml(root: Path) -> None:
    folder = _work(root)
    _rubric(folder)
    _course(root, COURSE_RUBRIC)

    phase = _plan(folder)

    assert phase.state == doc_status.DONE and phase.blocked_reason == ""
    assert phase.detail.endswith(
        f"; warning: the course rubric has 1 criterion (academic-sources/{SLUG}/rubrics/) and rubric.yml has "
        "no teacher criterion; run course_memory.py and add them with origin: teacher"
    )


def test_plan_detail_is_unchanged_without_a_course_rubric(root: Path) -> None:
    folder = _work(root)
    _rubric(folder)

    assert _plan(folder).detail == (
        "rubric.yml valid (2 criteria, 0 with checks); warning: guide-only plan, no teacher rubric "
        "(add the teacher's criteria with origin: teacher, or record teacher_rubric: none once the user "
        "confirms there is none)"
    )


# --- calibration (guide-vs-teacher-rubric T4, S8) ---------------------------

S8 = [("fase-1", 6.0, 7.0), ("fase-2", 9.0, 7.5), ("ape-3", 6.0, 7.5), ("ape-4", 5.0, 6.0), ("ape-5", 8.5, 7.5)]


def test_add_delivery_stores_the_predicted_leveled_grade(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _work(root)
    course = _course(root, feedback=FEEDBACK)

    lines = _run(capsys, str(folder), "--add-delivery", "--date", "2026-11-01", "--grade", "8.5", "--predicted", "7.5")

    assert lines == [f"recorded: ape-1 2026-11-01 8.5/10 (predicted 7.5) in academic-sources/{SLUG}/feedback.yml"]
    data = yaml.safe_load((course / "feedback.yml").read_text(encoding="utf-8"))
    assert data["deliveries"][0] == FEEDBACK["deliveries"][0]
    assert data["deliveries"][1]["predicted"] == 7.5
    bad = _run(capsys, str(folder), "--add-delivery", "--date", "2026-11-02", "--grade", "8", "--predicted", "x")
    assert bad == ["warning: --predicted must be a number (the leveled grade /10); delivery not recorded"]
    assert len(yaml.safe_load((course / "feedback.yml").read_text(encoding="utf-8"))["deliveries"]) == 2


def test_calibration_prints_the_mean_absolute_difference_of_the_redes_u1_case(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _work(root, "ai_declaration: \"Se uso Claude.\"\n")
    deliveries = [{"work": w, "date": "2026-10-01", "grade": g, "max": 10, "comments": [], "predicted": p} for w, g, p in S8]
    deliveries.append({"work": "fase-0", "date": "2026-09-01", "grade": 7.0, "max": 10, "comments": []})
    _course(root, feedback={**FEEDBACK, "deliveries": deliveries})

    lines = _run(capsys, str(folder))

    assert "- fase-2 2026-10-01: 9.0/10 (predicted 7.5)" in lines
    assert "- fase-0 2026-09-01: 7.0/10" in lines
    assert ("calibration: mean absolute difference 1.2/10 between the leveled grade and the teacher's grade "
            "(n=5; orientative, never a gate)") in lines

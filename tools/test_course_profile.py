"""Course profiles: front-matter match, default merge, delivery_dir template."""
from pathlib import Path

import pytest
import yaml

import course_profile
from report_config import load_report_config

PROFILE = """---
match:
  subject: Simulación
report_defaults:
  format: ape
  uncited_bibliography: true
  cover:
    required: false
delivery_dir_template: "/tmp/sim/unidad-{unit}/ape-{practice_number}-{slug}/documento/"
---
Prose body.
"""

REPORT = """# my report
route: academic
metadata:
  title: "Modelo de colas"
  subject: simulacion
  unit: "2"
  practice_number: "3"
"""


def _profiles(tmp_path: Path, *texts: str) -> Path:
    directory = tmp_path / "profiles"
    directory.mkdir()
    for index, text in enumerate(texts):
        (directory / f"p{index}.md").write_text(text, encoding="utf-8")
    return directory


def _folder(tmp_path: Path, text: str = REPORT) -> Path:
    folder = tmp_path / "report"
    folder.mkdir()
    (folder / "report.yml").write_text(text, encoding="utf-8")
    return folder


def _run(folder: Path, profiles: Path, *flags: str) -> int:
    return course_profile.main([str(folder), "--profiles", str(profiles), *flags])


def test_applies_defaults_and_delivery_dir_preserving_comments(tmp_path, capsys):
    folder = _folder(tmp_path)
    assert _run(folder, _profiles(tmp_path, PROFILE)) == 0
    text = (folder / "report.yml").read_text(encoding="utf-8")
    assert text.startswith(REPORT)
    data = yaml.safe_load(text)
    assert data["format"] == "ape" and data["uncited_bibliography"] is True
    assert data["cover"] == {"required": False}
    assert data["delivery_dir"] == "/tmp/sim/unidad-2/ape-3-modelo-de-colas/documento/"
    assert "format" in capsys.readouterr().out


def test_numeric_placeholders_use_the_bare_number(tmp_path):
    report = REPORT.replace('unit: "2"', 'unit: "U1: Introducción a la Simulación"').replace(
        'practice_number: "3"', 'practice_number: "01"')
    folder = _folder(tmp_path, report)
    assert _run(folder, _profiles(tmp_path, PROFILE)) == 0
    data = yaml.safe_load((folder / "report.yml").read_text(encoding="utf-8"))
    assert data["delivery_dir"] == "/tmp/sim/unidad-1/ape-1-modelo-de-colas/documento/"


def test_explicit_report_values_win(tmp_path):
    folder = _folder(tmp_path, REPORT + "format: libre\ncover:\n  required: true\ndelivery_dir: /x\n")
    assert _run(folder, _profiles(tmp_path, PROFILE)) == 0
    data = yaml.safe_load((folder / "report.yml").read_text(encoding="utf-8"))
    assert data["format"] == "libre"
    assert data["cover"] == {"required": True}
    assert data["delivery_dir"] == "/x"
    assert data["uncited_bibliography"] is True


def test_nested_default_is_added_to_existing_block(tmp_path):
    folder = _folder(tmp_path, REPORT + "cover:\n  logo_required: false\n")
    assert _run(folder, _profiles(tmp_path, PROFILE)) == 0
    data = yaml.safe_load((folder / "report.yml").read_text(encoding="utf-8"))
    assert data["cover"] == {"logo_required": False, "required": False}


def test_no_match_prints_no_profile_and_leaves_file(tmp_path, capsys):
    folder = _folder(tmp_path, REPORT.replace("simulacion", "Redes"))
    assert _run(folder, _profiles(tmp_path, PROFILE, "no front matter\n")) == 0
    assert "no profile" in capsys.readouterr().out
    assert (folder / "report.yml").read_text(encoding="utf-8") == REPORT.replace("simulacion", "Redes")


def test_several_matches_is_an_error(tmp_path):
    folder = _folder(tmp_path)
    assert _run(folder, _profiles(tmp_path, PROFILE, PROFILE)) == 2


def test_unresolved_placeholder_leaves_delivery_dir_unset(tmp_path, capsys):
    folder = _folder(tmp_path, REPORT.replace('  unit: "2"\n', ""))
    assert _run(folder, _profiles(tmp_path, PROFILE)) == 0
    data = yaml.safe_load((folder / "report.yml").read_text(encoding="utf-8"))
    assert "delivery_dir" not in data and data["format"] == "ape"
    assert "unit" in capsys.readouterr().out


def test_practice_number_falls_back_to_guide_facts(tmp_path):
    text = REPORT.replace('  practice_number: "3"\n', "") + "guide: guia.txt\n"
    folder = _folder(tmp_path, text)
    (folder / "guia.txt").write_text("Práctico experimental. Práctica Nro. 4", encoding="utf-8")
    assert _run(folder, _profiles(tmp_path, PROFILE)) == 0
    data = yaml.safe_load((folder / "report.yml").read_text(encoding="utf-8"))
    assert data["delivery_dir"].endswith("ape-4-modelo-de-colas/documento/")


def test_check_flag_does_not_write(tmp_path, capsys):
    folder = _folder(tmp_path)
    assert _run(folder, _profiles(tmp_path, PROFILE), "--check") == 0
    assert (folder / "report.yml").read_text(encoding="utf-8") == REPORT
    assert "ape" in capsys.readouterr().out


def test_real_simulacion_profile_applies_valid_keys(tmp_path):
    folder = _folder(tmp_path, REPORT.replace("simulacion", "Simulación"))
    assert course_profile.main([str(folder)]) == 0
    (folder / "sources.bib").touch()  # uncited_bibliography needs the file at build time
    config = load_report_config(folder)
    assert config.format == "ape"
    assert config.uncited_bibliography is True
    assert config.figure_placement == "here"
    assert config.output_format == "pdf"
    assert config.cover_value("required") is False
    assert config.delivery_dir == Path(
        "~/Documents/Academicos/simulacion/unidad-2/ape-3-modelo-de-colas/documento/"
    ).expanduser()


COURSE_REPORT = """route: academic
format: aa
metadata:
  title: "Análisis de actores y fundamentos de Spec-Driven Development"
  subject: "Desarrollo Basado en Plataformas"
  unit: "Unidad 1"
  practice_number: "1"
  topic: "actores-sdd"
"""


def _course_repo(tmp_path: Path) -> Path:
    documents = tmp_path / "Documents"
    repo = documents / "Academicos" / "desarrollo-basado-en-plataformas"
    repo.mkdir(parents=True)
    (repo / "AGENTS.md").write_text("- `unidad-<n>/<tipo>-<m>-<tema>/`\n", encoding="utf-8")
    return documents


def _run_docs(folder: Path, profiles: Path, documents: Path, *flags: str) -> int:
    return course_profile.main(
        [str(folder), "--profiles", str(profiles), "--documents-root", str(documents), *flags]
    )


def test_course_repo_convention_sets_delivery_dir_without_a_profile(tmp_path, capsys):
    documents = _course_repo(tmp_path)
    folder = _folder(tmp_path, COURSE_REPORT)

    assert _run_docs(folder, _profiles(tmp_path), documents) == 0

    data = yaml.safe_load((folder / "report.yml").read_text(encoding="utf-8"))
    expected = documents / "Academicos/desarrollo-basado-en-plataformas/unidad-1/aa-1-actores-sdd/documento"
    assert data["delivery_dir"] == f"{expected}/"
    assert "delivery_dir" in capsys.readouterr().out


def test_course_repo_convention_names_the_missing_fields(tmp_path, capsys):
    documents = _course_repo(tmp_path)
    text = COURSE_REPORT.replace('  topic: "actores-sdd"\n', "")
    folder = _folder(tmp_path, text)

    assert _run_docs(folder, _profiles(tmp_path), documents) == 0

    assert (folder / "report.yml").read_text(encoding="utf-8") == text
    assert "topic" in capsys.readouterr().out


def test_without_a_course_repo_nothing_is_applied(tmp_path, capsys):
    documents = tmp_path / "Documents"
    documents.mkdir()
    folder = _folder(tmp_path, COURSE_REPORT)

    assert _run_docs(folder, _profiles(tmp_path), documents) == 0

    assert (folder / "report.yml").read_text(encoding="utf-8") == COURSE_REPORT
    assert "no profile" in capsys.readouterr().out


def test_course_repo_convention_accepts_an_uppercase_format(tmp_path):
    documents = _course_repo(tmp_path)
    folder = _folder(tmp_path, COURSE_REPORT.replace("format: aa", "format: AA"))

    assert _run_docs(folder, _profiles(tmp_path), documents) == 0

    data = yaml.safe_load((folder / "report.yml").read_text(encoding="utf-8"))
    assert "/unidad-1/aa-1-actores-sdd/documento/" in data["delivery_dir"]


def _practice_folder(documents: Path, relative: str) -> None:
    (documents / "Academicos" / "desarrollo-basado-en-plataformas" / relative).mkdir(parents=True)


def _proposed(folder: Path) -> str:
    return yaml.safe_load((folder / "report.yml").read_text(encoding="utf-8"))["delivery_dir"]


def test_course_folder_uses_the_practice_type_its_existing_folders_use(tmp_path):
    """#84: a course that names practices `ejercicio-N-...` never gets `aa-N-...`."""
    documents = _course_repo(tmp_path)
    _practice_folder(documents, "unidad-1/ejercicio-1-introduccion")
    folder = _folder(tmp_path, COURSE_REPORT.replace('practice_number: "1"', 'practice_number: "2"'))

    assert _run_docs(folder, _profiles(tmp_path), documents) == 0

    assert _proposed(folder).endswith("/unidad-1/ejercicio-2-actores-sdd/documento/")


def test_course_folder_reuses_the_existing_folder_of_the_same_practice(tmp_path):
    """#84: the practice folder already exists under another topic: deliver there."""
    documents = _course_repo(tmp_path)
    _practice_folder(documents, "unidad-1/ejercicio-1-introduccion")
    _practice_folder(documents, "unidad-1/ejercicio-2-series-taylor-cap4")
    folder = _folder(tmp_path, COURSE_REPORT.replace('practice_number: "1"', 'practice_number: "2"'))

    assert _run_docs(folder, _profiles(tmp_path), documents) == 0

    assert _proposed(folder).endswith("/unidad-1/ejercicio-2-series-taylor-cap4/documento/")


def test_course_folder_keeps_the_format_when_the_course_already_uses_it(tmp_path):
    documents = _course_repo(tmp_path)
    _practice_folder(documents, "unidad-1/ejercicio-1-introduccion")
    _practice_folder(documents, "unidad-1/aa-2-otro-tema")
    folder = _folder(tmp_path, COURSE_REPORT.replace('practice_number: "1"', 'practice_number: "3"'))

    assert _run_docs(folder, _profiles(tmp_path), documents) == 0

    assert _proposed(folder).endswith("/unidad-1/aa-3-actores-sdd/documento/")


def test_profile_without_a_template_takes_the_course_folder_too(tmp_path, capsys):
    """#72.4: a profile with only report_defaults still gets the course repo layout."""
    documents = _course_repo(tmp_path)
    profile = """---
match:
  subject: Desarrollo Basado en Plataformas
report_defaults:
  uncited_bibliography: true
---
"""
    folder = _folder(tmp_path, COURSE_REPORT)

    assert _run_docs(folder, _profiles(tmp_path, profile), documents) == 0

    data = _proposed(folder)
    report = yaml.safe_load((folder / "report.yml").read_text(encoding="utf-8"))
    assert data.endswith("/unidad-1/aa-1-actores-sdd/documento/")
    assert report["uncited_bibliography"] is True
    assert "profile p0.md" in capsys.readouterr().out


def test_another_practice_format_is_never_taken_as_the_course_type(tmp_path):
    """An AA report in a course with only APE folders stays `aa`, never `ape`."""
    documents = _course_repo(tmp_path)
    _practice_folder(documents, "unidad-1/ape-1-laboratorio")

    folder = _folder(tmp_path, COURSE_REPORT.replace('practice_number: "1"', 'practice_number: "2"'))

    assert _run_docs(folder, _profiles(tmp_path), documents) == 0

    assert _proposed(folder).endswith("/unidad-1/aa-2-actores-sdd/documento/")


def test_an_aa_report_is_never_moved_into_an_ape_folder_of_the_same_number(tmp_path):
    """Review R3-reuse-other-format-folder: reuse matches the report's own type only."""
    documents = _course_repo(tmp_path)
    _practice_folder(documents, "unidad-1/ape-1-laboratorio")
    folder = _folder(tmp_path, COURSE_REPORT)

    assert _run_docs(folder, _profiles(tmp_path), documents) == 0

    assert _proposed(folder).endswith("/unidad-1/aa-1-actores-sdd/documento/")


def test_a_reused_folder_ends_with_the_layout_s_document_folder(tmp_path, monkeypatch):
    """Review R2-reused-folder-hardcoded-suffix: the reuse path follows COURSE_LAYOUT."""
    monkeypatch.setattr(course_profile, "COURSE_DOCUMENT_DIR", "entrega/")
    monkeypatch.setattr(
        course_profile,
        "COURSE_LAYOUT",
        "unidad-{unit}/{practice_type}-{practice_number}-{topic}/entrega/",
    )
    documents = _course_repo(tmp_path)
    _practice_folder(documents, "unidad-1/aa-1-otro-nombre")
    folder = _folder(tmp_path, COURSE_REPORT)

    assert _run_docs(folder, _profiles(tmp_path), documents) == 0

    assert _proposed(folder).endswith("/unidad-1/aa-1-otro-nombre/entrega/")


def test_an_acd_report_gets_an_acd_practice_folder(tmp_path):
    documents = _course_repo(tmp_path)
    folder = _folder(
        tmp_path,
        COURSE_REPORT.replace("format: aa", "format: acd").replace('practice_number: "1"', 'practice_number: "4"'),
    )

    assert _run_docs(folder, _profiles(tmp_path), documents) == 0

    assert _proposed(folder).endswith("/unidad-1/acd-4-actores-sdd/documento/")


def test_an_acd_report_is_never_moved_into_an_aa_folder_of_the_same_number(tmp_path):
    documents = _course_repo(tmp_path)
    _practice_folder(documents, "unidad-1/aa-4-otro-tema")
    folder = _folder(
        tmp_path,
        COURSE_REPORT.replace("format: aa", "format: acd").replace('practice_number: "1"', 'practice_number: "4"'),
    )

    assert _run_docs(folder, _profiles(tmp_path), documents) == 0

    assert _proposed(folder).endswith("/unidad-1/acd-4-actores-sdd/documento/")


def test_min_sources_in_report_yml_keeps_uncited_bibliography_out(tmp_path):
    folder = _folder(tmp_path, REPORT.replace("simulacion", "Simulación") + "min_sources: 3\n")
    assert course_profile.main([str(folder)]) == 0
    text = (folder / "report.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert "uncited_bibliography" not in data and data["min_sources"] == 3
    assert data["format"] == "ape" and data["figure_placement"] == "here"
    assert data["cover"] == {"required": False}
    assert "delivery_dir" in data
    config = load_report_config(folder)
    assert config.min_sources == 3 and config.uncited_bibliography is False


def test_without_min_sources_the_profile_still_adds_uncited_bibliography(tmp_path):
    folder = _folder(tmp_path)
    assert _run(folder, _profiles(tmp_path, PROFILE)) == 0
    assert yaml.safe_load((folder / "report.yml").read_text(encoding="utf-8"))["uncited_bibliography"] is True

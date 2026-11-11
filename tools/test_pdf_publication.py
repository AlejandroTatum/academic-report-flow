"""Tests for where compile_latex() puts the finished PDF.

The final copy used to assume the build output and the configured ``pdf:``
destination were always distinct files. They are not: once reports were told to
keep final artifacts out of ``reports/<work>/outputs/``, pointing ``pdf:`` at
the build output itself became the obvious thing to write — and
``shutil.copy2`` raises ``SameFileError`` for a self-copy, so the build died
*after* successfully producing the PDF.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import types
from pathlib import Path

import publish_pdf
from conftest import _approval, _bibliography, _final_review

import pytest

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import build_latex_report  # noqa: E402


def _config(tmp_path: Path, pdf_path: Path | None = None) -> types.SimpleNamespace:
    folder = tmp_path / "report"
    build_dir = folder / "build"
    build_dir.mkdir(parents=True)
    body_path = folder / "body.md"
    body_path.write_text("# Titulo\n\nTexto.\n", encoding="utf-8")
    (build_dir / "main.tex").write_text("% tex", encoding="utf-8")
    return types.SimpleNamespace(
        folder=folder,
        body_path=body_path,
        tex_path=build_dir / "main.tex",
        pdf_path=pdf_path if pdf_path is not None else folder / "entrega" / "informe.pdf",
        bib_path=None,
        publish_global=False,
        metadata={},
    )


def _compiler_that_writes_the_pdf(build_dir: Path):
    def fake_run(*args, **kwargs):
        (build_dir / "main.pdf").write_bytes(b"%PDF-1.5\ncontenido\n")
        return subprocess.CompletedProcess(args=list(args[0]), returncode=0, stdout="")

    return fake_run


@pytest.fixture
def docker_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        build_latex_report.shutil,
        "which",
        lambda name: "/usr/bin/docker" if name == "docker" else None,
    )


def test_pdf_pointing_at_the_build_output_is_not_a_self_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, docker_engine: None
) -> None:
    """``pdf: build/main.pdf`` must publish, not crash on SameFileError."""
    config = _config(tmp_path)
    build_dir = config.tex_path.parent
    config.pdf_path = build_dir / "main.pdf"
    monkeypatch.setattr(build_latex_report, "run", _compiler_that_writes_the_pdf(build_dir))

    build_latex_report.compile_latex(config)

    assert config.pdf_path.exists()
    assert config.pdf_path.read_bytes().startswith(b"%PDF")


def test_pdf_reached_through_a_symlinked_build_dir_is_still_the_same_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, docker_engine: None
) -> None:
    """Sameness is about the file on disk, not about matching path strings."""
    config = _config(tmp_path)
    build_dir = config.tex_path.parent
    monkeypatch.setattr(build_latex_report, "run", _compiler_that_writes_the_pdf(build_dir))

    link = tmp_path / "atajo"
    link.symlink_to(build_dir, target_is_directory=True)
    config.pdf_path = link / "main.pdf"

    build_latex_report.compile_latex(config)

    assert (build_dir / "main.pdf").read_bytes().startswith(b"%PDF")


def test_distinct_destination_still_receives_a_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, docker_engine: None
) -> None:
    """The ordinary case must keep working: build output copied to pdf_path."""
    config = _config(tmp_path)
    build_dir = config.tex_path.parent
    monkeypatch.setattr(build_latex_report, "run", _compiler_that_writes_the_pdf(build_dir))

    build_latex_report.compile_latex(config)

    assert config.pdf_path.exists()
    assert config.pdf_path != build_dir / "main.pdf"
    assert config.pdf_path.read_bytes() == (build_dir / "main.pdf").read_bytes()


DEFAULT_VALIDATED_CONTENT = b"%PDF-1.7\nvalidated content\n"


def _validated_pdf(
    tmp_path: Path, content: bytes = DEFAULT_VALIDATED_CONTENT, *, final_review: bool = True
) -> Path:
    source = tmp_path / "work" / "validated.pdf"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    approved = tmp_path / "approved"
    if final_review and (approved / "approval.yml").is_file():
        # The publication gate also requires a final-review marker bound to the
        # exact bytes being published; every ordinary publication path gets one.
        _final_review(approved, pdf=source)
    return source


@pytest.fixture
def _approved_work_folder(tmp_path: Path) -> Path:
    """A work folder whose approval.yml records the current body.md hash.

    Publication is gated on this marker (plus the final-review marker the
    publishing helpers write for the exact source bytes), so every pre-existing
    publication assertion proves the ordinary, approved path still behaves
    exactly as it did before the guards existed.
    """
    folder = tmp_path / "approved"
    _approval(folder)
    return folder


def test_first_publication_is_v001_pdf_only_and_hash_verified(
    tmp_path: Path, _approved_work_folder: Path
) -> None:
    source = _validated_pdf(tmp_path)
    documents = tmp_path / "Documents"

    published = publish_pdf.publish_validated_pdf(
        source, "Tecnicos", "informe", documents, work_folder=_approved_work_folder
    )

    assert published.path == documents / "Tecnicos" / "informe" / "informe-v001.pdf"
    assert published.created is True
    assert published.path.exists()
    assert published.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert list(published.path.parent.iterdir()) == [published.path]


def test_unchanged_hash_reuses_existing_version(
    tmp_path: Path, _approved_work_folder: Path
) -> None:
    source = _validated_pdf(tmp_path)
    documents = tmp_path / "Documents"
    first = publish_pdf.publish_validated_pdf(
        source, "Tecnicos", "informe", documents, work_folder=_approved_work_folder
    )

    reused = publish_pdf.publish_validated_pdf(
        source, "Tecnicos", "informe", documents, work_folder=_approved_work_folder
    )

    assert reused.path == first.path
    assert reused.created is False
    assert list(first.path.parent.glob("*.pdf")) == [first.path]


def test_changed_hash_publishes_next_monotonic_version(
    tmp_path: Path, _approved_work_folder: Path
) -> None:
    source = _validated_pdf(tmp_path, b"%PDF-1.7\nfirst\n")
    documents = tmp_path / "Documents"
    publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents, work_folder=_approved_work_folder
    )
    source.write_bytes(b"%PDF-1.7\nsecond\n")
    _final_review(_approved_work_folder, pdf=source)

    published = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents, work_folder=_approved_work_folder
    )

    assert published.path.name == "informe-v002.pdf"
    assert published.path.read_bytes() == source.read_bytes()
    assert {path.name for path in published.path.parent.iterdir()} == {"informe-v001.pdf", "informe-v002.pdf"}


def test_concurrent_version_claim_retries_without_overwriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _approved_work_folder: Path
) -> None:
    source = _validated_pdf(tmp_path, b"%PDF-1.7\nsecond publisher\n")
    documents = tmp_path / "Documents"
    folder = documents / "Tecnicos" / "informe"
    folder.mkdir(parents=True)
    (folder / "informe-v001.pdf").write_bytes(b"%PDF-1.7\nfirst publisher\n")
    real_link = publish_pdf.os.link
    calls = 0

    def collision_once(source_path, destination_path):
        nonlocal calls
        calls += 1
        if calls == 1:
            Path(destination_path).write_bytes(b"%PDF-1.7\nconcurrent publisher\n")
            raise FileExistsError
        return real_link(source_path, destination_path)

    monkeypatch.setattr(publish_pdf.os, "link", collision_once)

    published = publish_pdf.publish_validated_pdf(
        source, "Tecnicos", "informe", documents, work_folder=_approved_work_folder
    )

    assert published.path.name == "informe-v003.pdf"
    assert (folder / "informe-v002.pdf").read_bytes() == b"%PDF-1.7\nconcurrent publisher\n"


def test_publication_rejects_non_pdf_source_and_non_pdf_output_folder_contents(
    tmp_path: Path, _approved_work_folder: Path
) -> None:
    source = tmp_path / "validated.docx"
    source.write_bytes(b"not a pdf")
    documents = tmp_path / "Documents"

    with pytest.raises(publish_pdf.PublicationError):
        publish_pdf.publish_validated_pdf(
            source, "Tecnicos", "informe", documents, work_folder=_approved_work_folder
        )

    source = _validated_pdf(tmp_path)
    destination = documents / "Tecnicos" / "informe"
    destination.mkdir(parents=True)
    (destination / "audit.txt").write_text("not a PDF", encoding="utf-8")
    with pytest.raises(publish_pdf.PublicationError):
        publish_pdf.publish_validated_pdf(
            source, "Tecnicos", "informe", documents, work_folder=_approved_work_folder
        )


def test_publish_refuses_absent_stale_malformed_marker(
    tmp_path: Path, _approved_work_folder: Path
) -> None:
    """Publication is fail-closed: without a current marker nothing is created.

    The guard must run before sha256_file, folder.mkdir and any temp file, so a
    refused publication leaves no directory and no partial copy anywhere.
    """
    source = _validated_pdf(tmp_path)
    documents = tmp_path / "Documents"

    # absent — a v1 work folder (S2: no draft approval) still needs the
    # generated artifact identity of the exact PDF
    absent = tmp_path / "absent"
    absent.mkdir()
    with pytest.raises(publish_pdf.PublicationError, match="identidad del PDF generado"):
        publish_pdf.publish_validated_pdf(
            source, "Tecnicos", "informe", documents, work_folder=absent
        )
    assert not documents.exists()

    # stale — the body changed after the human approved it
    (_approved_work_folder / "body.md").write_text(
        "edited after approval\n", encoding="utf-8"
    )
    with pytest.raises(publish_pdf.PublicationError, match="obsoleta"):
        publish_pdf.publish_validated_pdf(
            source, "Tecnicos", "informe", documents, work_folder=_approved_work_folder
        )
    assert not documents.exists()

    # malformed — the marker cannot be read as a valid approval record
    malformed = tmp_path / "malformed"
    malformed.mkdir()
    (malformed / "preview.md").write_text("# Content Preview: Informe\n", encoding="utf-8")
    (malformed / "approval.yml").write_text("preview_sha256: [unclosed\n", encoding="utf-8")
    with pytest.raises(publish_pdf.PublicationError, match="inválido"):
        publish_pdf.publish_validated_pdf(
            source, "Tecnicos", "informe", documents, work_folder=malformed
        )
    assert not documents.exists()


def test_publish_refuses_without_current_final_review(
    tmp_path: Path, _approved_work_folder: Path
) -> None:
    """A current approval is not enough: the PDF needs a current final review too.

    The gate is fail-closed like the approval gate: the refusal runs before any
    hash, directory or temporary file, so a refused publication creates nothing.
    """
    documents = tmp_path / "Documents"

    # absent — the human never reviewed the final PDF
    absent_source = _validated_pdf(tmp_path, final_review=False)
    with pytest.raises(publish_pdf.PublicationError, match="Falta la revisión humana final"):
        publish_pdf.publish_validated_pdf(
            absent_source, "Tecnicos", "informe", documents, work_folder=_approved_work_folder
        )
    assert not documents.exists()

    # stale — the PDF was rebuilt after the human reviewed it
    stale_source = _validated_pdf(tmp_path)
    stale_source.write_bytes(b"%PDF-1.7\nrebuilt after review\n")
    with pytest.raises(publish_pdf.PublicationError, match="revisión final está obsoleta"):
        publish_pdf.publish_validated_pdf(
            stale_source, "Tecnicos", "informe", documents, work_folder=_approved_work_folder
        )
    assert not documents.exists()

    # malformed — the marker cannot be read as a valid final-review record
    malformed_source = _validated_pdf(tmp_path)
    (_approved_work_folder / "final-review.yml").write_text("pdf_sha256: [unclosed\n", encoding="utf-8")
    with pytest.raises(publish_pdf.PublicationError, match="final-review.yml es inválido"):
        publish_pdf.publish_validated_pdf(
            malformed_source, "Tecnicos", "informe", documents, work_folder=_approved_work_folder
        )
    assert not documents.exists()


def test_refusal_messages_match_design_verbatim(
    tmp_path: Path, _approved_work_folder: Path
) -> None:
    """The three Spanish refusals are a fixed contract, not ad-hoc prose.

    ``build_report_auto.py`` prefixes them with ``PDF PUBLICATION FAILED:``; the
    wording must stay stable so the operator sees the same diagnosis at every
    entry point.
    """
    source = _validated_pdf(tmp_path)
    documents = tmp_path / "Documents"

    absent = tmp_path / "absent-message"
    absent.mkdir()
    with pytest.raises(publish_pdf.PublicationError) as exc:
        publish_pdf.publish_validated_pdf(
            source, "Tecnicos", "informe", documents, work_folder=absent
        )
    # S2: without approval.yml the report is a v1; the refusal names the
    # missing generated artifact identity instead of a draft approval.
    assert str(exc.value) == (
        "Falta o está obsoleta la identidad del PDF generado y sus entradas; "
        "volvé a generar y validar antes de publicar. No se publica nada."
    )

    (_approved_work_folder / "body.md").write_text("edited\n", encoding="utf-8")
    with pytest.raises(publish_pdf.PublicationError) as exc:
        publish_pdf.publish_validated_pdf(
            source, "Tecnicos", "informe", documents, work_folder=_approved_work_folder
        )
    assert str(exc.value) == (
        "La aprobación está obsoleta: body_sha256 de "
        f"approval.yml no coincide con body.md en {_approved_work_folder}. "
        "Volvé a aprobar el cuerpo actual; no se publica nada."
    )

    malformed = tmp_path / "malformed-message"
    malformed.mkdir()
    (malformed / "preview.md").write_text("# Content Preview: Informe\n", encoding="utf-8")
    (malformed / "approval.yml").write_text("preview_sha256: [unclosed\n", encoding="utf-8")
    with pytest.raises(publish_pdf.PublicationError) as exc:
        publish_pdf.publish_validated_pdf(
            source, "Tecnicos", "informe", documents, work_folder=malformed
        )
    assert str(exc.value) == (
        f"approval.yml es inválido en {malformed}: approval.yml is not valid YAML. "
        "No se publica nada y el marcador nunca se repara automáticamente."
    )


def test_global_publication_still_runs_when_the_pdf_is_the_build_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, docker_engine: None
) -> None:
    """Skipping the copy must not skip publishing the visible per-subject copy."""
    config = _config(tmp_path)
    build_dir = config.tex_path.parent
    config.pdf_path = build_dir / "main.pdf"
    config.publish_global = True
    config.metadata = {"subject": "Sistemas Operativos"}
    monkeypatch.setattr(build_latex_report, "run", _compiler_that_writes_the_pdf(build_dir))

    published: list[Path] = []
    monkeypatch.setattr(
        build_latex_report,
        "publish_global_output",
        lambda pdf, metadata: published.append(Path(pdf)) or Path(pdf),
    )

    build_latex_report.compile_latex(config)

    assert published == [config.pdf_path]


# ---------------------------------------------------------------------------
# Subject-scoped academic publication (course-deliverables-hierarchy T1)
# ---------------------------------------------------------------------------


def test_subject_scoped_publication_lands_under_the_subject_folder(
    tmp_path: Path, _approved_work_folder: Path
) -> None:
    """The optional course/subject level scopes the academic document folder."""
    source = _validated_pdf(tmp_path)
    documents = tmp_path / "Documents"

    published = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents,
        work_folder=_approved_work_folder, subject="sistemas-operativos",
    )

    assert published.path == (
        documents / "Academicos" / "sistemas-operativos" / "informe" / "informe-v001.pdf"
    )
    assert published.created is True
    assert published.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()


def test_subject_scoped_reuse_and_next_version_stay_in_the_subject_folder(
    tmp_path: Path, _approved_work_folder: Path
) -> None:
    """Hash reuse and the monotonic next version operate inside the subject folder."""
    source = _validated_pdf(tmp_path)
    documents = tmp_path / "Documents"

    first = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents,
        work_folder=_approved_work_folder, subject="sistemas-operativos",
    )
    reused = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents,
        work_folder=_approved_work_folder, subject="sistemas-operativos",
    )
    assert reused.path == first.path and reused.created is False

    source.write_bytes(b"%PDF-1.7\nsecond\n")
    _final_review(_approved_work_folder, pdf=source)
    second = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents,
        work_folder=_approved_work_folder, subject="sistemas-operativos",
    )

    assert second.path.name == "informe-v002.pdf"
    assert second.path.parent == first.path.parent
    assert {p.name for p in second.path.parent.iterdir()} == {"informe-v001.pdf", "informe-v002.pdf"}


def test_readme_in_the_delivery_folder_is_allowed_and_left_untouched(
    tmp_path: Path, _approved_work_folder: Path
) -> None:
    """The course-repo template ships documento/README.md; delivery keeps it as is."""
    source = _validated_pdf(tmp_path)
    destination = tmp_path / "curso" / "documento"
    destination.mkdir(parents=True)
    readme = destination / "README.md"
    readme.write_text("Aquí va el informe entregado en PDF.\n", encoding="utf-8")

    first = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", None,
        work_folder=_approved_work_folder, destination=destination,
    )
    source.write_bytes(b"%PDF-1.7\nsecond\n")
    _final_review(_approved_work_folder, pdf=source)
    second = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", None,
        work_folder=_approved_work_folder, destination=destination,
    )

    assert (first.path.name, second.path.name) == ("informe-v001.pdf", "informe-v002.pdf")
    assert readme.read_text(encoding="utf-8") == "Aquí va el informe entregado en PDF.\n"
    assert publish_pdf.scan_delivery_versions(destination, "informe")[0][0] == 1


def test_readme_does_not_excuse_another_foreign_file(tmp_path: Path) -> None:
    folder = tmp_path / "documento"
    folder.mkdir()
    (folder / "README.md").write_text("x", encoding="utf-8")
    (folder / "notas.txt").write_text("x", encoding="utf-8")

    with pytest.raises(publish_pdf.PublicationError, match="solo puede contener"):
        publish_pdf.scan_delivery_versions(folder, "informe")


def test_only_an_exact_regular_readme_md_is_allowed(tmp_path: Path) -> None:
    for name in ("readme.md", "README.MD", "README.md.bak"):
        folder = tmp_path / name.replace(".", "_")
        folder.mkdir()
        (folder / name).write_text("x", encoding="utf-8")
        with pytest.raises(publish_pdf.PublicationError, match="solo puede contener"):
            publish_pdf.scan_delivery_versions(folder, "informe")
    as_directory = tmp_path / "dir"
    (as_directory / "README.md").mkdir(parents=True)
    with pytest.raises(publish_pdf.PublicationError, match="solo puede contener"):
        publish_pdf.scan_delivery_versions(as_directory, "informe")


def test_gate_refusal_creates_nothing_not_even_the_subject_folder(
    tmp_path: Path,
) -> None:
    """A refused publication must not create the subject level either."""
    source = _validated_pdf(tmp_path)
    documents = tmp_path / "Documents"
    absent = tmp_path / "absent"
    absent.mkdir()

    with pytest.raises(publish_pdf.PublicationError, match="identidad del PDF generado"):
        publish_pdf.publish_validated_pdf(
            source, "Academicos", "informe", documents,
            work_folder=absent, subject="sistemas-operativos",
        )

    assert not documents.exists()


def test_git_metadata_at_the_course_root_coexists_with_publication(
    tmp_path: Path, _approved_work_folder: Path
) -> None:
    """A course folder that is the user's Git repo must not block publication.

    Git metadata lives at the course root, above the per-document folder; the
    publisher never touches it and never creates a repo itself.
    """
    source = _validated_pdf(tmp_path)
    documents = tmp_path / "Documents"
    course_root = documents / "Academicos" / "sistemas-operativos"
    (course_root / ".git" / "objects").mkdir(parents=True)
    (course_root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (course_root / ".git" / "objects" / "packed-objects").write_bytes(b"git\n")

    published = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents,
        work_folder=_approved_work_folder, subject="sistemas-operativos",
    )

    assert published.path.is_file()
    assert (course_root / ".git" / "HEAD").read_text(encoding="utf-8") == "ref: refs/heads/main\n"
    assert (course_root / ".git" / "objects" / "packed-objects").read_bytes() == b"git\n"


def test_document_folder_stays_pdf_only_even_for_git_metadata(
    tmp_path: Path, _approved_work_folder: Path
) -> None:
    """Per-document folders remain PDF-only: a .git inside one still refuses."""
    source = _validated_pdf(tmp_path)
    documents = tmp_path / "Documents"
    destination = documents / "Academicos" / "sistemas-operativos" / "informe"
    (destination / ".git").mkdir(parents=True)

    with pytest.raises(publish_pdf.PublicationError, match="solo puede contener"):
        publish_pdf.publish_validated_pdf(
            source, "Academicos", "informe", documents,
            work_folder=_approved_work_folder, subject="sistemas-operativos",
        )


# ---------------------------------------------------------------------------
# Declared bibliography pair publication (course-deliverables-hierarchy T2)
# ---------------------------------------------------------------------------


def _pair_folder(tmp_path: Path) -> tuple[Path, Path]:
    """An approved work folder plus its declared bibliography source."""
    work = tmp_path / "approved"
    _approval(work)
    bib = _bibliography(work)
    return work, bib


def test_opted_in_pair_publishes_versioned_pair_with_exact_names_and_hashes(
    tmp_path: Path,
) -> None:
    """A declared bibliography ships as the same-version <slug>-vNNN.bib pair."""
    source = _validated_pdf(tmp_path)
    work, bib = _pair_folder(tmp_path)
    _final_review(work, pdf=source, bibliography=bib)
    documents = tmp_path / "Documents"

    published = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents,
        work_folder=work, subject="sistemas-operativos", bibliography=bib,
    )

    folder = documents / "Academicos" / "sistemas-operativos" / "informe"
    assert published.path == folder / "informe-v001.pdf"
    pair = folder / "informe-v001.bib"
    assert pair.is_file()
    assert pair.read_bytes() == bib.read_bytes()
    assert published.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()


def test_pair_reuse_and_set_switching_claim_new_versions(tmp_path: Path) -> None:
    """Reuse matches the complete requested set; any set change claims a version."""
    source = _validated_pdf(tmp_path)
    work, bib = _pair_folder(tmp_path)
    _final_review(work, pdf=source, bibliography=bib)
    documents = tmp_path / "Documents"
    kwargs = dict(work_folder=work, subject="sistemas-operativos")

    first = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents, bibliography=bib, **kwargs
    )
    reused = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents, bibliography=bib, **kwargs
    )
    assert reused.path == first.path and reused.created is False

    # Same PDF, changed bibliography: the old pair must never be reused.
    bib.write_text('@book{bib1, title = "CHANGED"}\n', encoding="utf-8")
    _final_review(work, pdf=source, bibliography=bib)
    second = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents, bibliography=bib, **kwargs
    )
    assert second.path.name == "informe-v002.pdf"
    assert (second.path.parent / "informe-v002.bib").read_bytes() == bib.read_bytes()

    # Switching to PDF-only is a different set: it claims its own version.
    third = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents, **kwargs
    )
    assert third.path.name == "informe-v003.pdf"
    assert not (third.path.parent / "informe-v003.bib").exists()

    # Switching back to the exact v002 set is a complete-set reuse, never v003.
    fourth = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents, bibliography=bib, **kwargs
    )
    assert fourth.path == second.path and fourth.created is False


def test_pair_refusals_happen_before_destination_creation(tmp_path: Path) -> None:
    """Missing sources and unbound human evidence refuse without creating anything."""
    source = _validated_pdf(tmp_path)
    documents = tmp_path / "Documents"
    work, bib = _pair_folder(tmp_path)
    kwargs = dict(work_folder=work, subject="sistemas-operativos", bibliography=bib)

    # The declared source disappeared before publication.
    bib.unlink()
    with pytest.raises(publish_pdf.PublicationError, match="bibliograf"):
        publish_pdf.publish_validated_pdf(
            source, "Academicos", "informe", documents, **kwargs
        )
    assert not documents.exists()

    # The final review never bound the declared bibliography bytes.
    bib.write_text('@book{bib1, title = "Bib Title 1", author = "Autor 1"}\n', encoding="utf-8")
    _final_review(work, pdf=source)
    with pytest.raises(publish_pdf.PublicationError, match="bibliography_sha256|revisi[nu]n"):
        publish_pdf.publish_validated_pdf(
            source, "Academicos", "informe", documents, **kwargs
        )
    assert not documents.exists()


def test_delivery_folder_allows_only_versioned_final_artifacts(tmp_path: Path) -> None:
    """Stray work files refuse; a .bib without its paired PDF refuses too."""
    source = _validated_pdf(tmp_path)
    work, bib = _pair_folder(tmp_path)
    _final_review(work, pdf=source, bibliography=bib)
    documents = tmp_path / "Documents"
    folder = documents / "Academicos" / "informe"
    folder.mkdir(parents=True)
    (folder / "audit.txt").write_text("work file", encoding="utf-8")
    kwargs = dict(work_folder=work, subject=None, bibliography=bib)

    with pytest.raises(publish_pdf.PublicationError, match="solo puede contener"):
        publish_pdf.publish_validated_pdf(
            source, "Academicos", "informe", documents, **kwargs
        )

    (folder / "audit.txt").unlink()
    (folder / "informe-v001.bib").write_bytes(bib.read_bytes())
    with pytest.raises(publish_pdf.PublicationError, match="sin su PDF emparejado"):
        publish_pdf.publish_validated_pdf(
            source, "Academicos", "informe", documents, **kwargs
        )


def test_interrupted_pair_claim_cleans_only_its_own_partial_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failure between the two claims removes this call's files, nothing else."""
    source = _validated_pdf(tmp_path)
    work, bib = _pair_folder(tmp_path)
    _final_review(work, pdf=source, bibliography=bib)
    documents = tmp_path / "Documents"
    real_link = publish_pdf.os.link
    pdf_name = "informe-v001.pdf"

    def fail_on_bib(source_path, destination_path):
        if Path(destination_path).name.endswith(".bib"):
            raise OSError("disk full")
        return real_link(source_path, destination_path)

    monkeypatch.setattr(publish_pdf.os, "link", fail_on_bib)
    with pytest.raises(publish_pdf.PublicationError, match="No se pudo publicar"):
        publish_pdf.publish_validated_pdf(
            source, "Academicos", "informe", documents,
            work_folder=work, bibliography=bib,
        )

    folder = documents / "Academicos" / "informe"
    assert not (folder / pdf_name).exists(), "the claimed PDF of a broken pair must be removed"
    assert sorted(path.name for path in folder.iterdir()) == [], "no partial files may remain"

    # An earlier complete delivery is never touched by a later failed call.
    monkeypatch.setattr(publish_pdf.os, "link", real_link)
    first = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents, work_folder=work, bibliography=bib,
    )
    assert first.path.is_file() and (first.path.parent / "informe-v001.bib").is_file()


def test_concurrent_pair_claim_retries_without_overwriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lost version race retries with a fresh scan instead of overwriting."""
    source = _validated_pdf(tmp_path)
    work, bib = _pair_folder(tmp_path)
    _final_review(work, pdf=source, bibliography=bib)
    documents = tmp_path / "Documents"
    folder = documents / "Academicos" / "informe"
    folder.mkdir(parents=True)
    (folder / "informe-v001.pdf").write_bytes(b"%PDF-1.7\nfirst publisher\n")
    real_link = publish_pdf.os.link
    calls = 0

    def collision_once(source_path, destination_path):
        nonlocal calls
        calls += 1
        if calls == 1:
            Path(destination_path).write_bytes(b"%PDF-1.7\nconcurrent publisher\n")
            raise FileExistsError
        return real_link(source_path, destination_path)

    monkeypatch.setattr(publish_pdf.os, "link", collision_once)
    published = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents, work_folder=work, bibliography=bib,
    )

    assert published.path.name == "informe-v003.pdf"
    assert (folder / "informe-v002.pdf").read_bytes() == b"%PDF-1.7\nconcurrent publisher\n"
    assert not (folder / "informe-v002.bib").exists(), "the lost racer never claimed a bib"
    assert (folder / "informe-v003.bib").read_bytes() == bib.read_bytes()


def test_destination_override_publishes_into_exactly_that_folder(
    tmp_path: Path, _approved_work_folder: Path
) -> None:
    """An explicit destination replaces the Documents layout and keeps the register."""
    source = _validated_pdf(tmp_path)
    documents = tmp_path / "Documents"
    target = tmp_path / "course" / "unidad-1" / "ape-1" / "documento"

    first = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents,
        work_folder=_approved_work_folder, subject="fisica", destination=target,
    )
    reused = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents,
        work_folder=_approved_work_folder, destination=target,
    )
    assert first.path == target / "informe-v001.pdf" and first.created is True
    assert reused.path == first.path and reused.created is False

    source.write_bytes(b"%PDF-1.7\nsecond\n")
    _final_review(_approved_work_folder, pdf=source)
    second = publish_pdf.publish_validated_pdf(
        source, "Academicos", "informe", documents,
        work_folder=_approved_work_folder, destination=target,
    )
    assert second.path == target / "informe-v002.pdf"
    assert {p.name for p in target.iterdir()} == {"informe-v001.pdf", "informe-v002.pdf"}
    assert not documents.exists()

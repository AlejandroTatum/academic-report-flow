"""Tests for build_report_auto.py router behavior.

Covers backend routing without invoking LaTeX/PDF/Playwright tools.
Uses monkeypatch/fake objects so tests are fast and deterministic.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make tools/ importable (same pattern as test_metadata_validation.py)
TOOLS_DIR = str(Path(__file__).resolve().parent)
if TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

from build_report_auto import UNSUPPORTED_BUILDER_MESSAGES, build_backend, main


@pytest.fixture(autouse=True)
def _approved_body():
    """Router tests use fake folders; the real approval guard has its own tests."""
    current = MagicMock(state="current")
    with patch("build_report_auto.approval_state", return_value=current):
        yield


# ---------------------------------------------------------------------------
# Fake objects (lighter than full ReportConfig)
# ---------------------------------------------------------------------------


class FakeArgs:
    """Minimal argparse.Namespace stand-in for build_backend tests."""

    def __init__(self, *, tex_only: bool = False, validate_only: bool = False) -> None:
        self.tex_only = tex_only
        self.validate_only = validate_only


class FakeReportConfig:
    """Minimal ReportConfig stand-in — exposes what build_backend and main() need.

    output_format is a @property matching the real ReportConfig so post-init
    mutations to config.raw['output'] are reflected (used by --tex-only).
    """

    def __init__(
        self,
        backend: str = "latex",
        folder: Path | None = None,
        raw: dict | None = None,
    ) -> None:
        self.backend = backend
        self.folder = folder or Path("/tmp/fake-report")
        self.raw = raw or {}
        self.type = self.raw.get("type", "essay")
        self.quality_report_path = self.folder / "backups" / "quality_report.md"
        self.pdf_path = self.folder / "outputs" / "report.pdf"
        self.publication_category = "Tecnicos"
        self.document_slug = "informe"

    @property
    def output_format(self) -> str:
        return str(self.raw.get("output") or "pdf").strip().lower()


class FakeValidation:
    """Minimal ReportValidation stand-in for main() tests."""

    def __init__(self, errors: list[str] | None = None, warnings: list[str] | None = None) -> None:
        self.errors = errors or []
        self.warnings = warnings or []


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildBackend:
    """build_backend routing — no subprocess or file I/O."""

    # -- LaTeX path ---------------------------------------------------------

    def test_latex_routes_to_build_latex_report(self) -> None:
        """LaTeX backend invokes build_latex_report.py via subprocess."""
        config = FakeReportConfig(backend="latex")
        args = FakeArgs()

        with patch("build_report_auto.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[arg-type]
                args=[], returncode=0,
            )
            build_backend(config, args)  # should not raise

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert any("build_latex_report.py" in part for part in cmd), (
            f"Expected build_latex_report.py in command, got: {cmd}"
        )
        assert str(config.folder) in cmd

    def test_latex_tex_only_flag_passed_to_subprocess(self) -> None:
        """--tex-only is appended to the subprocess command."""
        config = FakeReportConfig(backend="latex")
        args = FakeArgs(tex_only=True)

        with patch("build_report_auto.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[arg-type]
                args=[], returncode=0,
            )
            build_backend(config, args)

        cmd = mock_run.call_args[0][0]
        assert "--tex-only" in cmd

    def test_latex_subprocess_failure_raises_systemexit(self) -> None:
        """LaTeX subprocess non-zero exit raises SystemExit."""
        config = FakeReportConfig(backend="latex")
        args = FakeArgs()

        with patch("build_report_auto.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[arg-type]
                args=[], returncode=2,
            )
            with pytest.raises(SystemExit) as exc:
                build_backend(config, args)
            assert exc.value.code == 2

    # -- Visual path --------------------------------------------------------

    def test_visual_backend_fails_fast(self) -> None:
        """Visual backend raises SystemExit with a non-zero code."""
        config = FakeReportConfig(backend="visual")
        args = FakeArgs()

        with pytest.raises(SystemExit) as exc:
            build_backend(config, args)

        assert exc.value.code  # truthy → non-zero / non-empty
        message = str(exc.value.code)
        assert "visual" in message.lower()
        assert "builder visual" in message.lower()

    def test_visual_backend_message_references_specific_builder(self) -> None:
        """Visual error message references a known visual builder script."""
        msg = UNSUPPORTED_BUILDER_MESSAGES.get("visual", "")
        assert "build_mapa_conceptual_investigacion" in msg

    # -- DOCX path ----------------------------------------------------------

    def test_docx_routes_to_build_docx_report(self) -> None:
        """DOCX backend invokes build_docx_report.py via subprocess.

        This backend used to fail fast with a pointer to a task-specific
        restyling script, because no generic Markdown -> DOCX builder existed
        while the intake still offered DOCX as a delivery format.
        """
        config = FakeReportConfig(backend="docx")
        args = FakeArgs()

        with patch("build_report_auto.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[arg-type]
                args=[], returncode=0,
            )
            build_backend(config, args)  # should not raise

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert any("build_docx_report.py" in part for part in cmd), (
            f"Expected build_docx_report.py in command, got: {cmd}"
        )
        assert str(config.folder) in cmd

    def test_docx_is_no_longer_advertised_as_unsupported(self) -> None:
        """DOCX has a generic builder, so it must not carry a no-op message."""
        assert "docx" not in UNSUPPORTED_BUILDER_MESSAGES

    def test_docx_ignores_the_latex_only_tex_only_flag(self) -> None:
        """--tex-only is a LaTeX stage; the DOCX builder has no such switch."""
        config = FakeReportConfig(backend="docx")
        args = FakeArgs(tex_only=True)

        with patch("build_report_auto.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[arg-type]
                args=[], returncode=0,
            )
            build_backend(config, args)

        assert "--tex-only" not in mock_run.call_args[0][0]

    def test_docx_subprocess_failure_raises_systemexit(self) -> None:
        """A failing DOCX builder propagates its exit code, like LaTeX does."""
        config = FakeReportConfig(backend="docx")
        args = FakeArgs()

        with patch("build_report_auto.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(  # type: ignore[arg-type]
                args=[], returncode=3,
            )
            with pytest.raises(SystemExit) as exc:
                build_backend(config, args)
            assert exc.value.code == 3

    # -- Unknown backend ----------------------------------------------------

    def test_unknown_backend_fails_fast(self) -> None:
        """Unknown backend raises SystemExit with a helpful message."""
        config = FakeReportConfig(backend="html")
        args = FakeArgs()

        with pytest.raises(SystemExit) as exc:
            build_backend(config, args)

        assert exc.value.code
        message = str(exc.value.code)
        assert "html" in message.lower() or "no soportado" in message.lower()
        assert "latex" in message.lower()  # mentions supported options

    # -- Subprocess error boundary -------------------------------------------

    def test_latex_subprocess_filenotfound_error(self) -> None:
        """FileNotFoundError from subprocess.run becomes SystemExit with clear message."""
        config = FakeReportConfig(backend="latex")
        args = FakeArgs()

        with patch("build_report_auto.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError(
                "No such file or directory: 'python3'"
            )
            with pytest.raises(SystemExit) as exc:
                build_backend(config, args)

        message = str(exc.value.code)
        assert "no se encontró" in message.lower()
        assert "build_latex_report.py" in message

    def test_latex_subprocess_oserror(self) -> None:
        """Generic OSError from subprocess.run becomes SystemExit with clear message."""
        config = FakeReportConfig(backend="latex")
        args = FakeArgs()

        with patch("build_report_auto.subprocess.run") as mock_run:
            mock_run.side_effect = OSError("Permission denied")
            with pytest.raises(SystemExit) as exc:
                build_backend(config, args)

        message = str(exc.value.code)
        assert "error del sistema" in message.lower()
        assert "permission" in message.lower()


class TestMain:
    """Tests for main() — the externally visible entry point.

    Patches module-level load_report_config, build_backend, and validate
    so no subprocess or file I/O runs. All tests are fast and deterministic.
    """

    # -- Helper --------------------------------------------------------------

    def _run_main(
        self,
        backend: str = "latex",
        extra_args: list[str] | None = None,
        validation: FakeValidation | None = None,
    ) -> tuple[FakeReportConfig, MagicMock, MagicMock]:
        """Run main() with patched dependencies and return (config, mock_build, mock_validate).

        Callers can inspect mock_validate.call_args to check config mutations.
        """
        config = FakeReportConfig(backend=backend)
        argv = ["build_report_auto.py", "/tmp/fake-report"] + (extra_args or [])

        with (
            patch.object(sys, "argv", argv),
            patch("build_report_auto.load_report_config", return_value=config),
            patch("build_report_auto.build_backend") as mock_build,
            patch("build_report_auto.validate", return_value=validation or FakeValidation()) as mock_validate,
            patch("build_report_auto.sha256_file", return_value="validated-hash"),
        ):
            main()

        return config, mock_build, mock_validate

    # -- Normal flow ---------------------------------------------------------

    def test_main_normal_flow_calls_build_backend_then_validate(self) -> None:
        """When --validate-only is absent, main() calls build_backend then validate.

        This is the primary production path: build happens first, validation second.
        """
        config, mock_build, mock_validate = self._run_main(backend="latex")

        mock_build.assert_called_once()
        assert mock_build.call_args[0][0] is config, "build_backend must receive the same config"
        mock_validate.assert_called_once_with(config)

    # -- --validate-only -----------------------------------------------------

    def test_validate_only_skips_build_backend(self) -> None:
        """--validate-only: build_backend is NOT called, validate IS called."""
        config, mock_build, mock_validate = self._run_main(
            backend="latex", extra_args=["--validate-only"],
        )

        mock_build.assert_not_called()
        mock_validate.assert_called_once_with(config)

    @pytest.mark.parametrize(
        "backend",
        [
            "latex",
            pytest.param("visual", id="visual"),
            pytest.param("docx", id="docx"),
            pytest.param("svglot", id="unknown_backend"),
        ],
    )
    def test_validate_only_all_backends(self, backend: str) -> None:
        """--validate-only skips build for every backend (validation-only supports manual builds)."""
        config, mock_build, mock_validate = self._run_main(
            backend=backend, extra_args=["--validate-only"],
        )

        mock_build.assert_not_called()
        mock_validate.assert_called_once()

    # -- --validate-only + --tex-only ----------------------------------------

    def test_validate_only_with_tex_only_mutates_config(self) -> None:
        """--validate-only AND --tex-only: build skipped, tex mutations still applied to validations."""
        config, mock_build, mock_validate = self._run_main(
            backend="latex", extra_args=["--validate-only", "--tex-only"],
        )

        mock_build.assert_not_called()
        mock_validate.assert_called_once()

        mutated_config = mock_validate.call_args[0][0]
        assert mutated_config.raw["output"] == "tex"
        assert mutated_config.raw.setdefault("validators", {})["pdf_layout"] is False
        assert mutated_config.output_format == "tex"

    def test_generation_never_exposes_a_publication_entrypoint(self) -> None:
        """Generation must not carry any publication machinery (#22).

        Publication belongs to the deliver phase through the guarded publisher;
        a generation run that could publish collapses generate and deliver into
        one side effect.
        """
        import build_report_auto

        assert not hasattr(build_report_auto, "publish_validated_pdf"), (
            "build_report_auto must not import or expose publish_validated_pdf"
        )

    def test_generation_does_not_publish_after_validation(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A validated generation run ends with evidence, never a publication."""
        folder = tmp_path / "generated"
        (folder / "outputs").mkdir(parents=True)
        (folder / "outputs" / "report.pdf").write_bytes(b"%PDF-1.7\nbuilt content\n")
        config = FakeReportConfig(backend="latex", folder=folder)
        argv = ["build_report_auto.py", str(folder)]

        with (
            patch.object(sys, "argv", argv),
            patch("build_report_auto.load_report_config", return_value=config),
            patch("build_report_auto.build_backend"),
            patch("build_report_auto.validate", return_value=FakeValidation()),
            patch("build_report_auto.sha256_file", return_value="a" * 64),
        ):
            main()  # must not raise and must not publish anything

        captured = capsys.readouterr()
        assert "VALIDATION PASSED" in captured.out
        assert "a" * 64 in captured.out, "generation must report the validated hash"
        assert "PUBLICADO" not in captured.out
        assert "PDF PUBLICATION" not in captured.out

    # -- Validation errors ---------------------------------------------------

    def test_generation_flow_is_build_then_validate_only(self) -> None:
        """Generation is build + validation; nothing runs after validation (#22)."""
        config = FakeReportConfig(backend="latex")
        argv = ["build_report_auto.py", "/tmp/fake-report"]
        events: list[str] = []

        with (
            patch.object(sys, "argv", argv),
            patch("build_report_auto.load_report_config", return_value=config),
            patch("build_report_auto.build_backend", side_effect=lambda *_: events.append("build")),
            patch("build_report_auto.validate", side_effect=lambda _: events.append("validate") or FakeValidation()),
            patch("build_report_auto.sha256_file", return_value="validated-hash"),
        ):
            main()

        assert events == ["build", "validate"]

    def test_pdf_bytes_must_not_change_across_validation(self) -> None:
        """A PDF mutated between the two hash reads invalidates the run."""
        config = FakeReportConfig(backend="latex")
        argv = ["build_report_auto.py", "/tmp/fake-report"]

        with (
            patch.object(sys, "argv", argv),
            patch("build_report_auto.load_report_config", return_value=config),
            patch("build_report_auto.build_backend"),
            patch("build_report_auto.sha256_file", side_effect=["hash-before", "hash-after"]),
            patch("build_report_auto.validate", return_value=FakeValidation()) as validate,
        ):
            with pytest.raises(SystemExit, match="CHANGED DURING VALIDATION"):
                main()

        validate.assert_called_once_with(config)

    def test_validation_failure_stops_generation_before_any_delivery(self) -> None:
        """Validation errors abort the run; delivery is a separate later phase."""
        config = FakeReportConfig(backend="latex")
        argv = ["build_report_auto.py", "/tmp/fake-report"]

        with (
            patch.object(sys, "argv", argv),
            patch("build_report_auto.load_report_config", return_value=config),
            patch("build_report_auto.build_backend"),
            patch("build_report_auto.validate", return_value=FakeValidation(errors=["falló"])),
            patch("build_report_auto.sha256_file", return_value="validated-hash"),
        ):
            with pytest.raises(SystemExit):
                main()

    def test_validation_errors_cause_systemexit(self) -> None:
        """When validate returns errors, main() raises SystemExit with a failure message."""
        val = FakeValidation(errors=["Metadata incompleta: falta título"])

        with pytest.raises(SystemExit) as exc:
            self._run_main(backend="latex", validation=val)

        message = str(exc.value.code)
        assert message, "SystemExit code must be a non-empty string"
        assert "VALIDATION FAILED" in message

    # -- Validation warnings -------------------------------------------------

    def test_validation_warnings_printed(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When validate returns warnings only, they are printed to stdout."""
        val = FakeValidation(warnings=["Revisar fuentes de figuras"])

        self._run_main(backend="latex", validation=val)

        captured = capsys.readouterr()
        assert "VALIDATION PASSED WITH WARNINGS" in captured.out
        assert "Revisar fuentes de figuras" in captured.out

    # -- Validation errors + warnings ----------------------------------------

    def test_validation_errors_suppress_warnings_printing(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When validate returns both errors AND warnings, errors raise first — warnings are not printed.

        Current implementation: errors raise SystemExit before the warnings print
        statement is reached. This test documents that specific behavior.
        """
        val = FakeValidation(
            errors=["Metadata incompleta: falta título"],
            warnings=["Revisar fuentes de figuras"],
        )

        with pytest.raises(SystemExit) as exc:
            self._run_main(backend="latex", validation=val)

        message = str(exc.value.code)
        assert "VALIDATION FAILED" in message
        assert "falta título" in message
        # Warnings must NOT appear in the SystemExit message
        assert "VALIDATION PASSED WITH WARNINGS" not in message
        assert "Revisar fuentes" not in message

        # Warnings must NOT have been printed to stdout either
        captured = capsys.readouterr()
        assert "Revisar fuentes" not in captured.out
        assert "VALIDATION PASSED WITH WARNINGS" not in captured.out

    # -- --tex-only mutation -------------------------------------------------

    def test_tex_only_mutation(self) -> None:
        """--tex-only: config.raw['output'] = 'tex' and pdf_layout validator disabled."""
        config, mock_build, mock_validate = self._run_main(
            backend="latex", extra_args=["--tex-only"],
        )

        # Verify raw mutations via the config passed to validate
        mutated_config = mock_validate.call_args[0][0]
        assert mutated_config.raw["output"] == "tex"
        assert mutated_config.raw.setdefault("validators", {})["pdf_layout"] is False
        # Externally-visible: output_format property reflects the mutation
        assert mutated_config.output_format == "tex"

    def test_tex_only_announces_pdf_layout_disabled(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--tex-only must print an explicit notice that pdf_layout is off.

        The mutation must not be silent: a user running --tex-only needs to see
        that the layout audit is skipped for this run, before any validation
        result is printed.
        """
        self._run_main(backend="latex", extra_args=["--tex-only"])

        captured = capsys.readouterr()
        assert "tex-only" in captured.out
        assert "pdf_layout" in captured.out
        assert "desactivado" in captured.out

    def test_tex_only_disclosure_absent_without_flag(
        self, capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Without --tex-only, no pdf_layout disclosure is printed."""
        self._run_main(backend="latex")

        captured = capsys.readouterr()
        assert "pdf_layout" not in captured.out

    # -- Unsupported backend normal mode (no --validate-only) ------------------

    @pytest.mark.parametrize(
        "backend,keyword",
        [
            pytest.param("visual", "visual", id="visual"),
            pytest.param("html", "no soportado", id="unknown"),
        ],
    )
    def test_main_unsupported_backend_normal_mode(
        self, backend: str, keyword: str,
    ) -> None:
        """Normal mode (no --validate-only) with unsupported backend raises SystemExit.

        build_backend runs first and must fail before validate is reached.
        """
        config = FakeReportConfig(backend=backend)
        argv = ["build_report_auto.py", "/tmp/fake-report"]

        with (
            patch.object(sys, "argv", argv),
            patch("build_report_auto.load_report_config", return_value=config),
            patch("build_report_auto.validate") as mock_validate,
        ):
            with pytest.raises(SystemExit) as exc:
                main()

        mock_validate.assert_not_called()
        assert exc.value.code
        message = str(exc.value.code)
        assert keyword in message.lower()

    # -- Happy path output ----------------------------------------------------

    def test_main_validation_passed(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When validate returns no errors or warnings, 'VALIDATION PASSED' is printed."""
        val = FakeValidation()  # no errors, no warnings

        self._run_main(backend="latex", validation=val)

        captured = capsys.readouterr()
        assert "VALIDATION PASSED" in captured.out
        assert "VALIDATION FAILED" not in captured.out
        assert "VALIDATION PASSED WITH WARNINGS" not in captured.out

    # -- --tex-only + unsupported backend -------------------------------------

    @pytest.mark.parametrize(
        "backend",
        [
            pytest.param("visual", id="visual"),
            pytest.param("docx", id="docx"),
            pytest.param("svglot", id="unknown"),
        ],
    )
    def test_tex_only_with_unsupported_backend(self, backend: str) -> None:
        """--tex-only combined with unsupported backend still fails fast.

        build_backend runs before the --tex-only mutation, so unsupported
        backends must raise SystemExit regardless of --tex-only.
        """
        config = FakeReportConfig(backend=backend)
        argv = ["build_report_auto.py", "/tmp/fake-report", "--tex-only"]

        with (
            patch.object(sys, "argv", argv),
            patch("build_report_auto.load_report_config", return_value=config),
            patch("build_report_auto.validate") as mock_validate,
        ):
            with pytest.raises(SystemExit) as exc:
                main()

        mock_validate.assert_not_called()
        assert exc.value.code


class TestApprovalGuard:
    """Building requires a current approval.yml unless explicitly skipped."""

    def _run(self, folder: Path, extra: list[str] | None = None, build_error: BaseException | None = None) -> MagicMock:
        config = FakeReportConfig(backend="latex", folder=folder)
        argv = ["build_report_auto.py", str(folder)] + (extra or [])
        with (
            patch.object(sys, "argv", argv),
            patch("build_report_auto.load_report_config", return_value=config),
            patch("build_report_auto.build_backend", side_effect=build_error) as mock_build,
            patch("build_report_auto.validate", return_value=FakeValidation()),
            patch("build_report_auto.sha256_file", return_value="h"),
            patch("build_report_auto.approval_state", wraps=__import__("approval_marker").approval_state),
        ):
            main()
        return mock_build

    def test_missing_approval_refuses_to_build(self, tmp_path: Path) -> None:
        (tmp_path / "body.md").write_text("# A\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="approval"):
            self._run(tmp_path)

    def test_stale_approval_refuses_to_build(self, tmp_path: Path) -> None:
        from conftest import _approval

        _approval(tmp_path)
        (tmp_path / "body.md").write_text("# Changed\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="approval"):
            self._run(tmp_path)

    def test_current_approval_builds(self, tmp_path: Path) -> None:
        from conftest import _approval

        _approval(tmp_path)
        self._run(tmp_path).assert_called_once()

    def test_no_approval_check_flag_skips_the_guard(self, tmp_path: Path) -> None:
        self._run(tmp_path, ["--no-approval-check"]).assert_called_once()

    def test_no_approval_check_records_the_rendered_body_hash(self, tmp_path: Path) -> None:
        from approval_marker import draft_record_path, sha256_file

        body = tmp_path / "body.md"
        body.write_text("# A\n", encoding="utf-8")
        self._run(tmp_path, ["--no-approval-check"])
        record = draft_record_path(tmp_path / "outputs" / "report.pdf")
        assert record.read_text(encoding="utf-8").strip() == sha256_file(body)

    def test_failed_draft_build_leaves_no_fresh_record(self, tmp_path: Path) -> None:
        from approval_marker import draft_is_fresh, draft_record_path, write_draft_record

        body = tmp_path / "body.md"
        body.write_text("# A\n", encoding="utf-8")
        pdf = tmp_path / "outputs" / "report.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(b"%PDF old")
        write_draft_record(pdf, body)
        body.write_text("# Edited\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            self._run(tmp_path, ["--no-approval-check"], build_error=SystemExit("latex failed"))
        assert not draft_record_path(pdf).exists()
        assert not draft_is_fresh(pdf, body)

    def test_tex_only_draft_build_writes_no_record(self, tmp_path: Path) -> None:
        from approval_marker import draft_record_path

        (tmp_path / "body.md").write_text("# A\n", encoding="utf-8")
        self._run(tmp_path, ["--no-approval-check", "--tex-only"])
        assert not draft_record_path(tmp_path / "outputs" / "report.pdf").exists()

    def test_final_build_records_the_rendered_body_hash_too(self, tmp_path: Path) -> None:
        """The publisher needs proof that a final PDF comes from the current body.md."""
        from approval_marker import draft_is_fresh, draft_record_path, sha256_file
        from conftest import _approval

        _approval(tmp_path)
        self._run(tmp_path)
        pdf = tmp_path / "outputs" / "report.pdf"
        assert draft_record_path(pdf).read_text(encoding="utf-8").strip() == sha256_file(tmp_path / "body.md")
        pdf.write_bytes(b"%PDF built")  # the faked backend writes none
        assert draft_is_fresh(pdf, tmp_path / "body.md")

    def test_failed_final_build_leaves_no_fresh_record(self, tmp_path: Path) -> None:
        from approval_marker import draft_is_fresh, draft_record_path, write_draft_record
        from conftest import _approval

        _approval(tmp_path)
        pdf = tmp_path / "outputs" / "report.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(b"%PDF old")
        write_draft_record(pdf, tmp_path / "body.md")
        with pytest.raises(SystemExit, match="latex failed"):
            self._run(tmp_path, build_error=SystemExit("latex failed"))
        assert not draft_record_path(pdf).exists()
        assert not draft_is_fresh(pdf, tmp_path / "body.md")

    def test_build_records_the_report_render_settings(self, tmp_path: Path) -> None:
        from approval_marker import render_record_path, render_settings_unchanged

        (tmp_path / "report.yml").write_text("format: aa\n", encoding="utf-8")
        self._run(tmp_path, ["--no-approval-check"])
        assert render_record_path(tmp_path).is_file()
        assert render_settings_unchanged(tmp_path)

    def test_failed_build_leaves_no_render_record(self, tmp_path: Path) -> None:
        from approval_marker import render_record_path, write_render_record

        (tmp_path / "report.yml").write_text("format: aa\n", encoding="utf-8")
        write_render_record(tmp_path)
        with pytest.raises(SystemExit):
            self._run(tmp_path, ["--no-approval-check"], build_error=SystemExit("latex failed"))
        assert not render_record_path(tmp_path).exists()

    def test_tex_only_build_writes_no_render_record(self, tmp_path: Path) -> None:
        from approval_marker import render_record_path

        (tmp_path / "report.yml").write_text("format: aa\n", encoding="utf-8")
        self._run(tmp_path, ["--no-approval-check", "--tex-only"])
        assert not render_record_path(tmp_path).exists()

    def test_validate_only_does_not_need_approval(self, tmp_path: Path) -> None:
        self._run(tmp_path, ["--validate-only"]).assert_not_called()

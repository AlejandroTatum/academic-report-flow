"""Tests for pre-flight figure validation and compiler-failure diagnostics.

Two silent-failure defects are pinned here:

* the LaTeX compiler's output was captured and thrown away, so a fatal
  ``! Package luatex.def Error: File ... not found`` was replaced by a bare
  ``La compilación no generó PDF``;
* figure paths referenced from ``body.md`` were never checked, so a missing
  file — or an absolute host path that cannot exist inside the Docker bind
  mount — only surfaced as that same swallowed fatal error.
"""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import build_latex_report  # noqa: E402

LUATEX_FAILURE = "\n".join(
    ["This is LuaHBTeX, Version 1.18.0"]
    + [f"[{n}]" for n in range(1, 200)]
    + [
        "! Package luatex.def Error: File `/host/assets/flujo-prompting.png' not found",
        "See the luatex.def package documentation for explanation.",
        "!  ==> Fatal error occurred, no output PDF file produced!",
    ]
)


def _config(tmp_path: Path, body: str = "# Titulo\n\nTexto.\n") -> types.SimpleNamespace:
    folder = tmp_path / "report"
    build_dir = folder / "build"
    build_dir.mkdir(parents=True)
    body_path = folder / "body.md"
    body_path.write_text(body, encoding="utf-8")
    (build_dir / "main.tex").write_text("% tex", encoding="utf-8")
    return types.SimpleNamespace(
        folder=folder,
        body_path=body_path,
        tex_path=build_dir / "main.tex",
        pdf_path=folder / "outputs" / "main.pdf",
        bib_path=None,
        publish_global=False,
        metadata={},
    )


# ---------------------------------------------------------------------------
# D-08 — the compiler output must reach the user when there is no PDF
# ---------------------------------------------------------------------------


def test_failure_message_names_the_missing_pdf_and_the_log() -> None:
    message = build_latex_report.compilation_failure_message(
        Path("/x/build/main.pdf"), Path("/x/build/main.log"), LUATEX_FAILURE
    )
    assert "/x/build/main.pdf" in message
    assert "/x/build/main.log" in message


def test_failure_message_surfaces_the_latex_error_line() -> None:
    message = build_latex_report.compilation_failure_message(
        Path("/x/build/main.pdf"), Path("/x/build/main.log"), LUATEX_FAILURE
    )
    assert "flujo-prompting.png' not found" in message
    assert "Fatal error occurred" in message


def test_failure_message_does_not_dump_the_whole_transcript() -> None:
    message = build_latex_report.compilation_failure_message(
        Path("/x/build/main.pdf"), Path("/x/build/main.log"), LUATEX_FAILURE
    )
    assert len(message.splitlines()) < 80
    assert "[1]" not in message


def test_failure_message_without_captured_output_still_points_at_the_log() -> None:
    message = build_latex_report.compilation_failure_message(
        Path("/x/build/main.pdf"), Path("/x/build/main.log"), ""
    )
    assert "/x/build/main.log" in message


def test_compile_latex_reports_the_compiler_output_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(
        build_latex_report.shutil,
        "which",
        lambda name: "/usr/bin/docker" if name == "docker" else None,
    )
    monkeypatch.setattr(
        build_latex_report,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            args=list(a[0]), returncode=1, stdout=LUATEX_FAILURE
        ),
    )
    with pytest.raises(SystemExit) as excinfo:
        build_latex_report.compile_latex(config)
    message = str(excinfo.value)
    assert "flujo-prompting.png' not found" in message
    assert "main.log" in message


def test_successful_compile_stays_quiet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _config(tmp_path)
    build_dir = config.tex_path.parent

    def fake_run(*args, **kwargs):
        (build_dir / "main.pdf").write_bytes(b"%PDF-1.5\n")
        return subprocess.CompletedProcess(args=list(args[0]), returncode=0, stdout=LUATEX_FAILURE)

    monkeypatch.setattr(
        build_latex_report.shutil,
        "which",
        lambda name: "/usr/bin/docker" if name == "docker" else None,
    )
    monkeypatch.setattr(build_latex_report, "run", fake_run)
    build_latex_report.compile_latex(config)
    printed = capsys.readouterr().out
    assert "LuaHBTeX" not in printed
    assert "[1]" not in printed


# ---------------------------------------------------------------------------
# D-16 — figure references are resolved before the compiler runs
# ---------------------------------------------------------------------------


def test_missing_relative_figure_is_reported(tmp_path: Path) -> None:
    errors = build_latex_report.validate_figure_paths(
        "![Flujo](../assets/flujo.png)\n", tmp_path / "build"
    )
    assert len(errors) == 1
    assert "flujo.png" in errors[0]


def test_existing_relative_figure_passes(tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "flujo.png").write_bytes(b"x")
    assert build_latex_report.validate_figure_paths(
        "![Flujo](../assets/flujo.png)\n", build_dir
    ) == []


def test_extensionless_figure_resolves_through_a_known_suffix(tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    (build_dir / "grafico.png").write_bytes(b"x")
    assert build_latex_report.validate_figure_paths("![G](grafico)\n", build_dir) == []


def test_absolute_figure_path_is_rejected_under_the_docker_mount(tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    figure = tmp_path / "flujo.png"
    figure.write_bytes(b"x")
    errors = build_latex_report.validate_figure_paths(
        f"![Flujo]({figure})\n", build_dir, docker_mount=tmp_path
    )
    assert len(errors) == 1
    assert str(figure) in errors[0]
    assert "absoluta" in errors[0].lower()


def test_absolute_figure_path_is_fine_for_a_local_engine(tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    figure = tmp_path / "flujo.png"
    figure.write_bytes(b"x")
    assert build_latex_report.validate_figure_paths(f"![Flujo]({figure})\n", build_dir) == []


def test_figure_outside_the_docker_mount_is_reported(tmp_path: Path) -> None:
    mount = tmp_path / "mount"
    build_dir = mount / "report" / "build"
    build_dir.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "flujo.png").write_bytes(b"x")
    errors = build_latex_report.validate_figure_paths(
        "![Flujo](../../../outside/flujo.png)\n", build_dir, docker_mount=mount
    )
    assert len(errors) == 1
    assert "flujo.png" in errors[0]


def test_remote_figure_urls_are_not_checked(tmp_path: Path) -> None:
    assert build_latex_report.validate_figure_paths(
        "![Logo](https://example.org/logo.png)\n", tmp_path
    ) == []


def test_compile_latex_fails_before_running_the_compiler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path, body="# Titulo\n\n![Flujo](../../assets/ausente.png)\n")
    calls: list[list[str]] = []
    monkeypatch.setattr(
        build_latex_report.shutil,
        "which",
        lambda name: "/usr/bin/docker" if name == "docker" else None,
    )
    monkeypatch.setattr(
        build_latex_report,
        "run",
        lambda *a, **k: calls.append(list(a[0]))
        or subprocess.CompletedProcess(args=list(a[0]), returncode=0, stdout=""),
    )
    with pytest.raises(SystemExit) as excinfo:
        build_latex_report.compile_latex(config)
    assert "ausente.png" in str(excinfo.value)
    assert calls == [], "no compiler must run once a figure is known to be unusable"


# ---------------------------------------------------------------------------
# #102 — one failed run cannot poison the next; bibliography errors surface
# ---------------------------------------------------------------------------

STALE_SUFFIXES = (".aux", ".bbl", ".bcf", ".blg", ".fdb_latexmk")


def _local_engine(monkeypatch: pytest.MonkeyPatch, tools: tuple[str, ...]) -> None:
    monkeypatch.setattr(
        build_latex_report.shutil, "which", lambda name: f"/usr/bin/{name}" if name in tools else None
    )


def _with_bib(config: types.SimpleNamespace) -> types.SimpleNamespace:
    config.bib_path = config.folder / "sources.bib"
    config.bib_path.write_text("@misc{k, title={T}}\n", encoding="utf-8")
    return config


def test_stale_bibliography_artifacts_are_removed_before_compiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _with_bib(_config(tmp_path))
    build_dir = config.tex_path.parent
    for suffix in STALE_SUFFIXES:
        (build_dir / f"main{suffix}").write_text("stale", encoding="utf-8")
    seen: list[list[str]] = []

    def fake_run(command, cwd=None, check=True):
        if not seen:
            seen.append([s for s in STALE_SUFFIXES if (build_dir / f"main{s}").exists()])
        (build_dir / "main.pdf").write_bytes(b"%PDF-1.5\n")
        return subprocess.CompletedProcess(args=list(command), returncode=0, stdout="")

    _local_engine(monkeypatch, ("latexmk",))
    monkeypatch.setattr(build_latex_report, "run", fake_run)
    build_latex_report.compile_latex(config)
    assert seen == [[]]
    assert (build_dir / "main.tex").exists()


@pytest.mark.parametrize("writes_bcf, backend", [(True, "biber"), (False, "bibtex")])
def test_bibliography_backend_follows_the_document_not_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, writes_bcf: bool, backend: str
) -> None:
    config = _with_bib(_config(tmp_path))
    build_dir = config.tex_path.parent
    commands: list[str] = []

    def fake_run(command, cwd=None, check=True):
        commands.append(Path(command[0]).name)
        if command[0].endswith("lualatex") and writes_bcf:
            (build_dir / "main.bcf").write_text("<bcf/>", encoding="utf-8")
        (build_dir / "main.pdf").write_bytes(b"%PDF-1.5\n")
        return subprocess.CompletedProcess(args=list(command), returncode=0, stdout="")

    _local_engine(monkeypatch, ("lualatex", "biber", "bibtex"))
    monkeypatch.setattr(build_latex_report, "run", fake_run)
    build_latex_report.compile_latex(config)
    assert commands == ["lualatex", backend, "lualatex", "lualatex"]


def test_bibliography_errors_are_printed_even_when_a_pdf_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _with_bib(_config(tmp_path))
    build_dir = config.tex_path.parent
    error = "ERROR - BibTeX subsystem: sources.bib, line 3, syntax error: found '%'"

    def fake_run(command, cwd=None, check=True):
        if command[0].endswith("lualatex"):
            (build_dir / "main.bcf").write_text("<bcf/>", encoding="utf-8")
            (build_dir / "main.pdf").write_bytes(b"%PDF-1.5\n")
            return subprocess.CompletedProcess(args=list(command), returncode=0, stdout="")
        (build_dir / "main.blg").write_text(f"[1] INFO - start\n[2] {error}\n", encoding="utf-8")
        return subprocess.CompletedProcess(args=list(command), returncode=2, stdout=error)

    _local_engine(monkeypatch, ("lualatex", "biber"))
    monkeypatch.setattr(build_latex_report, "run", fake_run)
    build_latex_report.compile_latex(config)
    printed = capsys.readouterr().err
    assert error in printed
    assert "main.blg" in printed


def test_docker_fallback_does_not_swallow_a_biber_failure_into_bibtex(tmp_path: Path) -> None:
    config = _config(tmp_path)
    script = build_latex_report.docker_compile_command(config)[-1]
    assert "|| bibtex" not in script
    assert "|| true" not in script
    assert "main.bcf" in script

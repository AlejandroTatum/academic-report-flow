"""`typeset.py auto` (odd/tasks/typeset-auto.md S1-S6).

The deterministic part of the typeset phase: tables from `- a; b; c` lines,
`Figura:` lines and bare URLs are formatted in ``body.typeset.md``; what needs
judgement is listed for the agent and ``body.md`` is never touched.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import typeset
from conftest import _report, _sources_bib
from report_config import read_yaml

PLAIN = (
    "# Informe\n"
    "\n"
    "Texto con fuentes [@key1] y enlace https://example.org/a_(b).\n"
    "Ya enlazado <https://example.org/x>, [nombre](https://example.org/y) y `https://example.org/code`.\n"
    "\n"
    "Tabla 1. Precios\n"
    "- Placa; Loja; 1; 15,25\n"
    "- Total; ; ; 15,25\n"
    "\n"
    "Figura: Diagrama del sistema (assets/diagrama.png)\n"
    "\n"
    "```\n"
    "https://example.org/fenced\n"
    "- a; b; c\n"
    "- d; e; f\n"
    "```\n"
)
FORMATTED = (
    "# Informe\n"
    "\n"
    "Texto con fuentes [@key1] y enlace <https://example.org/a_(b)>.\n"
    "Ya enlazado <https://example.org/x>, [nombre](https://example.org/y) y `https://example.org/code`.\n"
    "\n"
    "Tabla 1. Precios\n"
    "\n"
    "|  |  |  |  |\n"
    "|---|---|---:|---:|\n"
    "| Placa | Loja | 1 | 15,25 |\n"
    "| Total |  |  | 15,25 |\n"
    "\n"
    "![Diagrama del sistema](assets/diagrama.png)\n"
    "\n"
    "```\n"
    "https://example.org/fenced\n"
    "- a; b; c\n"
    "- d; e; f\n"
    "```\n"
)


def _folder(tmp_path: Path, body: str = PLAIN) -> Path:
    folder = tmp_path / "wf"
    _report(folder)
    _sources_bib(folder)
    (folder / "body.md").write_text(body, encoding="utf-8")
    return folder


def _typeset_text(folder: Path) -> str:
    return (folder / "body.typeset.md").read_text(encoding="utf-8")


def _check(folder: Path) -> dict[str, dict]:
    return {item["check"]: item for item in typeset.check_results(folder)}


def test_auto_binds_and_formats_only_the_typeset_copy(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _folder(tmp_path)

    assert typeset.main(["auto", str(folder)]) == 0

    out = capsys.readouterr().out
    assert "auto formatted 1 table(s), 1 figure(s), 1 URL(s)" in out
    assert _typeset_text(folder) == FORMATTED
    assert (folder / "body.md").read_text(encoding="utf-8") == PLAIN
    assert (folder / "typeset-source.md").read_text(encoding="utf-8") == PLAIN
    binding = read_yaml(folder / "typeset.yml")
    assert binding["body_sha256"] == hashlib.sha256(PLAIN.encode("utf-8")).hexdigest()
    assert _check(folder)["binding"]["ok"]


def test_auto_links_bare_urls_and_keeps_punctuation_outside(tmp_path: Path) -> None:
    body = "# Informe\n\nVer https://a.example/x, (https://b.example/y) y https://c.example/z.\n"
    folder = _folder(tmp_path, body)

    assert typeset.main(["auto", str(folder)]) == 0

    assert _typeset_text(folder) == (
        "# Informe\n\nVer <https://a.example/x>, (<https://b.example/y>) y <https://c.example/z>.\n"
    )


def test_auto_turns_a_figura_line_into_an_image(tmp_path: Path) -> None:
    body = "# Informe\n\nFigura: Montaje final (fotos/montaje.jpg)\n\nFigura: sin ruta, queda igual\n"
    folder = _folder(tmp_path, body)

    assert typeset.main(["auto", str(folder)]) == 0

    assert _typeset_text(folder) == (
        "# Informe\n\n![Montaje final](fotos/montaje.jpg)\n\nFigura: sin ruta, queda igual\n"
    )


def test_auto_builds_a_table_only_from_equal_runs_of_three_or_more_cells(tmp_path: Path) -> None:
    body = (
        "# Informe\n\n"
        "Datos:\n"
        "- uno; 10 %; rojo|verde\n"
        "- dos; 5 %; azul\n"
        "Cierre.\n\n"
        "- sola; fila; aqui\n\n"
        "- tres; celdas; aqui\n"
        "- pero; cuatro; celdas; aqui\n"
    )
    folder = _folder(tmp_path, body)

    assert typeset.main(["auto", str(folder)]) == 0

    assert _typeset_text(folder) == (
        "# Informe\n\n"
        "Datos:\n"
        "\n"
        "|  |  |  |\n"
        "|---|---:|---|\n"
        "| uno | 10 % | rojo\\|verde |\n"
        "| dos | 5 % | azul |\n"
        "\n"
        "Cierre.\n\n"
        "- sola; fila; aqui\n\n"
        "- tres; celdas; aqui\n"
        "- pero; cuatro; celdas; aqui\n"
    )


def test_auto_never_rewrites_an_already_formatted_typeset_body(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = _folder(tmp_path)
    assert typeset.main(["bind", str(folder)]) == 0
    edited = PLAIN.replace("# Informe", "# Informe ")
    (folder / "body.typeset.md").write_text(edited, encoding="utf-8")
    capsys.readouterr()

    assert typeset.main(["auto", str(folder)]) == 0

    assert "already differs from body.md, auto left it unchanged" in capsys.readouterr().out
    assert _typeset_text(folder) == edited


def test_auto_refuses_like_bind_when_body_is_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = tmp_path / "wf"
    _report(folder)
    before = sorted(p.name for p in folder.iterdir())

    assert typeset.main(["auto", str(folder)]) == 1

    assert "typeset not bound:" in capsys.readouterr().err
    assert sorted(p.name for p in folder.iterdir()) == before


def test_auto_lists_what_it_leaves_for_the_agent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    body = (
        "# Informe\n\n"
        "- a; 1; 2\n"
        "- b; 3; 4\n\n"
        "- clave; valor\n"
        "- otra; cosa\n\n"
        "El error es e = |x1 - x0| / |x1|.\n"
        "Ver https://example.org/a=b para n = 3 casos.\n"
    )
    folder = _folder(tmp_path, body)

    assert typeset.main(["auto", str(folder)]) == 0

    out = capsys.readouterr().out
    assert "  left for you: line 3: table without column names: name its 3 columns" in out
    assert "  left for you: line 8: possible two-column table: format it as a table if it is data" in out
    assert "  left for you: line 11: possible formula: write it as math" in out
    assert out.count("left for you:") == 3


def test_check_fails_until_the_table_columns_are_named(tmp_path: Path) -> None:
    folder = _folder(tmp_path)
    assert typeset.main(["auto", str(folder)]) == 0

    headers = _check(folder)["table_headers"]
    assert not headers["ok"]
    assert headers["detail"] == "line 8: table without column names"

    named = FORMATTED.replace("|  |  |  |  |", "| Componente | Tienda | Cant. | Precio |")
    (folder / "body.typeset.md").write_text(named, encoding="utf-8")

    assert _check(folder)["table_headers"] == {
        "check": "table_headers",
        "ok": True,
        "detail": "every table names its columns",
    }


def test_auto_keeps_citations_and_inline_code_whole_inside_cells(tmp_path: Path) -> None:
    body = (
        "# Informe\n\n"
        "- Sensor; 3,3 V; ver [@key1; @key2]\n"
        "- Motor; 5 V; usa `a; b`\n"
    )
    folder = _folder(tmp_path, body)

    assert typeset.main(["auto", str(folder)]) == 0

    assert _typeset_text(folder) == (
        "# Informe\n\n"
        "|  |  |  |\n"
        "|---|---|---|\n"
        "| Sensor | 3,3 V | ver [@key1; @key2] |\n"
        "| Motor | 5 V | usa `a; b` |\n"
    )
    assert _check(folder)["citations_match"]["ok"]


def test_auto_converts_a_run_whole_or_not_at_all_and_ignores_a_trailing_semicolon(tmp_path: Path) -> None:
    body = (
        "# Informe\n\n"
        "- a; b\n"
        "- c; d; e\n"
        "- f; g; h\n\n"
        "- uno; dos;\n"
        "- tres; cuatro;\n\n"
        "- x; 1; 2;\n"
        "- y; 3; 4;\n"
    )
    folder = _folder(tmp_path, body)

    assert typeset.main(["auto", str(folder)]) == 0

    assert _typeset_text(folder) == (
        "# Informe\n\n"
        "- a; b\n"
        "- c; d; e\n"
        "- f; g; h\n\n"
        "- uno; dos;\n"
        "- tres; cuatro;\n\n"
        "|  |  |  |\n"
        "|---|---:|---:|\n"
        "| x | 1 | 2 |\n"
        "| y | 3 | 4 |\n"
    )


def test_auto_keeps_markup_outside_links_and_leaves_code_alone(tmp_path: Path) -> None:
    body = (
        "# Informe\n\n"
        '**https://bold.example** _https://ital.example_ "https://quote.example" «https://guill.example»\n\n'
        "    https://indented.example\n\n"
        "```\n"
        "~~~\n"
        "https://fenced.example\n"
        "```\n"
    )
    folder = _folder(tmp_path, body)

    assert typeset.main(["auto", str(folder)]) == 0

    assert _typeset_text(folder) == (
        "# Informe\n\n"
        '**<https://bold.example>** _<https://ital.example>_ "<https://quote.example>" «<https://guill.example>»\n\n'
        "    https://indented.example\n\n"
        "```\n"
        "~~~\n"
        "https://fenced.example\n"
        "```\n"
    )


def test_auto_writes_nothing_when_body_is_not_utf8(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _folder(tmp_path)
    (folder / "body.md").write_bytes(b"# Informe\n\nA\xf1o\n")
    before = sorted(p.name for p in folder.iterdir())

    assert typeset.main(["auto", str(folder)]) == 1

    assert "typeset not bound:" in capsys.readouterr().err
    assert sorted(p.name for p in folder.iterdir()) == before


def test_auto_never_splits_a_url_and_keeps_its_own_trailing_marks(tmp_path: Path) -> None:
    body = (
        "# Informe\n\n"
        "- [Doc](https://x.example/a;b=1); c; d\n"
        "- Ver https://y.example/p;q=2 aqui; e; f\n\n"
        "Ver https://x.example/Ley_de_Ohm_ y https://y.example/a*b*\n\n"
        "````\n"
        "```\n"
        "https://inner.example\n"
        "```\n"
        "````\n"
    )
    folder = _folder(tmp_path, body)

    assert typeset.main(["auto", str(folder)]) == 0

    assert _typeset_text(folder) == (
        "# Informe\n\n"
        "|  |  |  |\n"
        "|---|---|---|\n"
        "| [Doc](https://x.example/a;b=1) | c | d |\n"
        "| Ver <https://y.example/p;q=2> aqui | e | f |\n\n"
        "Ver <https://x.example/Ley_de_Ohm_> y <https://y.example/a*b*>\n\n"
        "````\n"
        "```\n"
        "https://inner.example\n"
        "```\n"
        "````\n"
    )


def test_auto_leaves_a_run_whole_when_one_line_has_no_cell_separator(tmp_path: Path) -> None:
    body = "# Informe\n\n- a [b; c; d\n- e; f; g\n- h; i; j\n"
    folder = _folder(tmp_path, body)

    assert typeset.main(["auto", str(folder)]) == 0

    assert _typeset_text(folder) == body


# odd/tasks/skill-visual-organization.md S3: column names from the caption parentheses.
def test_auto_names_the_columns_from_the_caption_parentheses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        "# Informe\n\n"
        "Tabla 2. Funciones de la capa de enlace (función; qué hace; ejemplo).\n\n"
        "- Encapsulamiento; arma la trama; Ethernet II\n"
        "- Direccionamiento; usa la MAC; 48 bits\n"
    )
    folder = _folder(tmp_path, body)

    assert typeset.main(["auto", str(folder)]) == 0

    assert _typeset_text(folder) == (
        "# Informe\n\n"
        "Tabla 2. Funciones de la capa de enlace.\n\n"
        "<!-- table-style: tabla-2 purpose=reference -->\n\n"
        "| Función | Qué hace | Ejemplo |\n"
        "|---|---|---|\n"
        "| Encapsulamiento | arma la trama | Ethernet II |\n"
        "| Direccionamiento | usa la MAC | 48 bits |\n"
    )
    assert "table without column names" not in capsys.readouterr().out
    assert _check(folder)["table_headers"]["ok"]


def test_auto_takes_only_the_last_parentheses_and_keeps_an_existing_directive(tmp_path: Path) -> None:
    body = (
        "# Informe\n\n"
        "Tabla 6. Clases IPv4 (RFC 1918) (clase; rango; máscara)\n"
        "<!-- table-style: clases purpose=reference -->\n"
        "- A; 1 a 126; 255.0.0.0\n"
        "- B; 128 a 191; 255.255.0.0\n"
    )
    folder = _folder(tmp_path, body)

    assert typeset.main(["auto", str(folder)]) == 0

    assert _typeset_text(folder) == (
        "# Informe\n\n"
        "Tabla 6. Clases IPv4 (RFC 1918).\n"
        "<!-- table-style: clases purpose=reference -->\n\n"
        "| Clase | Rango | Máscara |\n"
        "|---|---|---:|\n"
        "| A | 1 a 126 | 255.0.0.0 |\n"
        "| B | 128 a 191 | 255.255.0.0 |\n"
    )


def test_auto_keeps_the_empty_header_when_the_caption_count_differs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = "# Informe\n\nTabla 3. Datos (nombre; valor).\n\n- a; 1; 2\n- b; 3; 4\n"
    folder = _folder(tmp_path, body)

    assert typeset.main(["auto", str(folder)]) == 0

    assert _typeset_text(folder) == (
        "# Informe\n\nTabla 3. Datos (nombre; valor).\n\n|  |  |  |\n|---|---:|---:|\n| a | 1 | 2 |\n| b | 3 | 4 |\n"
    )
    out = capsys.readouterr().out
    assert (
        "  left for you: line 5: table without column names: name its 3 columns "
        "(the caption names 2: fix the caption or the rows)"
    ) in out


def test_auto_points_at_a_list_that_a_stray_semicolon_kept_from_being_a_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = "# Informe\n\n- a; b; c\n- d; e; f; g\n- h; i; j\n"
    folder = _folder(tmp_path, body)

    assert typeset.main(["auto", str(folder)]) == 0

    assert _typeset_text(folder) == body
    assert (
        "  left for you: line 3: list rows with 3, 4 cells: a stray ';' keeps it from becoming a table"
        in capsys.readouterr().out
    )


# S5: a 'Figura:' line merged with the next sentence (delivered APE 7 PDF).
def test_auto_splits_the_sentence_merged_into_a_figura_line(tmp_path: Path) -> None:
    body = (
        "# Informe\n\n"
        "Figura: Partes de una dirección IPv6 y su forma abreviada (figures/diag-03-ipv6-estructura.png) "
        "La Tabla 8 resume los tipos de direcciones.\n"
        "Figura: Topología (figures/pt-01.png)\n"
        "Sigue el texto.\n"
    )
    folder = _folder(tmp_path, body)

    assert typeset.main(["auto", str(folder)]) == 0

    assert _typeset_text(folder) == (
        "# Informe\n\n"
        "![Partes de una dirección IPv6 y su forma abreviada](figures/diag-03-ipv6-estructura.png)\n\n"
        "La Tabla 8 resume los tipos de direcciones.\n\n"
        "![Topología](figures/pt-01.png)\n\n"
        "Sigue el texto.\n"
    )
    assert _check(folder)["figure_leftovers"]["ok"]

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
        "| A | 1 a 126 | `255.0.0.0` |\n"
        "| B | 128 a 191 | `255.255.0.0` |\n"
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


# ---------------------------------------------------------------------------
# odd/tasks/skill-visual-organization.md S9: technical tokens in monospace and
# key terms in bold, applied by auto in body.typeset.md only.
# ---------------------------------------------------------------------------

import typeset_auto  # noqa: E402


@pytest.mark.parametrize(
    ("kind", "token"),
    [
        ("mac", "38:a7:46:39:d2:7b"),
        ("mac", "38-A7-46-39-D2-7B"),
        ("mac", "0001.6453.DBC1"),
        ("ipv4", "192.168.10.0/24"),
        ("ipv4", "10.0.0.1"),
        ("ipv6", "fe80::/10"),
        ("ipv6", "2001:db8::ff00:42:8329"),
        ("ipv6", "2001:0db8:0000:0000:0000:ff00:0042:8329"),
        ("ipv6", "::1"),
        ("ipv6", "ff02::1"),
        ("interface", "Fa0/24"),
        ("interface", "FastEthernet0/1"),
        ("interface", "Gi0/1"),
        ("binary", "00111000"),
        ("binary", "11000000.10101000.00001010.00000001"),
        ("hex", "0x0800"),
        ("command", "show mac address-table"),
        ("command", "clear mac address-table dynamic"),
        ("command", "mac address-table static"),
        ("command", "ipconfig /all"),
        ("command", "ip -6 addr show"),
        ("command", "ping"),
    ],
)
def test_auto_wraps_each_kind_of_technical_token_in_inline_code(kind: str, token: str) -> None:
    text, counts = typeset_auto.auto_format(f"# Informe\n\nEl valor {token} aparece aquí.\n")

    assert text == f"# Informe\n\nEl valor `{token}` aparece aquí.\n"
    assert counts["code"] == 1 and counts[f"code_{kind}"] == 1


def test_auto_wraps_tokens_in_list_items_table_cells_and_range_endpoints() -> None:
    body = (
        "# Informe\n\n"
        "- La PC0 usa 192.168.1.10 en Fa0/1.\n\n"
        "Tabla 1. Equipos (equipo; MAC; rango).\n"
        "- PC0; 0001.6453.DBC1; 192.168.1.1-192.168.1.254\n"
        "- PC1; 38:A7:46:39:D2:7B; 10.0.0.1 - 10.0.0.254\n\n"
        "| Puerto | IP |\n|---|---|\n| Gi0/1 | 172.16.0.1/16 |\n"
    )
    text, counts = typeset_auto.auto_format(body)

    assert "- La PC0 usa `192.168.1.10` en `Fa0/1`.\n" in text
    assert "| PC0 | `0001.6453.DBC1` | `192.168.1.1`-`192.168.1.254` |" in text
    assert "| PC1 | `38:A7:46:39:D2:7B` | `10.0.0.1` - `10.0.0.254` |" in text
    assert "| `Gi0/1` | `172.16.0.1/16` |" in text
    assert counts["code"] == 10


def test_auto_leaves_tokens_alone_where_they_are_not_prose() -> None:
    body = (
        "# Red 192.168.1.0/24\n\n"
        "## Puerto Fa0/1\n\n"
        "Tabla 2. Rango 10.0.0.0/8 del laboratorio.\n\n"
        "Figura: MAC 0001.6453.DBC1 (figures/mac.png)\n\n"
        "![Captura de 10.0.0.1](figures/a.png)\n\n"
        "Ver <http://192.168.0.1/x>, http://10.0.0.1/y y [panel](http://10.1.1.1/z) [@rfc4291].\n"
        "Ya formateado `ping 10.0.0.1` y $2^{8}$.\n"
        "<!-- table-style: tabla-2 purpose=reference 10.0.0.1 -->\n\n"
        "```\n"
        "show mac address-table\n"
        "```\n\n"
        "    ping 10.0.0.1\n"
    )
    text, counts = typeset_auto.auto_format(body)

    expected = body.replace(
        "Figura: MAC 0001.6453.DBC1 (figures/mac.png)", "![MAC 0001.6453.DBC1](figures/mac.png)"
    ).replace("http://10.0.0.1/y", "<http://10.0.0.1/y>")
    assert text == expected
    assert counts["code"] == 0


def test_auto_ignores_lookalikes_in_ordinary_prose() -> None:
    body = (
        "# Informe\n\n"
        "A las 10:30 se midió 3.14 y la versión 1.2.3; el /24 suelto, 2024-11-24, "
        "12345678 y el pingüino Faro0 quedan igual: hacemos pings.\n"
    )
    text, counts = typeset_auto.auto_format(body)

    assert text == body
    assert counts["code"] == 0


def test_auto_token_wrapping_is_idempotent() -> None:
    body = (
        "# Informe\n\nUsar show mac address-table en Fa0/24 y ping 192.168.1.1 (MAC 0001.6453.DBC1, "
        "fe80::1, 0x0800, 00111000).\n\n"
        "Tabla 1. Equipos (equipo; MAC; IP).\n- PC0; 0001.6453.DBC1; 10.0.0.1\n- PC1; 0001.6453.DBC2; 10.0.0.2\n"
    )
    once, _ = typeset_auto.auto_format(body)
    twice, counts = typeset_auto.auto_format(once)

    assert twice == once
    assert counts["code"] == 0
    assert "``" not in once


def test_auto_bolds_the_first_key_term_per_section_only() -> None:
    body = (
        "# Resultados\n\n"
        "La dirección MAC identifica la tarjeta; la dirección MAC no cambia.\n"
        "El ARP resuelve la MAC.\n\n"
        "## Tabla ARP\n\n"
        "ARP\n\n"
        "- Cada entrada ARP guarda una dirección MAC.\n\n"
        "| Término | Uso |\n|---|---|\n| ARP | resolver |\n\n"
        "Ver `arp -a` y dirección MAC [@rfc826].\n"
    )
    text, counts = typeset_auto.auto_format(body, key_terms=["ARP", "dirección MAC"])

    assert text == (
        "# Resultados\n\n"
        "La **dirección MAC** identifica la tarjeta; la dirección MAC no cambia.\n"
        "El **ARP** resuelve la MAC.\n\n"
        "## Tabla ARP\n\n"
        "ARP\n\n"
        "- Cada entrada **ARP** guarda una **dirección MAC**.\n\n"
        "| Término | Uso |\n|---|---|\n| ARP | resolver |\n\n"
        "Ver `arp -a` y dirección MAC [@rfc826].\n"
    )
    assert counts["bold"] == 4
    assert typeset_auto.auto_format(text, key_terms=["ARP", "dirección MAC"])[0] == text


def test_auto_never_bolds_without_key_terms() -> None:
    body = "# Informe\n\nLa dirección MAC identifica la tarjeta.\n"
    text, counts = typeset_auto.auto_format(body)

    assert "**" not in text
    assert counts["bold"] == 0


def test_auto_reads_key_terms_from_report_yml(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _folder(tmp_path, "# Informe\n\nLa dirección MAC de la PC0 es 0001.6453.DBC1 [@key1].\n")
    with (folder / "report.yml").open("a", encoding="utf-8") as handle:
        handle.write("key_terms: [dirección MAC]\n")

    assert typeset.main(["auto", str(folder)]) == 0

    assert _typeset_text(folder) == "# Informe\n\nLa **dirección MAC** de la PC0 es `0001.6453.DBC1` [@key1].\n"
    assert "1 technical token(s) in code, 1 key term(s) in bold" in capsys.readouterr().out
    checks = _check(folder)
    assert checks["body_format"]["ok"] and checks["binding"]["ok"] and checks["citations_match"]["ok"]


def test_auto_help_documents_the_token_list(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        typeset.main(["auto", "--help"])

    out = " ".join(capsys.readouterr().out.split())
    assert "key_terms" in out
    for command in typeset_auto.CLI_COMMANDS:
        assert command in out
    for kind in typeset_auto.TECHNICAL_TOKEN_KINDS:
        assert kind in out


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Se hizo ping 192.168.1.1 y luego ping a la PC.", "Se hizo `ping 192.168.1.1` y luego `ping` a la PC."),
        ("Máscara 255.255.255.0.", "Máscara `255.255.255.0`."),
        ("La ruta ::/0 y el :: suelto.", "La ruta `::/0` y el :: suelto."),
        ("Ver figures/192.168.1.1.png y logs/0001.6453.DBC1.txt.", "Ver `figures/192.168.1.1.png` y `logs/0001.6453.DBC1.txt`."),
        ("Ver **192.168.1.1** ahora.", "Ver **`192.168.1.1`** ahora."),
    ],
)
def test_auto_token_edges(line: str, expected: str) -> None:
    assert typeset_auto.wrap_technical_tokens(line)[0] == expected


@pytest.mark.parametrize(
    "token",
    ["APE2-F2-mac-ip.pkt", "report.yml", "configs/sw1-running.txt", "captura_01.pcapng", "body.typeset.md"],
)
def test_auto_wraps_file_names_in_inline_code(token: str) -> None:
    text, counts = typeset_auto.auto_format(f"# Informe\n\nEl archivo {token} se entrega.\n")

    assert text == f"# Informe\n\nEl archivo `{token}` se entrega.\n"
    assert counts["code"] == 1 and counts["code_file"] == 1


def test_auto_leaves_dotted_words_and_figure_path_leftovers_alone() -> None:
    # A '(figures/x.png)' leftover must stay visible to the figure_leftovers check.
    body = "# Informe\n\nVer uic.io, acortar.link, 3.14, e.g. y (figures/diag-03.png) aquí.\n"
    text, counts = typeset_auto.auto_format(body)

    assert text == body
    assert counts["code"] == 0


def test_auto_leaves_display_math_blocks_alone() -> None:
    body = "# Informe\n\n$$\n192.168.1.1 \\wedge 255.255.255.0\n$$\n\n\\[\nping 10.0.0.1\n\\]\n"
    text, counts = typeset_auto.auto_format(body)

    assert text == body
    assert counts["code"] == 0


def test_auto_bolds_the_first_definition_of_a_term_per_section() -> None:
    body = (
        "# Seguridad\n\n"
        "El MAC flooding es un ataque que satura al switch.\n\n"
        "El MAC flooding es un ataque frecuente en laboratorios.\n\n"
        "- Port security es una función del switch que limita las MAC.\n\n"
        "## Ataques\n\n"
        "El ARP spoofing, o envenenamiento de la caché ARP, es un ataque de capa 2.\n\n"
        "Dynamic ARP Inspection (DAI) es una defensa del switch.\n\n"
        "El MAC flooding es un ataque que vuelve a definirse aquí.\n"
    )
    text, counts = typeset_auto.auto_format(body)

    assert text == (
        "# Seguridad\n\n"
        "El **MAC flooding** es un ataque que satura al switch.\n\n"
        "El MAC flooding es un ataque frecuente en laboratorios.\n\n"
        "- **Port security** es una función del switch que limita las MAC.\n\n"
        "## Ataques\n\n"
        "El **ARP spoofing**, o envenenamiento de la caché ARP, es un ataque de capa 2.\n\n"
        "**Dynamic ARP Inspection** (DAI) es una defensa del switch.\n\n"
        "El **MAC flooding** es un ataque que vuelve a definirse aquí.\n"
    )
    assert counts["bold"] == 5
    assert typeset_auto.auto_format(text)[0] == text


def test_auto_does_not_bold_non_definitions() -> None:
    body = (
        "# Informe\n\n"
        "El primero es la dirección real de la PC.\n\n"
        "El resultado es un valor esperado.\n\n"
        "Esto es una prueba.\n\n"
        "Una dirección MAC tiene 48 bits y es un identificador.\n\n"
        "Para mitigarlo se usa port security, que es una función del switch.\n\n"
        "## La capa de enlace es un nivel\n\n"
        "Tabla 1. El switch es un equipo de capa 2.\n\n"
        "Ya **definido**: el switch es un equipo.\n"
    )
    text, counts = typeset_auto.auto_format(body)

    assert text == body
    assert counts["bold"] == 0


def test_auto_definition_bold_skips_a_term_already_bolded_by_key_terms() -> None:
    body = "# Informe\n\nEl switch reenvía tramas.\n\nEl switch es un equipo de capa 2.\n"
    text, counts = typeset_auto.auto_format(body, key_terms=["switch"])

    assert text == "# Informe\n\nEl **switch** reenvía tramas.\n\nEl switch es un equipo de capa 2.\n"
    assert counts["bold"] == 1


def test_auto_bolds_definitions_only_where_a_paragraph_or_list_item_opens() -> None:
    body = (
        "El switch es un equipo de capa 2.\n"
        "El router es un equipo de capa 3 en la misma línea de párrafo.\n\n"
        "# Red\n"
        "El hub es un repetidor multipuerto.\n"
    )
    text, counts = typeset_auto.auto_format(body)

    assert text == (
        "El **switch** es un equipo de capa 2.\n"
        "El router es un equipo de capa 3 en la misma línea de párrafo.\n\n"
        "# Red\n"
        "El **hub** es un repetidor multipuerto.\n"
    )
    assert counts["bold"] == 2


# T11 (S9): partial IPv6 tokens and hex placeholders are technical tokens too.
@pytest.mark.parametrize(
    "token",
    ["ff02::1:ffXX:XXXX", "ff:fe", "1ee3:56db:e4ad:3dab", "0a00:27ff:fe4e:66a1", "fe80::1ee3:56db:e4ad:3dab"],
)
def test_auto_wraps_partial_ipv6_and_placeholder_tokens(token: str) -> None:
    text, counts = typeset_auto.auto_format(f"# Informe\n\nEl valor {token} aparece aquí.\n")

    assert text == f"# Informe\n\nEl valor `{token}` aparece aquí.\n"
    assert counts["code"] == 1 and counts["code_ipv6"] == 1


def test_auto_leaves_times_ratios_and_colon_prose_alone() -> None:
    body = (
        "# Informe\n\n"
        "A las 10:30 y a las 12:30:45 la relación fue 3:1 y luego 16:9; nota: a:b, "
        "caso:de estudio, Café: listo y la hora 08:00.\n"
    )
    text, counts = typeset_auto.auto_format(body)

    assert text == body
    assert counts["code"] == 0

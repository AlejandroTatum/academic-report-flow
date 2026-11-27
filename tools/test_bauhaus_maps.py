"""Bauhaus técnico maps: fonts, concept maps and process maps rendered from a YAML spec.

Every test drives the public interface: the ``render`` CLI (exit code, stderr, files on disk)
and the SVG it writes (colours, fonts, text, geometry).
"""
from __future__ import annotations

import copy
import hashlib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import editorial_svg
import pytest
import yaml

TOOL = Path(__file__).resolve().parent / "bauhaus_maps.py"
FONTS = Path(__file__).resolve().parents[1] / "assets" / "fonts"
needs_dot = pytest.mark.skipif(shutil.which("dot") is None, reason="Graphviz dot is not installed")
needs_rsvg = pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="rsvg-convert is not installed")

BG, INK, MUTED = "#F6F4EE", "#121212", "#4A4A4A"
# Pastel by default: fills, deeper pastel lines/borders, and dark text for words set in a family colour.
BLUE, RED, GREEN, SAFFRON = "#B9CBF0", "#F7C3B6", "#B5E3CF", "#F9DD94"
LINE = {BLUE: "#8FA8E0", RED: "#EE9F8C", GREEN: "#7FC6A8", "#121212": "#121212"}
# Words in a family colour on paper are the saturated hue at 85 % over black, for contrast.
SHADE = {BLUE: "#1D3C9A", RED: "#BE3B24", GREEN: "#0B765C"}
WHITE, ON_FILL = "#FFFFFF", "#2B2B38"
SIZE_LIMIT = 860

CONCEPT_SPEC = {
    "kind": "concept_map",
    "title": "Spec-Driven Development en el proyecto de prácticas",
    "core": {"id": "sdd", "name": "Spec-Driven Development", "subtitle": "desarrollo guiado por especificaciones"},
    "families": {
        "que": {"label": "QUÉ", "color": "blue", "meaning": "problema y requisitos"},
        "reglas": {"label": "REGLAS", "color": "red", "meaning": "principios del proyecto"},
        "como": {"label": "CÓMO", "color": "green", "meaning": "solución técnica"},
    },
    "concepts": [
        {"id": "spec", "name": "Especificación", "detail": "spec.md: qué y por qué", "family": "que", "level": "key"},
        {"id": "const", "name": "Constitución", "detail": "principios del proyecto", "family": "reglas", "level": "key"},
        {"id": "problema", "name": "Problema", "detail": "lo que se quiere cambiar", "family": "que"},
        {"id": "req", "name": "Requisitos", "detail": "verificables", "family": "que"},
        {"id": "clar", "name": "Clarificación", "detail": "hasta 5 preguntas", "family": "que"},
        {"id": "plan", "name": "Plan técnico", "detail": "stack y datos", "family": "como"},
        {"id": "tareas", "name": "Tareas", "detail": "unidades verificables", "family": "como"},
        {"id": "codigo", "name": "Código", "detail": "se genera o se verifica", "family": "como"},
    ],
    "links": [
        {"from": "sdd", "to": "spec", "label": "toma como artefacto principal"},
        {"from": "sdd", "to": "const", "label": "se rige por"},
        {"from": "spec", "to": "problema", "label": "se escribe en el dominio del"},
        {"from": "spec", "to": "req", "label": "reúne"},
        {"from": "spec", "to": "plan", "label": "se traduce en"},
        {"from": "spec", "to": "clar", "label": "se depura con"},
        {"from": "const", "to": "plan", "label": "evalúa", "cross": True},
        {"from": "plan", "to": "tareas", "label": "se parte en"},
        {"from": "tareas", "to": "req", "label": "son rastreables a", "cross": True},
        {"from": "tareas", "to": "codigo", "label": "guían el"},
    ],
    "spine": ["sdd", "spec", "plan", "tareas", "codigo"],
}

PROCESS_SPEC = {
    "kind": "process_map",
    "title": "Flujo SDD con GitHub Spec Kit",
    "lanes": [
        {"id": "equipo", "label": "EQUIPO DE DESARROLLO", "short": "EQUIPO"},
        {"id": "ia", "label": "ASISTENTE CON SPEC KIT", "short": "ASISTENTE"},
    ],
    "artifact_lane": {"label": "ARTEFACTO"},
    "steps": [
        {"id": "s1", "lane": "equipo", "title": "Fijar principios", "detail": "/constitution", "artifact": "constitution.md"},
        {"id": "s2", "lane": "ia", "title": "Especificar", "detail": "/specify: qué y por qué", "artifact": "spec.md"},
        {"id": "d1", "lane": "equipo", "title": "¿Quedan ambigüedades?", "decision": True},
        {"id": "s3", "lane": "ia", "title": "Preguntar y registrar", "detail": "/clarify: hasta 5 preguntas",
         "artifact": "spec.md actualizado"},
        {"id": "s4", "lane": "ia", "title": "Diseñar la solución", "detail": "/plan: stack y datos",
         "artifact": "plan.md · data-model.md"},
        {"id": "s5", "lane": "ia", "title": "Partir en tareas", "detail": "/tasks", "artifact": "tasks.md"},
        {"id": "s6", "lane": "equipo", "title": "Implementar y verificar", "detail": "contra la especificación"},
    ],
    "flow": [
        {"from": "s1", "to": "s2"}, {"from": "s2", "to": "d1"},
        {"from": "d1", "to": "s3", "label": "sí"}, {"from": "s3", "to": "d1"},
        {"from": "d1", "to": "s4", "label": "no"},
        {"from": "s4", "to": "s5"}, {"from": "s5", "to": "s6"},
    ],
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def run_cli(*args: object, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True, env=env)


def write_spec(tmp_path: Path, spec: dict) -> Path:
    path = tmp_path / "spec.yml"
    path.write_text(yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def render(tmp_path: Path, spec: dict, *extra: object) -> tuple[subprocess.CompletedProcess, Path]:
    out = tmp_path / "fig.svg"
    return run_cli("render", write_spec(tmp_path, spec), "--out", out, *extra), out


def svg_root(tmp_path: Path, spec: dict) -> ET.Element:
    result, out = render(tmp_path, spec)
    assert result.returncode == 0, result.stderr
    return ET.fromstring(out.read_text(encoding="utf-8"))


def tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def find(root: ET.Element, name: str, **attrs: str) -> list[ET.Element]:
    return [e for e in root.iter() if tag(e) == name and all(e.get(k.replace("_", "-")) == v for k, v in attrs.items())]


def texts(root: ET.Element) -> list[ET.Element]:
    return find(root, "text")


def text_of(root: ET.Element, value: str) -> ET.Element:
    found = [e for e in texts(root) if "".join(e.itertext()) == value]
    assert found, f"no text {value!r}"
    return found[0]


def box(element: ET.Element) -> tuple[float, float, float, float]:
    """x0, y0, x1, y1 of a rect or an axis-aligned polygon."""
    if tag(element) == "rect":
        x, y, w, h = (float(element.get(k)) for k in ("x", "y", "width", "height"))
        return x, y, x + w, y + h
    points = [tuple(map(float, p.split(","))) for p in element.get("points").split()]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def node_box(root: ET.Element, node_id: str) -> tuple[float, float, float, float]:
    found = find(root, "rect", data_node=node_id) + find(root, "polygon", data_node=node_id)
    assert len(found) == 1, node_id
    return box(found[0])


def path_points(d: str) -> list[tuple[float, float]]:
    """Vertices of a path made of absolute M/L/H/V commands (straight, orthogonal connectors)."""
    points: list[tuple[float, float]] = []
    for command, args in re.findall(r"([MLHV])([^MLHV]*)", d):
        numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", args)]
        if command in "ML":
            points.append((numbers[0], numbers[1]))
        elif command == "H":
            points.append((numbers[0], points[-1][1]))
        else:
            points.append((points[-1][0], numbers[0]))
    return points


def crosses_box(points: list[tuple[float, float]], rect: tuple[float, float, float, float]) -> bool:
    """True when an axis-aligned segment of the polyline enters the open interior of ``rect``."""
    x0, y0, x1, y1 = rect
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        sx0, sx1, sy0, sy1 = min(ax, bx), max(ax, bx), min(ay, by), max(ay, by)
        if sx1 > x0 + 1e-6 and sx0 < x1 - 1e-6 and sy1 > y0 + 1e-6 and sy0 < y1 - 1e-6:
            return True
    return False


def canvas_width(root: ET.Element) -> float:
    return float(root.get("width"))


# --------------------------------------------------------------------------
# T1 · shipped fonts
# --------------------------------------------------------------------------

def test_space_grotesk_ships_in_the_repo_with_its_licence() -> None:
    font = FONTS / "SpaceGrotesk[wght].ttf"
    assert font.is_file() and font.stat().st_size > 10_000
    assert "SIL OPEN FONT LICENSE" in (FONTS / "OFL.txt").read_text(encoding="utf-8").upper()


@pytest.fixture(autouse=True)
def _caller_font_environment_is_out_of_the_picture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Whatever FONTCONFIG_FILE or HOME the caller has, PNG tests start from a clean slate."""
    for name in ("FONTCONFIG_FILE", "FONTCONFIG_PATH"):
        monkeypatch.delenv(name, raising=False)
    for name in ("HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "XDG_CONFIG_HOME"):
        monkeypatch.setenv(name, str(tmp_path / "caller-home"))


def test_png_fontconfig_adds_the_repo_font_folder_to_the_system_fonts(tmp_path: Path) -> None:
    import bauhaus_maps

    conf = bauhaus_maps.write_fontconfig(tmp_path)
    text_ = conf.read_text(encoding="utf-8")
    assert f"<dir>{FONTS}</dir>" in text_ and "/etc/fonts/fonts.conf" in text_


@pytest.mark.skipif(shutil.which("fc-match") is None, reason="fc-match is not installed")
def test_generated_fontconfig_resolves_space_grotesk_to_the_repo_file(tmp_path: Path) -> None:
    import bauhaus_maps

    conf = bauhaus_maps.write_fontconfig(tmp_path)
    env = {"FONTCONFIG_FILE": str(conf), "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    for query in ("Space Grotesk:weight=bold", "Space Grotesk"):
        match = subprocess.run(["fc-match", "-f", "%{family}|%{file}", query], capture_output=True, text=True, env=env)
        family, _, file = match.stdout.partition("|")
        assert "Space Grotesk" in family, match.stdout
        assert Path(file).resolve() == (FONTS / "SpaceGrotesk[wght].ttf").resolve(), match.stdout


def fake_tool(directory: Path, name: str, body: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    tool = directory / name
    tool.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    tool.chmod(0o755)


def test_png_rasterising_uses_its_own_fontconfig_whatever_the_caller_exports(tmp_path: Path) -> None:
    seen = tmp_path / "seen.conf"
    bin_dir = tmp_path / "bin"
    fake_tool(bin_dir, "rsvg-convert", f'cat > /dev/null\ncp "$FONTCONFIG_FILE" "{seen}"\nprintf PNG > "$4"')
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "FONTCONFIG_FILE": "/nonexistent/caller.conf", "FONTCONFIG_PATH": "/nonexistent",
           "HOME": "/nonexistent"}
    out, png = tmp_path / "fig.svg", tmp_path / "fig.png"
    result = run_cli("render", write_spec(tmp_path, PROCESS_SPEC), "--out", out, "--png", png, env=env)
    assert result.returncode == 0, result.stderr
    assert f"<dir>{FONTS}</dir>" in seen.read_text(encoding="utf-8")
    assert png.read_bytes() == b"PNG"


# --------------------------------------------------------------------------
# T1 · concept map: style tokens
# --------------------------------------------------------------------------

@needs_dot
def test_concept_map_renders_a_valid_svg_and_reports_it(tmp_path: Path) -> None:
    result, out = render(tmp_path, CONCEPT_SPEC)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"rendered {out}"
    root = ET.fromstring(out.read_text(encoding="utf-8"))
    assert tag(root) == "svg"


@needs_dot
def test_concept_map_uses_only_space_grotesk_in_four_weights(tmp_path: Path) -> None:
    root = svg_root(tmp_path, CONCEPT_SPEC)
    assert {t.get("font-family") for t in texts(root)} == {"Space Grotesk, sans-serif"}
    assert {t.get("font-weight") for t in texts(root)} <= {"400", "500", "600", "700"}
    assert find(root, "rect", width=root.get("width"), fill=BG), "paper background"


@needs_dot
def test_concept_map_header_has_red_kind_label_muted_title_and_hairline(tmp_path: Path) -> None:
    root = svg_root(tmp_path, CONCEPT_SPEC)
    kind = text_of(root, "MAPA CONCEPTUAL")
    assert kind.get("fill") == SHADE[RED] and kind.get("letter-spacing") == "2.2"
    title = text_of(root, CONCEPT_SPEC["title"])
    assert title.get("fill") == MUTED and float(title.get("x")) > float(kind.get("x"))
    assert title.get("y") == kind.get("y")
    rules = [e for e in find(root, "line") if e.get("data-legend") is None and e.get("y1") == e.get("y2")]
    assert any(float(e.get("y1")) > float(kind.get("y")) for e in rules), "hairline below the header"


@needs_dot
def test_core_concept_is_a_solid_ink_box_with_white_title_and_saffron_subtitle(tmp_path: Path) -> None:
    root = svg_root(tmp_path, CONCEPT_SPEC)
    (core,) = find(root, "rect", data_node="sdd")
    assert core.get("fill") == INK
    title = text_of(root, "Spec-Driven Development")
    assert title.get("fill") == WHITE and title.get("font-weight") == "700"
    sub = text_of(root, "DESARROLLO GUIADO POR ESPECIFICACIONES")
    assert sub.get("fill") == SAFFRON


@needs_dot
def test_key_concepts_are_solid_pastel_with_dark_text(tmp_path: Path) -> None:
    root = svg_root(tmp_path, CONCEPT_SPEC)
    for node_id, colour, name in (("spec", BLUE, "Especificación"), ("const", RED, "Constitución")):
        (rect,) = find(root, "rect", data_node=node_id)
        assert rect.get("fill") == colour
        assert text_of(root, name).get("fill") == ON_FILL


@needs_dot
def test_no_text_on_a_pastel_family_fill_is_white(tmp_path: Path) -> None:
    concept, process = svg_root(tmp_path, CONCEPT_SPEC), svg_root(tmp_path, PROCESS_SPEC)
    white = ["".join(t.itertext()) for t in texts(concept) if t.get("fill") == WHITE]
    assert white == ["Spec-Driven Development"], "white text only on the ink core"
    assert not [t for t in texts(process) if t.get("fill") == WHITE], "no ink lane here, so no white text"
    for root in (concept, process):
        assert {t.get("fill") for t in texts(root)}.isdisjoint({BLUE, RED, GREEN}), "no pastel text"


@needs_dot
def test_leaves_are_white_with_a_family_border_and_a_corner_square(tmp_path: Path) -> None:
    root = svg_root(tmp_path, CONCEPT_SPEC)
    for node_id, colour in (("problema", BLUE), ("plan", GREEN), ("codigo", GREEN)):
        (rect,) = find(root, "rect", data_node=node_id)
        assert (rect.get("fill"), rect.get("stroke"), rect.get("stroke-width")) == (WHITE, LINE[colour], "3")
        (corner,) = find(root, "rect", data_corner=node_id)
        assert (corner.get("width"), corner.get("height"), corner.get("fill")) == ("14", "14", LINE[colour])
        assert (corner.get("x"), corner.get("y")) == (rect.get("x"), rect.get("y"))


@needs_dot
def test_colour_encodes_the_family_never_one_colour_per_node(tmp_path: Path) -> None:
    root = svg_root(tmp_path, CONCEPT_SPEC)
    fills = {find(root, "rect", data_node=n)[0].get("stroke") or find(root, "rect", data_node=n)[0].get("fill")
             for n in ("spec", "problema", "req", "clar")}
    assert fills == {BLUE, LINE[BLUE]}
    colours = {e.get(a) for e in root.iter() for a in ("fill", "stroke")}
    assert {BLUE, RED, LINE[GREEN], SAFFRON, INK} <= colours  # no green key concept, so green is a line only


@needs_dot
def test_every_link_carries_its_phrase_coloured_by_the_source_family(tmp_path: Path) -> None:
    root = svg_root(tmp_path, CONCEPT_SPEC)
    for link in CONCEPT_SPEC["links"]:
        label = find(root, "text", data_label=f"{link['from']}>{link['to']}")
        assert len(label) == 1 and "".join(label[0].itertext()) == link["label"], link
    family = {c["id"]: c["family"] for c in CONCEPT_SPEC["concepts"]}
    colour = {"que": BLUE, "reglas": RED, "como": GREEN}
    assert find(root, "text", data_label="spec>req")[0].get("fill") == SHADE[BLUE]
    assert find(root, "text", data_label="const>plan")[0].get("fill") == SHADE[colour[family["const"]]]
    assert find(root, "text", data_label="plan>tareas")[0].get("fill") == SHADE[GREEN]
    assert find(root, "text", data_label="sdd>spec")[0].get("fill") == MUTED


@needs_dot
def test_cross_links_are_dashed_and_other_links_are_solid(tmp_path: Path) -> None:
    root = svg_root(tmp_path, CONCEPT_SPEC)
    cross = {f"{l['from']}>{l['to']}" for l in CONCEPT_SPEC["links"] if l.get("cross")}
    paths = {p.get("data-link"): p for p in find(root, "path") if p.get("data-link")}
    assert set(paths) == {f"{l['from']}>{l['to']}" for l in CONCEPT_SPEC["links"]}
    for name, path in paths.items():
        assert (path.get("stroke-dasharray") == "6 5") == (name in cross), name


@needs_dot
def test_legend_has_a_coloured_line_a_bold_uppercase_label_and_its_meaning(tmp_path: Path) -> None:
    root = svg_root(tmp_path, CONCEPT_SPEC)
    for family, colour in (("que", BLUE), ("reglas", RED), ("como", GREEN)):
        (line,) = find(root, "line", data_legend=family)
        assert line.get("stroke") == LINE[colour] and line.get("stroke-width") == "4"
        assert abs(float(line.get("x2")) - float(line.get("x1")) - 22) < 1e-6
    label = text_of(root, "QUÉ")
    assert label.get("font-weight") == "700" and label.get("fill") == SHADE[BLUE]
    assert text_of(root, "problema y requisitos").get("fill") == MUTED
    assert not [e for e in find(root, "rect") if e.get("data-legend")], "no chip grid"
    foot = max(float(e.get("y1")) for e in find(root, "line", data_legend="que"))
    assert foot > max(box(r)[3] for r in find(root, "rect") if r.get("data-node")), "legend sits at the foot"


# --------------------------------------------------------------------------
# T1 · concept map: layout
# --------------------------------------------------------------------------

@needs_dot
def test_cross_links_do_not_shape_the_ranks(tmp_path: Path) -> None:
    spec = copy.deepcopy(CONCEPT_SPEC)
    root = svg_root(tmp_path, spec)
    # tareas -> req and const -> plan are cross-links: req stays level with its siblings
    # and plan stays one rank below spec, as if the dashed links were absent.
    assert node_box(root, "req")[1] == node_box(root, "problema")[1]
    assert node_box(root, "plan")[1] == node_box(root, "problema")[1]
    assert node_box(root, "tareas")[1] > node_box(root, "plan")[3]


@needs_dot
def test_spine_is_a_straight_central_axis(tmp_path: Path) -> None:
    def spread(root: ET.Element) -> float:
        centres = [(node_box(root, n)[0] + node_box(root, n)[2]) / 2 for n in CONCEPT_SPEC["spine"]]
        return max(centres) - min(centres)

    assert spread(svg_root(tmp_path, CONCEPT_SPEC)) < 0.3  # one vertical axis (rounding only)
    small = {"kind": "concept_map", "title": "T", "core": {"id": "c", "name": "Centro"},
             "families": {"f": {"label": "F", "color": "blue"}},
             "concepts": [{"id": n, "name": n.upper(), "family": "f"} for n in ("x", "a", "b")],
             "links": [{"from": "c", "to": "x", "label": "incluye"}, {"from": "c", "to": "a", "label": "incluye"},
                       {"from": "a", "to": "b", "label": "incluye"}], "spine": ["c", "a", "b"]}
    centres = lambda root: [(node_box(root, n)[0] + node_box(root, n)[2]) / 2 for n in ("c", "a", "b")]  # noqa: E731
    assert max(centres(svg_root(tmp_path, small))) - min(centres(svg_root(tmp_path, small))) < 0.3
    small.pop("spine")
    unspined = centres(svg_root(tmp_path, small))
    assert max(unspined) - min(unspined) > 20


@needs_dot
def test_sibling_order_follows_the_spec(tmp_path: Path) -> None:
    spec = copy.deepcopy(CONCEPT_SPEC)
    root = svg_root(tmp_path, spec)
    order = sorted(("problema", "req", "plan", "clar"), key=lambda n: node_box(root, n)[0])
    assert order == ["problema", "req", "plan", "clar"]  # the order of the spec's links from 'spec'
    small = {"kind": "concept_map", "title": "T", "core": {"id": "c", "name": "Centro"},
             "families": {"f": {"label": "F", "color": "blue"}},
             "concepts": [{"id": name, "name": name.upper(), "family": "f"} for name in ("a", "b", "z")],
             "links": [{"from": "c", "to": name, "label": "incluye"} for name in ("a", "b", "z")]}
    root = svg_root(tmp_path, small)
    assert sorted("abz", key=lambda n: node_box(root, n)[0]) == ["a", "b", "z"]
    small["links"].reverse()  # a flipped order of the spec's links flips the children
    flipped = svg_root(tmp_path, small)
    assert sorted("abz", key=lambda n: node_box(flipped, n)[0]) == ["z", "b", "a"]


@needs_dot
def test_titles_are_centred_in_their_boxes_and_the_canvas_stays_within_the_limit(tmp_path: Path) -> None:
    root = svg_root(tmp_path, CONCEPT_SPEC)
    for concept in CONCEPT_SPEC["concepts"]:
        x0, _, x1, _ = node_box(root, concept["id"])
        centre = (x0 + x1) / 2
        assert abs(float(text_of(root, concept["name"]).get("x")) - centre) < 1.0
    assert 0 < canvas_width(ET.fromstring(Path(tmp_path / "fig.svg").read_text(encoding="utf-8"))) <= SIZE_LIMIT


# --------------------------------------------------------------------------
# T1 · legibility and width
# --------------------------------------------------------------------------

@needs_dot
def test_rendered_concept_map_passes_the_print_size_check(tmp_path: Path) -> None:
    result, out = render(tmp_path, CONCEPT_SPEC)
    assert result.returncode == 0
    svg = out.read_text(encoding="utf-8")
    assert editorial_svg.check(svg) == []
    assert min(size for size, _ in editorial_svg.printed_sizes(svg)) >= 5.5


@needs_dot
def test_a_layout_wider_than_860_units_fails_instead_of_shrinking(tmp_path: Path) -> None:
    spec = copy.deepcopy(CONCEPT_SPEC)
    spec["concepts"] = [
        {"id": f"c{i}", "name": f"Concepto largo número {i}", "detail": "con un detalle bastante extenso",
         "family": "que"} for i in range(8)]
    spec["links"] = [{"from": "sdd", "to": f"c{i}", "label": "incluye"} for i in range(8)]
    spec.pop("spine")
    result, out = render(tmp_path, spec)
    assert result.returncode == 2
    assert re.fullmatch(
        r"bauhaus_maps: layout is \d+ units wide, over the 860-unit limit; the figure is never shrunk, "
        r"so split the map or shorten names and details\n", result.stderr), result.stderr
    assert not out.exists()


# --------------------------------------------------------------------------
# T1 · malformed specs: SpecError names the field, exit 2, no file
# --------------------------------------------------------------------------

def _without(spec: dict, *path: object) -> dict:
    spec = copy.deepcopy(spec)
    target = spec
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]
    return spec


def _with(spec: dict, value: object, *path: object) -> dict:
    spec = copy.deepcopy(spec)
    target = spec
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return spec


CONCEPT_CASES = [
    (_without(CONCEPT_SPEC, "title"), "'title' is required"),
    (_without(CONCEPT_SPEC, "core"), "'core' is required"),
    (_without(CONCEPT_SPEC, "core", "name"), "'core.name' is required"),
    (_without(CONCEPT_SPEC, "concepts"), "'concepts' is required"),
    (_without(CONCEPT_SPEC, "families"), "'families' is required"),
    (_without(CONCEPT_SPEC, "links"), "'links' is required"),
    (_without(CONCEPT_SPEC, "concepts", 0, "name"), "'concepts[0].name' is required"),
    (_without(CONCEPT_SPEC, "concepts", 2, "family"), "'concepts[2].family' is required"),
    (_with(CONCEPT_SPEC, "nope", "concepts", 0, "family"), "'concepts[0].family' is 'nope'; use one of ['como', 'que', 'reglas']"),
    (_with(CONCEPT_SPEC, "huge", "concepts", 0, "level"), "'concepts[0].level' is 'huge'; use one of ['key', 'leaf']"),
    (_with(CONCEPT_SPEC, "spec", "concepts", 1, "id"), "'concepts[1].id' repeats id 'spec'"),
    (_with(CONCEPT_SPEC, "sdd", "concepts", 0, "id"), "'concepts[0].id' repeats id 'sdd'"),
    (_with(CONCEPT_SPEC, "saffron", "families", "que", "color"),
     "'families.que.color' is 'saffron'; use one of ['blue', 'green', 'red']"),
    (_with(CONCEPT_SPEC, "blue", "families", "reglas", "color"), "'families.reglas.color' repeats colour 'blue'"),
    (_without(CONCEPT_SPEC, "families", "que", "label"), "'families.que.label' is required"),
    (_with(CONCEPT_SPEC, "zzz", "links", 0, "to"), "'links[0].to' refers to unknown id 'zzz'"),
    (_with(CONCEPT_SPEC, "zzz", "links", 3, "from"), "'links[3].from' refers to unknown id 'zzz'"),
    (_without(CONCEPT_SPEC, "links", 0, "label"), "'links[0].label' is required"),
    (_with(CONCEPT_SPEC, "yes please", "links", 6, "cross"), "'links[6].cross' must be true or false"),
    (_with(CONCEPT_SPEC, "spec", "links", 1, "to"), "'links[1]' repeats the link 'sdd' -> 'spec'"),
    (_with(CONCEPT_SPEC, "sdd", "links", 1, "to"), "'links[1]' links 'sdd' to itself"),
    (_with(CONCEPT_SPEC, ["sdd", "nope"], "spine"), "'spine[1]' refers to unknown id 'nope'"),
    (_with(CONCEPT_SPEC, "sdd", "spine"), "'spine' must be a list of ids"),
    ({**CONCEPT_SPEC, "kind": "actor_map"},
     "unknown kind 'actor_map'; use one of ['concept_map', 'process_map']"),
    (_without(CONCEPT_SPEC, "kind"), "'kind' is required; use one of ['concept_map', 'process_map']"),
]


@pytest.mark.parametrize(("spec", "message"), CONCEPT_CASES, ids=[m for _, m in CONCEPT_CASES])
def test_malformed_concept_specs_fail_naming_the_field_and_write_nothing(tmp_path: Path, spec: dict, message: str) -> None:
    result, out = render(tmp_path, spec, "--png", tmp_path / "fig.png")
    assert result.returncode == 2
    assert result.stderr == f"bauhaus_maps: {message}\n"
    assert result.stdout == ""
    assert not out.exists() and not (tmp_path / "fig.png").exists()


def test_a_spec_that_is_not_a_yaml_mapping_is_rejected(tmp_path: Path) -> None:
    spec = tmp_path / "spec.yml"
    spec.write_text("- just\n- a list\n", encoding="utf-8")
    out = tmp_path / "fig.svg"
    result = run_cli("render", spec, "--out", out)
    assert (result.returncode, result.stderr) == (2, "bauhaus_maps: the spec must be a YAML mapping\n")
    assert not out.exists()


def test_invalid_yaml_and_missing_spec_file_exit_2_without_output(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yml"
    broken.write_text("kind: [unclosed\n", encoding="utf-8")
    out = tmp_path / "fig.svg"
    for spec in (broken, tmp_path / "absent.yml"):
        result = run_cli("render", spec, "--out", out)
        assert result.returncode == 2 and result.stderr.startswith("bauhaus_maps: ")
        assert not out.exists()


@pytest.mark.skipif(shutil.which("dot") is None, reason="needs a real dot to prove the lookup")
def test_missing_graphviz_is_reported_and_writes_nothing(tmp_path: Path) -> None:
    out = tmp_path / "fig.svg"
    result = run_cli("render", write_spec(tmp_path, CONCEPT_SPEC), "--out", out, env={"PATH": str(tmp_path)})
    assert result.returncode == 2
    assert result.stderr == "bauhaus_maps: Graphviz 'dot' was not found on PATH; install graphviz\n"
    assert not out.exists()


# --------------------------------------------------------------------------
# T1 · PNG
# --------------------------------------------------------------------------

@needs_dot
@needs_rsvg
def test_png_output_is_written_at_twice_the_svg_size(tmp_path: Path) -> None:
    png = tmp_path / "fig.png"
    result, out = render(tmp_path, CONCEPT_SPEC, "--png", png)
    assert result.returncode == 0, result.stderr
    data = png.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    root = ET.fromstring(out.read_text(encoding="utf-8"))
    assert (width, height) == (round(float(root.get("width")) * 2), round(float(root.get("height")) * 2))


@needs_dot
def test_png_without_rsvg_convert_fails_cleanly_and_writes_nothing(tmp_path: Path) -> None:
    out = tmp_path / "fig.svg"
    png = tmp_path / "fig.png"
    dot_dir = tmp_path / "bin"
    dot_dir.mkdir()
    (dot_dir / "dot").symlink_to(shutil.which("dot"))
    result = run_cli("render", write_spec(tmp_path, CONCEPT_SPEC), "--out", out, "--png", png,
                     env={"PATH": str(dot_dir), "HOME": str(tmp_path)})
    assert result.returncode == 2
    assert result.stderr == "bauhaus_maps: rsvg-convert was not found on PATH; install librsvg to use --png\n"
    assert not out.exists() and not png.exists()


# --------------------------------------------------------------------------
# T2 · process map
# --------------------------------------------------------------------------

LANE_TINT = {RED: "#F6E5DD", BLUE: "#E4E8EF", GREEN: "#E2EFE5"}  # 30 % of the pastel lane colour over the paper


def artifact_box(root: ET.Element, step_id: str) -> tuple[float, float, float, float]:
    (shape,) = find(root, "path", data_artifact=step_id)
    xs, ys = zip(*path_points(shape.get("d")))
    return min(xs), min(ys), max(xs), max(ys)


def all_boxes(root: ET.Element) -> dict[str, tuple[float, float, float, float]]:
    boxes = {e.get("data-node"): box(e) for e in root.iter() if tag(e) in ("rect", "polygon") and e.get("data-node")}
    boxes.update({f"artifact:{e.get('data-artifact')}": artifact_box(root, e.get("data-artifact"))
                  for e in find(root, "path") if e.get("data-artifact")})
    return boxes


def connectors(root: ET.Element) -> dict[str, list[tuple[float, float]]]:
    return {e.get("data-edge"): path_points(e.get("d")) for e in find(root, "path") if e.get("data-edge")}


def crosses_diamond(points: list[tuple[float, float]], rect: tuple[float, float, float, float]) -> bool:
    """True when an axis-aligned segment enters the open interior of the diamond inscribed in ``rect``."""
    x0, y0, x1, y1 = rect
    cx, cy, hw, hh = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        if abs(ay - by) < 1e-6:  # horizontal: the diamond is |x - cx| < hw * (1 - |y - cy| / hh) at this height
            reach = hw * (1 - abs(ay - cy) / hh)
            if reach > 0.05 and min(ax, bx) < cx + reach - 0.05 and max(ax, bx) > cx - reach + 0.05:
                return True
        else:
            reach = hh * (1 - abs(ax - cx) / hw)
            if reach > 0.05 and min(ay, by) < cy + reach - 0.05 and max(ay, by) > cy - reach + 0.05:
                return True
    return False


def assert_no_connector_crosses_a_node(root: ET.Element) -> None:
    boxes = all_boxes(root)
    diamonds = {e.get("data-node") for e in find(root, "polygon") if e.get("data-node")}
    assert connectors(root), "no connectors drawn"
    for name, points in connectors(root).items():
        for node_id, rect in boxes.items():
            hit = crosses_diamond(points, rect) if node_id in diamonds else crosses_box(points, rect)
            assert not hit, f"connector {name} crosses node {node_id}"


@pytest.fixture
def process_root(tmp_path: Path) -> ET.Element:
    return svg_root(tmp_path, PROCESS_SPEC)


def test_process_map_renders_at_860_units_and_passes_the_print_size_check(tmp_path: Path) -> None:
    result, out = render(tmp_path, PROCESS_SPEC)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"rendered {out}"
    svg = out.read_text(encoding="utf-8")
    assert canvas_width(ET.fromstring(svg)) == 860
    assert editorial_svg.check(svg) == []


def test_process_map_uses_the_bauhaus_tokens_and_only_space_grotesk(process_root: ET.Element) -> None:
    assert {t.get("font-family") for t in texts(process_root)} == {"Space Grotesk, sans-serif"}
    assert {t.get("font-weight") for t in texts(process_root)} <= {"400", "500", "600", "700"}
    assert find(process_root, "rect", width="860", fill=BG)
    kind = text_of(process_root, "MAPA DE PROCESO")
    assert (kind.get("fill"), kind.get("letter-spacing")) == (SHADE[RED], "2.2")
    title = text_of(process_root, PROCESS_SPEC["title"])
    assert title.get("fill") == MUTED and title.get("y") == kind.get("y")


def test_lanes_are_columns_with_solid_headers_and_tinted_bodies(process_root: ET.Element) -> None:
    lanes = {"equipo": RED, "ia": BLUE, "artifact": GREEN}
    for lane, colour in lanes.items():
        (head,) = find(process_root, "rect", data_lane_header=lane)
        (body,) = find(process_root, "rect", data_lane=lane)
        assert head.get("fill") == colour
        assert body.get("fill") == LANE_TINT[colour]
        assert box(body)[0] == box(head)[0] and box(body)[2] == box(head)[2] and box(body)[1] >= box(head)[3]
    xs = [box(find(process_root, "rect", data_lane=lane)[0])[0] for lane in lanes]
    assert xs == sorted(xs) and len(set(xs)) == 3
    label = text_of(process_root, "EQUIPO DE DESARROLLO")
    assert (label.get("fill"), label.get("font-weight")) == (ON_FILL, "700")


def test_steps_are_white_boxes_with_a_lane_border_and_a_numbered_corner_square(process_root: ET.Element) -> None:
    expected = {"s1": (RED, "1"), "s2": (BLUE, "2"), "s3": (BLUE, "3"), "s4": (BLUE, "4"), "s5": (BLUE, "5"),
                "s6": (RED, "6")}
    for step_id, (colour, number) in expected.items():
        (rect,) = find(process_root, "rect", data_node=step_id)
        assert (rect.get("fill"), rect.get("stroke"), rect.get("stroke-width")) == (WHITE, LINE[colour], "3")
        (corner,) = find(process_root, "rect", data_corner=step_id)
        assert (corner.get("width"), corner.get("height"), corner.get("fill")) == ("30", "30", colour)
        assert (corner.get("x"), corner.get("y")) == (rect.get("x"), rect.get("y"))
        digit = find(process_root, "text", data_number=step_id)
        assert [("".join(d.itertext()), d.get("fill")) for d in digit] == [(number, ON_FILL)]
    assert text_of(process_root, "Fijar principios").get("font-weight") == "700"
    assert text_of(process_root, "/constitution").get("fill") == MUTED


def test_decisions_are_saffron_diamonds_and_are_not_numbered(process_root: ET.Element) -> None:
    (diamond,) = find(process_root, "polygon", data_node="d1")
    assert diamond.get("fill") == SAFFRON
    assert not find(process_root, "rect", data_corner="d1") and not find(process_root, "text", data_number="d1")
    assert text_of(process_root, "¿Quedan ambigüedades?").get("fill") == INK
    numbers = sorted("".join(t.itertext()) for t in find(process_root, "text") if t.get("data-number"))
    assert numbers == ["1", "2", "3", "4", "5", "6"]  # six steps, the decision takes no number


def test_artifacts_are_folded_documents_joined_by_a_dashed_connector(process_root: ET.Element) -> None:
    (doc,) = find(process_root, "path", data_artifact="s1")
    assert (doc.get("fill"), doc.get("stroke")) == (WHITE, LINE[GREEN])
    (fold,) = find(process_root, "path", data_fold="s1")
    assert fold.get("fill") == GREEN
    (link,) = find(process_root, "line", data_edge="artifact:s1")
    assert (link.get("stroke"), link.get("stroke-dasharray")) == (LINE[GREEN], "4 4")
    assert text_of(process_root, "constitution.md").get("fill") == INK
    assert not find(process_root, "path", data_artifact="s6"), "steps without an artifact get no document"
    lane = box(find(process_root, "rect", data_lane="artifact")[0])
    doc_x0, _, doc_x1, _ = artifact_box(process_root, "s1")
    assert lane[0] < doc_x0 and doc_x1 < lane[2]


def test_flow_connectors_are_ink_and_branch_labels_are_uppercase(process_root: ET.Element) -> None:
    flows = {f"{f['from']}>{f['to']}" for f in PROCESS_SPEC["flow"]}
    paths = {p.get("data-edge"): p for p in find(process_root, "path") if p.get("data-edge")}
    assert set(paths) == flows
    for path in paths.values():
        assert (path.get("stroke"), path.get("fill"), path.get("marker-end")) == (INK, "none", "url(#tip-ink)")
    for edge, label in (("d1>s3", "SÍ"), ("d1>s4", "NO")):
        (found,) = find(process_root, "text", data_label=edge)
        assert "".join(found.itertext()) == label and found.get("font-weight") == "700"
    assert not find(process_root, "text", data_label="s1>s2")


def test_every_connector_of_the_sample_map_avoids_every_node(process_root: ET.Element) -> None:
    assert_no_connector_crosses_a_node(process_root)


def test_back_edge_loops_on_the_right_of_its_source_box(process_root: ET.Element) -> None:
    source = node_box(process_root, "s3")
    points = connectors(process_root)["s3>d1"]
    assert points[0][0] == pytest.approx(source[2]) and source[1] < points[0][1] < source[3]
    corridor = points[1][0]
    assert corridor > source[2] and all(p[0] >= source[2] - 1e-6 or p == points[-1] for p in points[1:-1])
    target = node_box(process_root, "d1")
    assert points[-1][1] == pytest.approx((target[1] + target[3]) / 2) and points[-1][0] > target[2]


def test_row_skipping_edge_runs_along_the_free_edge_of_its_source_lane(process_root: ET.Element) -> None:
    lane = box(find(process_root, "rect", data_lane="equipo")[0])
    points = connectors(process_root)["d1>s4"]
    run = points[1][0]
    assert lane[0] < run < node_box(process_root, "d1")[0]
    assert points[0][0] == pytest.approx(node_box(process_root, "d1")[0])  # leaves the left vertex
    assert points[-1][0] < node_box(process_root, "s4")[0] + 3  # enters the left side of s4
    assert points[2][1] == pytest.approx(points[3][1])


def _lattice_spec(count: int = 4) -> dict:
    """Three actor lanes and an artifact lane, boxes and decisions, with every ordered pair of ``count`` steps as a flow.

    Four steps is the densest such map on three lanes plus the artifact lane: with more, five connectors meet
    one side of a step (four fit apart there) or the corridors no longer fit 860 units.
    """
    steps = [
        {"id": "a", "lane": "l1", "title": "Alfa", "artifact": "alfa.md"},
        {"id": "b", "lane": "l2", "title": "¿Beta?", "decision": True},
        {"id": "c", "lane": "l3", "title": "Gamma", "artifact": "gamma.md"},
        {"id": "d", "lane": "l1", "title": "¿Delta?", "decision": True},
        {"id": "e", "lane": "l2", "title": "Épsilon", "artifact": "eps.md"},
        {"id": "f", "lane": "l1", "title": "Zeta"},
        {"id": "g", "lane": "l3", "title": "Eta", "artifact": "eta.md"},
        {"id": "h", "lane": "l2", "title": "Theta"},
    ][:count]
    ids = [s["id"] for s in steps]
    return {"kind": "process_map", "title": "Todas las parejas",
            "lanes": [{"id": "l1", "label": "UNO"}, {"id": "l2", "label": "DOS"}, {"id": "l3", "label": "TRES"}],
            "artifact_lane": {"label": "ARTEFACTO"}, "steps": steps,
            "flow": [{"from": a, "to": b} for a in ids for b in ids if a != b]}


def test_no_connector_crosses_a_node_for_any_pair_of_steps(tmp_path: Path) -> None:
    root = svg_root(tmp_path, _lattice_spec())
    assert len(connectors(root)) == 4 * 3
    assert_no_connector_crosses_a_node(root)
    assert collinear_overlaps(root) == []
    boxes = all_boxes(root)
    for name, points in connectors(root).items():
        source, target = name.split(">")
        sx0, sy0, sx1, sy1 = boxes[source]
        px, py = points[0]
        assert sx0 - 1e-6 <= px <= sx1 + 1e-6 and sy0 - 1e-6 <= py <= sy1 + 1e-6, f"{name} starts off its source"
        tx0, ty0, tx1, ty1 = boxes[target]
        qx, qy = points[-1]
        assert tx0 - 4 <= qx <= tx1 + 4 and ty0 - 4 <= qy <= ty1 + 4, f"{name} ends off its target"


def test_no_connector_crosses_a_node_with_two_lanes_and_no_artifact_lane(tmp_path: Path) -> None:
    spec = _lattice_spec(8)
    spec["steps"], spec["flow"] = spec["steps"][:5], [f for f in spec["flow"] if {f["from"], f["to"]} <= set("abcde")]
    spec["lanes"] = spec["lanes"][:2]
    spec.pop("artifact_lane")
    for step in spec["steps"]:
        step["lane"] = "l1" if step["lane"] == "l1" else "l2"
        step.pop("artifact", None)
    root = svg_root(tmp_path, spec)
    assert not find(root, "rect", data_lane="artifact")
    assert len(connectors(root)) == 5 * 4
    assert_no_connector_crosses_a_node(root)
    assert collinear_overlaps(root) == []


ROUTES_SPEC = {  # verifier repro: skip edges, back edges and labels competing for the same lanes
    "kind": "process_map", "title": "Rutas",
    "lanes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
    "artifact_lane": {"label": "DOC"},
    "steps": [
        {"id": "s1", "lane": "b", "title": "Uno", "artifact": "uno.md"},
        {"id": "d1", "lane": "c", "title": "¿Sigue?", "decision": True},
        {"id": "s3", "lane": "a", "title": "Tres"},
        {"id": "s4", "lane": "b", "title": "Cuatro", "artifact": "cuatro.md"},
        {"id": "s5", "lane": "c", "title": "Cinco"},
        {"id": "s6", "lane": "a", "title": "Seis"},
    ],
    "flow": [
        {"from": "s1", "to": "d1"}, {"from": "d1", "to": "s3", "label": "sí"}, {"from": "d1", "to": "s6", "label": "no"},
        {"from": "s5", "to": "s1", "label": "rehacer"}, {"from": "s4", "to": "d1"}, {"from": "s3", "to": "s5"},
        {"from": "s6", "to": "s4"},
    ],
}
STRESS_SPEC = {  # three back edges and three skip edges leaving the same lanes at the same time
    "kind": "process_map", "title": "Corredores",
    "lanes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}, {"id": "c", "label": "C"}],
    "steps": [
        {"id": "p1", "lane": "c", "title": "Uno"}, {"id": "p2", "lane": "a", "title": "Dos"},
        {"id": "p3", "lane": "c", "title": "Tres"}, {"id": "p4", "lane": "b", "title": "Cuatro"},
        {"id": "p5", "lane": "c", "title": "Cinco"}, {"id": "p6", "lane": "a", "title": "Seis"},
    ],
    "flow": [
        {"from": "p1", "to": "p2"}, {"from": "p2", "to": "p3"}, {"from": "p3", "to": "p4"}, {"from": "p4", "to": "p5"},
        {"from": "p5", "to": "p6"}, {"from": "p5", "to": "p1", "label": "otra vez"}, {"from": "p6", "to": "p2", "label": "no"},
        {"from": "p4", "to": "p1"}, {"from": "p1", "to": "p3", "label": "sí"}, {"from": "p1", "to": "p5"},
        {"from": "p2", "to": "p4"},
    ],
}


def _labelled_lattice() -> dict:
    spec = _lattice_spec()
    spec["flow"] = [{**f, **({"label": "sí"} if (f["from"], f["to"]) in {("a", "b"), ("c", "d"), ("e", "f")} else {})}
                    for f in spec["flow"]]
    return spec


def segments(root: ET.Element) -> dict[str, list[tuple[float, float]]]:
    """Every connector drawn, the dashed artifact ones included, as polylines."""
    found = dict(connectors(root))
    for line in find(root, "line"):
        if (line.get("data-edge") or "").startswith("artifact:"):
            found[line.get("data-edge")] = [(float(line.get("x1")), float(line.get("y1"))),
                                            (float(line.get("x2")), float(line.get("y2")))]
    return found


def label_boxes(root: ET.Element) -> dict[str, tuple[float, float, float, float]]:
    """Each branch label's ink box: the advance width and the glyph extents of the string in Space Grotesk at its size.

    Ascenders, accents and descenders count ("p" reaches about 2.5 units below the baseline).
    """
    import bauhaus_maps

    boxes = {}
    for label in find(root, "text"):
        if not label.get("data-label"):
            continue
        value, size, weight = "".join(label.itertext()), float(label.get("font-size")), int(label.get("font-weight"))
        width = bauhaus_maps.measure(value, size, weight, float(label.get("letter-spacing") or 0))
        _, top, _, bottom = (v * size / 100 for v in bauhaus_maps._face(weight).getbbox(value, anchor="ls"))
        x, y, anchor = float(label.get("x")), float(label.get("y")), label.get("text-anchor")
        left = x if anchor == "start" else x - width if anchor == "end" else x - width / 2
        boxes[label.get("data-label")] = (left, y + top, left + width, y + bottom)
    return boxes


def overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def assert_labels_are_clear(root: ET.Element) -> None:
    labels = label_boxes(root)
    assert labels, "no labels drawn"
    nodes = all_boxes(root)
    lines = segments(root)
    for name, rect in labels.items():
        for other, points in lines.items():
            assert not crosses_box(points, rect), f"label {name} is crossed by connector {other}"
        for node_id, box_ in nodes.items():
            diamond = {e.get("data-node"): e for e in find(root, "polygon")}.get(node_id)
            if diamond is not None:  # a diamond's corners are empty: measure against its outline
                assert not any(rect[0] < x < rect[2] and rect[1] < y < rect[3] for x, y in outline_of(diamond)), \
                    f"label {name} overlaps node {node_id}"
            else:
                assert not overlap(rect, box_), f"label {name} overlaps node {node_id}"
        for other, box_ in labels.items():
            assert other == name or not overlap(rect, box_), f"labels {name} and {other} overlap"


def collinear_overlaps(root: ET.Element) -> list[str]:
    """Pairs of distinct connectors that run along the same line over a stretch longer than a stroke."""
    flat = [(name, a, b) for name, points in segments(root).items() for a, b in zip(points, points[1:])]
    clashes = []
    for i, (name, a, b) in enumerate(flat):
        for other, c, d in flat[i + 1:]:
            if name == other:
                continue
            for axis in (0, 1):  # 0: both vertical (same x), 1: both horizontal (same y)
                if abs(a[axis] - b[axis]) < 1e-6 and abs(c[axis] - d[axis]) < 1e-6 and abs(a[axis] - c[axis]) < 0.75:
                    lo, hi = max(min(a[1 - axis], b[1 - axis]), min(c[1 - axis], d[1 - axis])), min(
                        max(a[1 - axis], b[1 - axis]), max(c[1 - axis], d[1 - axis]))
                    if hi - lo > 0.75:
                        clashes.append(f"{name} / {other} at {'x' if axis == 0 else 'y'}={a[axis]:.1f}")
    return clashes


@pytest.mark.parametrize("lane_id", ["artifact", "decision"])
def test_reserved_lane_ids_are_rejected_naming_the_field(tmp_path: Path, lane_id: str) -> None:
    spec = copy.deepcopy(PROCESS_SPEC)
    spec["lanes"][0]["id"] = lane_id
    for step in spec["steps"]:
        step["lane"] = lane_id if step["lane"] == "equipo" else step["lane"]
    result, out = render(tmp_path, spec, "--png", tmp_path / "fig.png")
    assert result.returncode == 2
    assert result.stderr == (f"bauhaus_maps: 'lanes[0].id' is {lane_id!r}, which names the "
                             f"{'artifact lane' if lane_id == 'artifact' else 'decision legend entry'}; use another id\n")
    assert not out.exists() and not (tmp_path / "fig.png").exists()


def test_an_actor_lane_never_shares_the_artifact_column_in_the_reproduction(tmp_path: Path) -> None:
    spec = {"kind": "process_map", "title": "T", "lanes": [{"id": "artifact", "label": "A"}, {"id": "b", "label": "B"}],
            "artifact_lane": {"label": "DOC"},
            "steps": [{"id": "s1", "lane": "artifact", "title": "Uno", "artifact": "x.md"}, {"id": "s2", "lane": "b", "title": "Dos"}],
            "flow": [{"from": "s1", "to": "s2"}]}
    result, out = render(tmp_path, spec)
    assert result.returncode == 2 and not out.exists()


@pytest.mark.parametrize("spec", [PROCESS_SPEC, ROUTES_SPEC, STRESS_SPEC, _labelled_lattice()], ids=["spec-kit", "routes", "stress", "lattice"])
def test_no_label_touches_a_connector_a_node_or_another_label(tmp_path: Path, spec: dict) -> None:
    assert_labels_are_clear(svg_root(tmp_path, spec))


def test_a_label_with_no_free_spot_fails_naming_the_flow_field(tmp_path: Path) -> None:
    spec = copy.deepcopy(PROCESS_SPEC)
    spec["flow"][0]["label"] = "una etiqueta imposiblemente larga para el hueco de la ruta " * 3
    result, out = render(tmp_path, spec)
    assert result.returncode == 2 and not out.exists()
    assert result.stderr.startswith("bauhaus_maps: 'flow[0].label' has no free spot beside its connector"), result.stderr


@pytest.mark.parametrize("spec", [PROCESS_SPEC, ROUTES_SPEC, STRESS_SPEC], ids=["spec-kit", "routes", "stress"])
def test_no_two_connectors_share_a_collinear_stretch(tmp_path: Path, spec: dict) -> None:
    root = svg_root(tmp_path, spec)
    assert collinear_overlaps(root) == []
    assert_no_connector_crosses_a_node(root)


def test_concurrent_corridors_stay_inside_the_lane_margin(tmp_path: Path) -> None:
    root = svg_root(tmp_path, STRESS_SPEC)
    lane = box(find(root, "rect", data_lane="c")[0])
    for name in ("p5>p1", "p4>p1"):
        corridor = connectors(root)[name][1][0]
        assert lane[0] < corridor < lane[2]
        assert corridor > node_box(root, "p1")[2], name  # right of the nodes of the lane
    assert connectors(root)["p5>p1"][1][0] != connectors(root)["p4>p1"][1][0]


def test_more_connectors_than_a_step_side_can_keep_apart_fail_naming_the_step(tmp_path: Path) -> None:
    result, out = render(tmp_path, _lattice_spec(6))
    assert result.returncode == 2 and not out.exists()
    assert result.stderr == ("bauhaus_maps: step 'a' has 5 connectors on its right side and only 4 fit apart; "
                             "split the map or route some flows through another step\n")


def test_corridors_that_cannot_fit_fail_with_the_width_message_instead_of_overlapping(tmp_path: Path) -> None:
    result, out = render(tmp_path, _lattice_spec(8))
    assert result.returncode == 2 and not out.exists()
    assert re.fullmatch(r"bauhaus_maps: layout is \d+ units wide, over the 860-unit limit; the figure is never shrunk, "
                        r"so split the map or shorten names and details\n", result.stderr), result.stderr


def test_the_legend_names_each_lane_and_the_decision(process_root: ET.Element) -> None:
    for key, colour, label in (("equipo", RED, "EQUIPO"), ("ia", BLUE, "ASISTENTE"), ("artifact", GREEN, "ARTEFACTO")):
        (line,) = find(process_root, "line", data_legend=key)
        assert (line.get("stroke"), line.get("stroke-width")) == (LINE[colour], "4")
        legend = [t for t in texts(process_root) if "".join(t.itertext()) == label and t.get("font-weight") == "700"]
        assert legend and legend[-1].get("fill") == SHADE[colour]
    (marker,) = find(process_root, "polygon", data_legend="decision")
    assert marker.get("fill") == SAFFRON
    assert text_of(process_root, "DECISIÓN").get("fill") == INK
    foot = max(float(e.get("y1")) for e in find(process_root, "line", data_legend="equipo"))
    assert foot > max(b[3] for b in all_boxes(process_root).values())


def test_a_map_without_decisions_has_no_decision_legend_entry(tmp_path: Path) -> None:
    spec = copy.deepcopy(PROCESS_SPEC)
    spec["steps"] = [s for s in spec["steps"] if s["id"] != "d1"]
    spec["flow"] = [{"from": "s1", "to": "s2"}, {"from": "s2", "to": "s3"}, {"from": "s3", "to": "s4"},
                    {"from": "s4", "to": "s5"}, {"from": "s5", "to": "s6"}]
    root = svg_root(tmp_path, spec)
    assert not find(root, "polygon", data_legend="decision")


def test_lane_colours_default_to_red_blue_green_ink_and_can_be_chosen(tmp_path: Path) -> None:
    spec = _lattice_spec()
    root = svg_root(tmp_path, spec)
    heads = {lane: find(root, "rect", data_lane_header=lane)[0].get("fill") for lane in ("l1", "l2", "l3", "artifact")}
    assert heads == {"l1": RED, "l2": BLUE, "l3": GREEN, "artifact": INK}
    spec["lanes"][0]["color"] = "green"
    spec["lanes"][2]["color"] = "red"
    swapped = svg_root(tmp_path, spec)
    assert find(swapped, "rect", data_lane_header="l1")[0].get("fill") == GREEN


def test_a_process_map_wider_than_860_units_fails_instead_of_shrinking(tmp_path: Path) -> None:
    spec = copy.deepcopy(PROCESS_SPEC)
    spec["lanes"].append({"id": "extra", "label": "TERCER ACTOR"})
    spec["steps"][0]["title"] = "Un título extraordinariamente largo para forzar el ancho"
    result, out = render(tmp_path, spec)
    assert result.returncode == 2
    assert re.fullmatch(
        r"bauhaus_maps: layout is \d+ units wide, over the 860-unit limit; the figure is never shrunk, "
        r"so split the map or shorten names and details\n", result.stderr), result.stderr
    assert not out.exists()


def _lane(lane_id: str, label: str, **extra: str) -> dict:
    return {"id": lane_id, "label": label, **extra}


PROCESS_CASES = [
    (_without(PROCESS_SPEC, "title"), "'title' is required"),
    (_without(PROCESS_SPEC, "lanes"), "'lanes' is required"),
    (_with(PROCESS_SPEC, [_lane("a", "A")], "lanes"), "'lanes' needs 2 or 3 actor lanes, not 1"),
    (_with(PROCESS_SPEC, [_lane(c, c.upper()) for c in "abcd"], "lanes"), "'lanes' needs 2 or 3 actor lanes, not 4"),
    (_without(PROCESS_SPEC, "lanes", 0, "label"), "'lanes[0].label' is required"),
    (_without(PROCESS_SPEC, "lanes", 1, "id"), "'lanes[1].id' is required"),
    (_with(PROCESS_SPEC, "equipo", "lanes", 1, "id"), "'lanes[1].id' repeats id 'equipo'"),
    (_with(PROCESS_SPEC, "saffron", "lanes", 0, "color"),
     "'lanes[0].color' is 'saffron'; use one of ['blue', 'green', 'ink', 'red']"),
    (_with(_with(PROCESS_SPEC, "red", "lanes", 0, "color"), "red", "lanes", 1, "color"),
     "'lanes[1].color' repeats colour 'red'"),
    (_with(PROCESS_SPEC, {"label": ""}, "artifact_lane"), "'artifact_lane.label' is required"),
    (_with(_with(PROCESS_SPEC, "red", "lanes", 0, "color"), {"label": "ARTEFACTO", "color": "red"}, "artifact_lane"),
     "'artifact_lane.color' repeats colour 'red'"),
    (_without(PROCESS_SPEC, "steps"), "'steps' is required"),
    (_with(PROCESS_SPEC, PROCESS_SPEC["steps"][:1], "steps"), "'steps' needs at least 2 steps"),
    (_without(PROCESS_SPEC, "steps", 0, "title"), "'steps[0].title' is required"),
    (_without(PROCESS_SPEC, "steps", 1, "id"), "'steps[1].id' is required"),
    (_without(PROCESS_SPEC, "steps", 1, "lane"), "'steps[1].lane' is required"),
    (_with(PROCESS_SPEC, "nope", "steps", 1, "lane"), "'steps[1].lane' is 'nope'; use one of ['equipo', 'ia']"),
    (_with(PROCESS_SPEC, "s1", "steps", 1, "id"), "'steps[1].id' repeats id 's1'"),
    (_with(PROCESS_SPEC, "sí", "steps", 2, "decision"), "'steps[2].decision' must be true or false"),
    (_with(PROCESS_SPEC, "x.md", "steps", 2, "artifact"), "'steps[2].artifact' is not allowed on a decision"),
    (_without(PROCESS_SPEC, "artifact_lane"), "'steps[0].artifact' needs an 'artifact_lane'"),
    (_without(PROCESS_SPEC, "flow"), "'flow' is required"),
    (_with(PROCESS_SPEC, "zzz", "flow", 0, "to"), "'flow[0].to' refers to unknown id 'zzz'"),
    (_with(PROCESS_SPEC, "zzz", "flow", 2, "from"), "'flow[2].from' refers to unknown id 'zzz'"),
    (_without(PROCESS_SPEC, "flow", 0, "to"), "'flow[0].to' is required"),
    (_with(PROCESS_SPEC, "s1", "flow", 0, "to"), "'flow[0]' links 's1' to itself"),
]


@pytest.mark.parametrize(("spec", "message"), PROCESS_CASES, ids=[m for _, m in PROCESS_CASES])
def test_malformed_process_specs_fail_naming_the_field_and_write_nothing(tmp_path: Path, spec: dict, message: str) -> None:
    result, out = render(tmp_path, spec, "--png", tmp_path / "fig.png")
    assert result.returncode == 2
    assert result.stderr == f"bauhaus_maps: {message}\n"
    assert result.stdout == ""
    assert not out.exists() and not (tmp_path / "fig.png").exists()


def test_a_repeated_flow_pair_is_rejected(tmp_path: Path) -> None:
    spec = copy.deepcopy(PROCESS_SPEC)
    spec["flow"].append({"from": "s1", "to": "s2", "label": "otra vez"})
    result, out = render(tmp_path, spec)
    assert (result.returncode, result.stderr) == (2, "bauhaus_maps: 'flow[7]' repeats the flow 's1' -> 's2'\n")
    assert not out.exists()


def test_an_unquoted_yaml_no_is_reported_with_the_quoting_hint(tmp_path: Path) -> None:
    out = tmp_path / "fig.svg"
    spec = tmp_path / "spec.yml"
    # YAML 1.1 reads a bare "no" as false, so a branch label written "label: no" arrives as a boolean.
    text = yaml.safe_dump(PROCESS_SPEC, allow_unicode=True, sort_keys=False).replace("label: 'no'", "label: no")
    assert "label: no\n" in text
    spec.write_text(text, encoding="utf-8")
    result = run_cli("render", spec, "--out", out)
    assert result.returncode == 2
    assert result.stderr == ("bauhaus_maps: 'flow[4].label' must be text; YAML reads an unquoted yes/no as true/false, "
                             "so put the word in quotes\n")
    assert not out.exists()


@needs_rsvg
def test_process_map_png_is_written_at_twice_the_svg_size(tmp_path: Path) -> None:
    png = tmp_path / "proceso.png"
    result, out = render(tmp_path, PROCESS_SPEC, "--png", png)
    assert result.returncode == 0, result.stderr
    data = png.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    root = ET.fromstring(out.read_text(encoding="utf-8"))
    assert (int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")) == (
        round(float(root.get("width")) * 2), round(float(root.get("height")) * 2))


# --------------------------------------------------------------------------
# existing editorial layouts stay untouched
# --------------------------------------------------------------------------

EDITORIAL_ACTOR = {
    "kind": "actor_map", "title": "Sistema de prueba", "scope": "Alcance MVP",
    "steps": [["Asignación", "y aprobación"], ["Seguimiento", ""], ["Cierre", "final"]],
    "note": "Cada evidencia queda ligada a una actividad.",
    "top": [{"name": "Estudiante", "category": "principal", "lines": ["registra"], "link": "both"},
            {"name": "Tutor", "category": "secundario", "lines": ["revisa"]},
            {"name": "Coordinador", "category": "responsable", "lines": ["asigna"]}],
    "bottom": [{"name": "Dirección", "category": "externo", "lines": ["consulta"], "link": "from_system"},
               {"name": "Tutor externo", "category": "secundario", "lines": ["valida"]},
               {"name": "Entidad", "category": "externo", "lines": ["acepta"]}],
    "designates": {"top": True, "bottom": True},
    "services": [{"name": "SIAAF", "lines": ["datos"], "out_of_scope": True},
                 {"name": "Correo", "lines": ["alertas"], "link": "from_system"}],
}
EDITORIAL_CONCEPT = {
    "kind": "concept_map",
    "center": {"title": "Spec-Driven Development", "subtitle": "flujo de GitHub Spec Kit"},
    "branches": [{"name": "Constitution", "link": "fija", "items": ["principios"]},
                 {"name": "Specify", "link": "describe", "items": ["qué y porqué", "historias"]},
                 {"name": "Clarify", "link": "resuelve", "items": ["ambigüedades"]},
                 {"name": "Plan", "link": "decide", "items": ["stack", "datos"]}],
}


def test_editorial_actor_and_concept_maps_render_byte_for_byte_as_before() -> None:
    golden = {
        "actor_map": ("d3897e202f64b5d2e327771ee6d0d08c3cbcb858b088d3434308285d8fdf4a2a", EDITORIAL_ACTOR),
        "concept_map": ("ea72f9a71b62291652b36d4d627ebe073335eee5b702d7c549f2213e1122ccf5", EDITORIAL_CONCEPT),
    }
    for kind, (digest, spec) in golden.items():
        svg = editorial_svg.render(spec)
        assert hashlib.sha256(svg.encode("utf-8")).hexdigest() == digest, kind
        assert editorial_svg.check(svg) == []


# --------------------------------------------------------------------------
# hardening: atomic output, unreadable specs, wrong types, quoting, tool failures, colours
# --------------------------------------------------------------------------

def leftovers(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


@needs_rsvg
@pytest.mark.parametrize("make_target", ["svg-is-a-directory", "svg-parent-is-a-file"])
def test_a_failed_svg_write_leaves_no_png_and_no_temporary_file(tmp_path: Path, make_target: str) -> None:
    spec, png_dir = write_spec(tmp_path, PROCESS_SPEC), tmp_path / "png"
    png_dir.mkdir()
    if make_target == "svg-is-a-directory":
        out = tmp_path / "taken"
        out.mkdir()
    else:
        (tmp_path / "plain").write_text("not a folder", encoding="utf-8")
        out = tmp_path / "plain" / "fig.svg"
    result = run_cli("render", spec, "--out", out, "--png", png_dir / "fig.png")
    assert result.returncode == 2 and result.stderr.startswith("bauhaus_maps: ") and "Traceback" not in result.stderr
    assert leftovers(png_dir) == [], "no PNG, no temporary file"
    assert leftovers(tmp_path / "taken") == [] if make_target == "svg-is-a-directory" else True


@needs_rsvg
def test_a_failed_png_write_leaves_no_svg(tmp_path: Path) -> None:
    (tmp_path / "plain").write_text("not a folder", encoding="utf-8")
    out_dir = tmp_path / "svg"
    out_dir.mkdir()
    result = run_cli("render", write_spec(tmp_path, PROCESS_SPEC), "--out", out_dir / "fig.svg", "--png", tmp_path / "plain" / "fig.png")
    assert result.returncode == 2 and "Traceback" not in result.stderr
    assert leftovers(out_dir) == []


def test_a_failing_rsvg_convert_leaves_neither_file(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    fake_tool(bin_dir, "rsvg-convert", "cat > /dev/null\necho boom >&2\nexit 1")
    out_dir = tmp_path / "dest"
    out_dir.mkdir()
    result = run_cli("render", write_spec(tmp_path, PROCESS_SPEC), "--out", out_dir / "fig.svg", "--png", out_dir / "fig.png",
                     env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)})
    assert (result.returncode, result.stderr) == (2, "bauhaus_maps: rsvg-convert failed: boom\n")
    assert leftovers(out_dir) == []


@needs_rsvg
def test_a_good_render_leaves_exactly_the_two_requested_files(tmp_path: Path) -> None:
    out_dir = tmp_path / "dest"
    out_dir.mkdir()
    result = run_cli("render", write_spec(tmp_path, PROCESS_SPEC), "--out", out_dir / "fig.svg", "--png", out_dir / "fig.png")
    assert result.returncode == 0, result.stderr
    assert leftovers(out_dir) == ["fig.png", "fig.svg"]


@pytest.mark.parametrize("payload", [b"\xff\xfe\x00 kind: \x80\x81", b"kind: \xc3("], ids=["binary", "bad-utf8"])
def test_an_undecodable_spec_is_a_clean_error_without_a_traceback(tmp_path: Path, payload: bytes) -> None:
    spec = tmp_path / "spec.yml"
    spec.write_bytes(payload)
    out = tmp_path / "fig.svg"
    result = run_cli("render", spec, "--out", out)
    assert result.returncode == 2 and "Traceback" not in result.stderr
    assert result.stderr.startswith("bauhaus_maps: cannot read the spec: ") and result.stderr.endswith("\n")
    assert not out.exists()


def test_a_spec_that_is_a_folder_is_a_clean_error(tmp_path: Path) -> None:
    out = tmp_path / "fig.svg"
    result = run_cli("render", tmp_path, "--out", out)
    assert result.returncode == 2 and "Traceback" not in result.stderr and not out.exists()


WRONG_TYPES = [
    ({"kind": ["concept_map"]}, "'kind' must be text; use one of ['concept_map', 'process_map']"),
    ({"kind": {"a": 1}}, "'kind' must be text; use one of ['concept_map', 'process_map']"),
    (("concept", ["concepts", 0, "family"], ["que"]), "'concepts[0].family' must be text"),
    (("concept", ["families", "que", "color"], ["blue"]), "'families.que.color' must be text"),
    (("concept", ["families", "que", "color"], {"a": 1}), "'families.que.color' must be text"),
    (("concept", ["links", 0, "from"], ["sdd"]), "'links[0].from' must be text"),
    (("process", ["lanes", 0, "color"], ["red"]), "'lanes[0].color' must be text"),
    (("process", ["steps", 1, "lane"], ["ia"]), "'steps[1].lane' must be text"),
    (("process", ["flow", 0, "to"], {"x": 1}), "'flow[0].to' must be text"),
]


@pytest.mark.parametrize(("case", "message"), WRONG_TYPES, ids=[m for _, m in WRONG_TYPES])
def test_a_list_or_mapping_where_text_is_expected_names_the_field(tmp_path: Path, case: object, message: str) -> None:
    if isinstance(case, dict):
        spec = case
    else:
        which, path, value = case
        spec = _with(CONCEPT_SPEC if which == "concept" else PROCESS_SPEC, value, *path)
    result, out = render(tmp_path, spec)
    assert (result.returncode, result.stderr) == (2, f"bauhaus_maps: {message}\n")
    assert not out.exists()


QUOTED = 'a"b&c<d'


@needs_dot
def test_quotes_ampersands_and_brackets_in_ids_and_names_keep_the_concept_svg_well_formed(tmp_path: Path) -> None:
    spec = {"kind": "concept_map", "title": f"Título {QUOTED}", "core": {"id": f"core{QUOTED}", "name": f"Núcleo {QUOTED}", "subtitle": QUOTED},
            "families": {f"fam{QUOTED}": {"label": f"F{QUOTED}", "color": "blue", "meaning": QUOTED}},
            "concepts": [{"id": f"x{QUOTED}", "name": f"Uno {QUOTED}", "detail": QUOTED, "family": f"fam{QUOTED}", "level": "key"},
                         {"id": f"y{QUOTED}", "name": "Dos", "family": f"fam{QUOTED}"}],
            "links": [{"from": f"core{QUOTED}", "to": f"x{QUOTED}", "label": f"rel {QUOTED}"},
                      {"from": f"x{QUOTED}", "to": f"y{QUOTED}", "label": "otro", "cross": True}]}
    root = svg_root(tmp_path, spec)
    assert len(find(root, "rect", data_node=f"x{QUOTED}")) == 1
    assert len(find(root, "rect", data_node=f"core{QUOTED}")) == 1
    assert len(find(root, "rect", data_corner=f"y{QUOTED}")) == 1
    assert len(find(root, "path", data_link=f"core{QUOTED}>x{QUOTED}")) == 1
    assert len(find(root, "text", data_label=f"x{QUOTED}>y{QUOTED}")) == 1
    assert len(find(root, "line", data_legend=f"fam{QUOTED}")) == 1
    assert "".join(text_of(root, f"rel {QUOTED}").itertext()) == f"rel {QUOTED}"


def test_quotes_ampersands_and_brackets_in_ids_and_names_keep_the_process_svg_well_formed(tmp_path: Path) -> None:
    lane_a, lane_b, step_a, step_d = f"l1{QUOTED}", f"l2{QUOTED}", f"s{QUOTED}", f"d{QUOTED}"
    spec = {"kind": "process_map", "title": QUOTED, "lanes": [{"id": lane_a, "label": QUOTED}, {"id": lane_b, "label": "B"}],
            "artifact_lane": {"label": "DOC"},
            "steps": [{"id": step_a, "lane": lane_a, "title": QUOTED, "detail": QUOTED, "artifact": QUOTED},
                      {"id": step_d, "lane": lane_b, "title": "¿?", "decision": True}],
            "flow": [{"from": step_a, "to": step_d, "label": QUOTED}]}
    root = svg_root(tmp_path, spec)
    for attribute, element in (("data_node", "rect"), ("data_corner", "rect"), ("data_lane", "rect"), ("data_lane_header", "rect")):
        assert find(root, element, **{attribute: step_a if "lane" not in attribute else lane_a}), attribute
    assert find(root, "polygon", data_node=step_d)
    assert find(root, "path", data_artifact=step_a) and find(root, "path", data_fold=step_a)
    assert find(root, "line", data_edge=f"artifact:{step_a}")
    assert find(root, "path", data_edge=f"{step_a}>{step_d}")
    assert find(root, "text", data_label=f"{step_a}>{step_d}")
    assert find(root, "text", data_number=step_a) and find(root, "line", data_legend=lane_a)


def test_dot_that_never_finishes_fails_naming_the_tool_and_writes_nothing(tmp_path: Path, monkeypatch, capsys) -> None:
    import bauhaus_maps

    fake_tool(tmp_path / "bin", "dot", "exec sleep 30")
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:/usr/bin:/bin")
    monkeypatch.setattr(bauhaus_maps, "TOOL_TIMEOUT", 0.5)
    out = tmp_path / "fig.svg"
    assert bauhaus_maps.main(["render", str(write_spec(tmp_path, CONCEPT_SPEC)), "--out", str(out)]) == 2
    assert capsys.readouterr().err == "bauhaus_maps: Graphviz 'dot' did not finish within 0.5 s; simplify the map\n"
    assert not out.exists()


@needs_rsvg
def test_rsvg_convert_that_never_finishes_fails_naming_the_tool_and_writes_nothing(tmp_path: Path, monkeypatch, capsys) -> None:
    import bauhaus_maps

    fake_tool(tmp_path / "bin", "rsvg-convert", "exec sleep 30")
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:/usr/bin:/bin")
    monkeypatch.setattr(bauhaus_maps, "TOOL_TIMEOUT", 0.5)
    out, png = tmp_path / "fig.svg", tmp_path / "fig.png"
    assert bauhaus_maps.main(["render", str(write_spec(tmp_path, PROCESS_SPEC)), "--out", str(out), "--png", str(png)]) == 2
    assert capsys.readouterr().err == "bauhaus_maps: rsvg-convert did not finish within 0.5 s\n"
    assert not out.exists() and not png.exists()


@pytest.mark.parametrize(("tool", "spec", "extra"), [("dot", CONCEPT_SPEC, []), ("rsvg-convert", PROCESS_SPEC, ["--png"])])
def test_a_tool_that_cannot_be_executed_fails_naming_the_tool(tmp_path: Path, tool: str, spec: dict, extra: list) -> None:
    fake_tool(tmp_path / "bin", tool, "exit 0")
    (tmp_path / "bin" / tool).write_text("#!/nonexistent/interpreter\n", encoding="utf-8")
    out = tmp_path / "fig.svg"
    args = ["--png", tmp_path / "fig.png"] if extra else []
    result = run_cli("render", write_spec(tmp_path, spec), "--out", out, *args, env={"PATH": str(tmp_path / "bin")})
    assert result.returncode == 2 and "Traceback" not in result.stderr
    name = "Graphviz 'dot'" if tool == "dot" else "rsvg-convert"
    assert result.stderr.startswith(f"bauhaus_maps: {name} could not be run: ")
    assert not out.exists() and not (tmp_path / "fig.png").exists()


def lane_fills(root: ET.Element) -> dict[str, str]:
    return {e.get("data-lane-header"): e.get("fill") for e in find(root, "rect") if e.get("data-lane-header")}


def test_lanes_without_a_colour_avoid_the_colours_other_lanes_chose(tmp_path: Path) -> None:
    spec = copy.deepcopy(PROCESS_SPEC)
    spec["lanes"] = [{"id": "a", "label": "A"}, {"id": "b", "label": "B", "color": "red"}, {"id": "c", "label": "C"}]
    spec["steps"] = [{"id": "s1", "lane": "a", "title": "Uno"}, {"id": "s2", "lane": "b", "title": "Dos", "artifact": "x.md"},
                     {"id": "s3", "lane": "c", "title": "Tres"}]
    spec["flow"] = [{"from": "s1", "to": "s2"}, {"from": "s2", "to": "s3"}]
    fills = lane_fills(svg_root(tmp_path, spec))
    assert fills == {"a": BLUE, "b": RED, "c": GREEN, "artifact": INK}
    assert len(set(fills.values())) == 4


def test_an_explicit_colour_on_a_late_lane_does_not_collide_with_an_earlier_default(tmp_path: Path) -> None:
    spec = copy.deepcopy(PROCESS_SPEC)
    spec["lanes"][1]["color"] = "red"
    fills = lane_fills(svg_root(tmp_path, spec))
    assert fills["ia"] == RED and fills["equipo"] != RED
    assert len(set(fills.values())) == len(fills)


def test_the_artifact_lane_takes_a_colour_nobody_chose(tmp_path: Path) -> None:
    spec = copy.deepcopy(PROCESS_SPEC)
    spec["lanes"][0]["color"] = "green"
    spec["lanes"][1]["color"] = "ink"
    fills = lane_fills(svg_root(tmp_path, spec))
    assert fills == {"equipo": GREEN, "ia": INK, "artifact": RED}


# --------------------------------------------------------------------------
# #77 · follow-ups from the Engram example maps
# --------------------------------------------------------------------------

ENGRAM_CONCEPT_SPEC = {  # the Engram concept map the user marked ("mia esas lineas tan pegadas")
    "kind": "concept_map",
    "title": "Engram, la memoria persistente de los agentes",
    "core": {"id": "engram", "name": "Engram", "subtitle": "memoria persistente de agentes"},
    "families": {
        "guarda": {"label": "GUARDA", "color": "blue", "meaning": "lo que se registra"},
        "organiza": {"label": "ORDENA", "color": "green", "meaning": "proyecto y tema"},
        "usa": {"label": "USO", "color": "red", "meaning": "herramientas"},
    },
    "concepts": [
        {"id": "obs", "name": "Observación", "detail": "qué, por qué, dónde", "family": "guarda", "level": "key"},
        {"id": "proyecto", "name": "Proyecto", "detail": "uno por repo", "family": "organiza", "level": "key"},
        {"id": "tools", "name": "Herramientas", "detail": "del agente", "family": "usa", "level": "key"},
        {"id": "resumen", "name": "Resumen", "detail": "al cerrar", "family": "guarda"},
        {"id": "topic", "name": "topic_key", "detail": "sin duplicar", "family": "organiza"},
        {"id": "save", "name": "mem_save", "detail": "al decidir", "family": "usa"},
        {"id": "search", "name": "mem_search", "detail": "por palabras", "family": "usa"},
    ],
    "links": [
        {"from": "engram", "to": "obs", "label": "almacena"},
        {"from": "engram", "to": "proyecto", "label": "se ordena por"},
        {"from": "engram", "to": "tools", "label": "se usa con"},
        {"from": "obs", "to": "resumen", "label": "se condensa en"},
        {"from": "proyecto", "to": "topic", "label": "agrupa temas con"},
        {"from": "tools", "to": "save", "label": "escribe con"},
        {"from": "tools", "to": "search", "label": "recupera con"},
        {"from": "save", "to": "obs", "label": "crea o revisa", "cross": True},
        {"from": "topic", "to": "obs", "label": "identifica la", "cross": True},
    ],
}

ENGRAM_PROCESS_SPEC = {  # the Engram process map, with the "sí" on d2 -> s6 that made it fail
    "kind": "process_map",
    "title": "Ciclo de memoria en una sesión del agente",
    "lanes": [{"id": "agente", "label": "AGENTE", "short": "AGENTE"}, {"id": "engram", "label": "ENGRAM", "short": "ENGRAM"}],
    "artifact_lane": {"label": "REGISTRO"},
    "steps": [
        {"id": "s1", "lane": "agente", "title": "Abrir sesión", "detail": "mem_context"},
        {"id": "s2", "lane": "engram", "title": "Dar contexto", "detail": "sesiones previas", "artifact": "contexto"},
        {"id": "s3", "lane": "agente", "title": "Trabajar", "detail": "decidir y corregir"},
        {"id": "d1", "lane": "agente", "title": "¿Hay algo útil?", "decision": True},
        {"id": "s4", "lane": "engram", "title": "Guardar", "detail": "upsert por topic_key", "artifact": "observación"},
        {"id": "d2", "lane": "agente", "title": "¿Fin de sesión?", "decision": True},
        {"id": "s6", "lane": "agente", "title": "Resumir", "detail": "mem_session_summary"},
        {"id": "s7", "lane": "engram", "title": "Archivar", "detail": "para la próxima", "artifact": "resumen"},
    ],
    "flow": [
        {"from": "s1", "to": "s2"}, {"from": "s2", "to": "s3"}, {"from": "s3", "to": "d1"},
        {"from": "d1", "to": "s4", "label": "sí"}, {"from": "d1", "to": "d2", "label": "no"}, {"from": "s4", "to": "d2"},
        {"from": "d2", "to": "s3", "label": "no"}, {"from": "d2", "to": "s6", "label": "sí"}, {"from": "s6", "to": "s7"},
    ],
}


def long_legend_spec() -> dict:
    """The Engram concept map with the original legend, whose texts alone are wider than 860 units."""
    spec = copy.deepcopy(ENGRAM_CONCEPT_SPEC)
    for key, label, meaning in (("guarda", "QUÉ GUARDA", "observaciones y resúmenes"),
                                ("organiza", "CÓMO ORGANIZA", "proyecto, alcance y tema"),
                                ("usa", "CÓMO SE USA", "herramientas mem_*")):
        spec["families"][key].update(label=label, meaning=meaning)
    return spec


@needs_dot
def test_a_legend_wider_than_860_units_is_named_as_the_culprit(tmp_path: Path) -> None:
    result, out = render(tmp_path, long_legend_spec(), "--png", tmp_path / "fig.png")
    assert result.returncode == 2
    assert re.fullmatch(
        r"bauhaus_maps: the legend is \d+ units wide, over the 860-unit limit; the figure is never shrunk, so shorten "
        r"its widest entry 'CÓMO ORGANIZA: proyecto, alcance y tema' or the other legend entries\n", result.stderr), result.stderr
    assert not out.exists() and not (tmp_path / "fig.png").exists()


@needs_dot
def test_a_legend_that_fits_leaves_the_drawing_message_alone(tmp_path: Path) -> None:
    spec = long_legend_spec()
    for item in spec["families"].values():
        item.pop("meaning")
    spec["concepts"] = [
        {"id": f"c{i}", "name": f"Concepto largo número {i}", "detail": "con un detalle bastante extenso", "family": "guarda"}
        for i in range(8)]
    spec["links"] = [{"from": "engram", "to": f"c{i}", "label": "incluye"} for i in range(8)]
    result, out = render(tmp_path, spec)
    assert result.returncode == 2 and not out.exists()
    assert re.fullmatch(r"bauhaus_maps: layout is \d+ units wide, over the 860-unit limit; the figure is never shrunk, "
                        r"so split the map or shorten names and details\n", result.stderr), result.stderr


def test_lane_names_wider_than_860_units_in_the_legend_name_the_widest_one(tmp_path: Path) -> None:
    spec = copy.deepcopy(PROCESS_SPEC)
    spec["lanes"][0]["short"] = "UN NOMBRE DE ACTOR EXTRAORDINARIAMENTE LARGO PARA LA LEYENDA"
    spec["lanes"][1]["short"] = "OTRO NOMBRE DE ACTOR TAMBIÉN MUY LARGO PARA LA LEYENDA"
    result, out = render(tmp_path, spec)
    assert result.returncode == 2 and not out.exists()
    assert re.fullmatch(
        r"bauhaus_maps: the legend is \d+ units wide, over the 860-unit limit; the figure is never shrunk, so shorten "
        r"its widest entry 'UN NOMBRE DE ACTOR EXTRAORDINARIAMENTE LARGO PARA LA LEYENDA' or the other legend entries\n",
        result.stderr), result.stderr


@needs_dot
def test_a_decision_branch_straight_down_keeps_its_label_beside_its_own_line(tmp_path: Path) -> None:
    root = svg_root(tmp_path, ENGRAM_PROCESS_SPEC)
    diamond, below = node_box(root, "d2"), node_box(root, "s6")
    line_x = connectors(root)["d2>s6"][0][0]
    label = label_boxes(root)["d2>s6"]
    assert text_of(root, "SÍ") is not None
    assert label[1] >= diamond[3] and label[3] <= below[1], "the label sits between the diamond and the step below"
    # beside the line, yet 8 units from the arrowhead wing, so a few units further out than the usual 7
    assert 0 < label[0] - line_x <= 24 or 0 < line_x - label[2] <= 24, "the label sits beside its connector"
    assert_labels_are_clear(root)
    assert_no_connector_crosses_a_node(root)


CLEARANCE = 10  # SVG units a concept-map link keeps from every node it does not connect and from other links' arrowheads
ARROW_LENGTH, ARROW_HALF_WIDTH = 11.5, 5.8  # the marker: 8 of its 10 units long, 4 of them to each side, at 1.6 x 9 / 10


def sampled_path(d: str, per_curve: int = 60) -> list[tuple[float, float]]:
    """Points along a drawn link: the start plus every cubic béziér ('M x,y C c1 c2 end ...') sampled finely."""
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", d)]
    points = list(zip(numbers[0::2], numbers[1::2]))
    assert d.startswith("M") and (len(points) - 1) % 3 == 0, d
    samples = [points[0]]
    for i in range(0, len(points) - 1, 3):
        (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points[i:i + 4]
        for step in range(1, per_curve + 1):
            t = step / per_curve
            a, b, c, e = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t ** 2 * (1 - t), t ** 3
            samples.append((a * x0 + b * x1 + c * x2 + e * x3, a * y0 + b * y1 + c * y2 + e * y3))
    return samples


def distance_to_box(point: tuple[float, float], rect: tuple[float, float, float, float]) -> float:
    dx = max(rect[0] - point[0], 0, point[0] - rect[2])
    dy = max(rect[1] - point[1], 0, point[1] - rect[3])
    return (dx * dx + dy * dy) ** 0.5


def arrowhead(samples: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The triangle the marker draws at the end of a link: tip on the last point, pointing along the last stretch."""
    (tx, ty) = samples[-1]
    ax, ay = next(p for p in reversed(samples) if ((p[0] - tx) ** 2 + (p[1] - ty) ** 2) ** 0.5 > 3)
    length = ((tx - ax) ** 2 + (ty - ay) ** 2) ** 0.5
    ux, uy = (tx - ax) / length, (ty - ay) / length
    bx, by = tx - ARROW_LENGTH * ux, ty - ARROW_LENGTH * uy
    return [(tx, ty), (bx - ARROW_HALF_WIDTH * uy, by + ARROW_HALF_WIDTH * ux), (bx + ARROW_HALF_WIDTH * uy, by - ARROW_HALF_WIDTH * ux)]


def distance_to_triangle(point: tuple[float, float], triangle: list[tuple[float, float]]) -> float:
    px, py = point
    signs = []
    for (ax, ay), (bx, by) in zip(triangle, triangle[1:] + triangle[:1]):
        signs.append((bx - ax) * (py - ay) - (by - ay) * (px - ax))
    if all(s >= 0 for s in signs) or all(s <= 0 for s in signs):
        return 0.0
    best = float("inf")
    for (ax, ay), (bx, by) in zip(triangle, triangle[1:] + triangle[:1]):
        along = max(0.0, min(1.0, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2)))
        best = min(best, ((px - ax - along * (bx - ax)) ** 2 + (py - ay - along * (by - ay)) ** 2) ** 0.5)
    return best


def drawn_links(root: ET.Element) -> dict[str, list[tuple[float, float]]]:
    return {e.get("data-link"): sampled_path(e.get("d")) for e in find(root, "path") if e.get("data-link")}


def concept_boxes(root: ET.Element) -> dict[str, tuple[float, float, float, float]]:
    return {e.get("data-node"): box(e) for e in find(root, "rect") if e.get("data-node")}


def assert_links_keep_their_distance(root: ET.Element) -> None:
    boxes, links = concept_boxes(root), drawn_links(root)
    assert links, "no links drawn"
    for name, samples in links.items():
        ends = name.split(">")
        for node_id, rect in boxes.items():
            near = min(distance_to_box(p, rect) for p in samples)
            if node_id in ends:
                inside = [p for p in samples if rect[0] + 1 < p[0] < rect[2] - 1 and rect[1] + 1 < p[1] < rect[3] - 1]
                assert not inside, f"link {name} runs inside its own node {node_id}"
            else:
                assert near >= CLEARANCE, f"link {name} passes {near:.1f} units from node {node_id}"
        for other, other_samples in links.items():
            if other != name:
                head = arrowhead(other_samples)
                near = min(distance_to_triangle(p, head) for p in samples)
                assert near >= CLEARANCE, f"link {name} passes {near:.1f} units from the arrowhead of {other}"


def assert_concept_labels_clear_of_nodes(root: ET.Element) -> None:
    labels = label_boxes(root)
    assert labels, "no labels drawn"
    for name, rect in labels.items():
        for node_id, node in concept_boxes(root).items():
            assert not overlap(rect, node), f"label {name} overlaps node {node_id}"
        for other, other_rect in labels.items():
            assert other == name or not overlap(rect, other_rect), f"labels {name} and {other} overlap"


@needs_dot
@pytest.mark.parametrize("spec", [CONCEPT_SPEC, ENGRAM_CONCEPT_SPEC], ids=["sdd", "engram"])
def test_concept_links_keep_their_distance_from_every_node_and_arrowhead(tmp_path: Path, spec: dict) -> None:
    root = svg_root(tmp_path, spec)
    assert_links_keep_their_distance(root)
    assert_concept_labels_clear_of_nodes(root)


@needs_dot
@pytest.mark.parametrize("spec", [CONCEPT_SPEC, ENGRAM_CONCEPT_SPEC], ids=["sdd", "engram"])
def test_every_concept_link_still_leaves_and_reaches_the_border_of_its_own_boxes(tmp_path: Path, spec: dict) -> None:
    root = svg_root(tmp_path, spec)
    boxes = concept_boxes(root)
    for name, samples in drawn_links(root).items():
        source, target = name.split(">")
        assert distance_to_box(samples[0], boxes[source]) < 0.5, f"{name} starts away from {source}"
        assert distance_to_box(samples[-1], boxes[target]) < 0.5, f"{name} stops short of {target}"


LABEL_CLEARANCE = 8  # SVG units a concept-map link phrase keeps from every other link (path and arrowhead) and phrase
PARALLEL_CLEARANCE, PARALLEL_STRETCH, PARALLEL_ANGLE = 8, 12, 30  # units apart, longest tolerated run (units), degrees


def box_gap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    dx, dy = max(b[0] - a[2], a[0] - b[2], 0), max(b[1] - a[3], a[1] - b[3], 0)
    return (dx * dx + dy * dy) ** 0.5


def triangle_outline(triangle: list[tuple[float, float]], per_edge: int = 40) -> list[tuple[float, float]]:
    return [(ax + (bx - ax) * i / per_edge, ay + (by - ay) * i / per_edge)
            for (ax, ay), (bx, by) in zip(triangle, triangle[1:] + triangle[:1]) for i in range(per_edge)]


def assert_labels_keep_their_distance(root: ET.Element) -> None:
    links, labels = drawn_links(root), label_boxes(root)
    for name, rect in labels.items():
        for other, samples in links.items():
            if other == name:
                continue
            path = min(distance_to_box(p, rect) for p in samples)
            assert path >= LABEL_CLEARANCE, f"label {name} is {path:.1f} units from link {other}"
            head = min(distance_to_box(p, rect) for p in triangle_outline(arrowhead(samples)))
            assert head >= LABEL_CLEARANCE, f"label {name} is {head:.1f} units from the arrowhead of {other}"
        for other, other_rect in labels.items():
            if other != name:
                gap = box_gap(rect, other_rect)
                assert gap >= LABEL_CLEARANCE, f"label {name} is {gap:.1f} units from label {other}"


def resampled(samples: list[tuple[float, float]], step: float = 2.0) -> list[tuple[float, float, float, float]]:
    """x, y and the unit tangent every ``step`` units of arc length along a sampled path."""
    out, travelled, carry = [], 0.0, 0.0
    for (ax, ay), (bx, by) in zip(samples, samples[1:]):
        length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        if length < 1e-9:
            continue
        ux, uy = (bx - ax) / length, (by - ay) / length
        position = step - carry if carry else 0.0
        while position <= length:
            out.append((ax + ux * position, ay + uy * position, ux, uy))
            position += step
        carry = (carry + length) % step
    return out


def parallel_runs(root: ET.Element) -> dict[str, float]:
    """For each ordered pair of links, the longest unbroken stretch of the first within the clearance of the second at a shallow angle."""
    import math

    links = {name: resampled(samples) for name, samples in drawn_links(root).items()}
    runs = {}
    for name, mine in links.items():
        for other, theirs in links.items():
            if name == other:
                continue
            run = longest = 0.0
            for x, y, ux, uy in mine:
                near = min(theirs, key=lambda q: (q[0] - x) ** 2 + (q[1] - y) ** 2)
                close = ((near[0] - x) ** 2 + (near[1] - y) ** 2) ** 0.5 < PARALLEL_CLEARANCE
                if close and math.degrees(math.acos(min(1.0, abs(ux * near[2] + uy * near[3])))) < PARALLEL_ANGLE:
                    run += 2.0
                    longest = max(longest, run)
                else:
                    run = 0.0
            runs[f"{name} / {other}"] = longest
    return runs


def assert_no_two_links_run_side_by_side(root: ET.Element) -> None:
    for pair, run in parallel_runs(root).items():
        assert run <= PARALLEL_STRETCH, f"links {pair} run side by side for {run:.0f} units within {PARALLEL_CLEARANCE}"


@needs_dot
@pytest.mark.parametrize("spec", [CONCEPT_SPEC, ENGRAM_CONCEPT_SPEC], ids=["sdd", "engram"])
def test_every_link_phrase_keeps_its_distance_from_the_other_links_and_phrases(tmp_path: Path, spec: dict) -> None:
    assert_labels_keep_their_distance(svg_root(tmp_path, spec))


@needs_dot
@pytest.mark.parametrize("spec", [CONCEPT_SPEC, ENGRAM_CONCEPT_SPEC], ids=["sdd", "engram"])
def test_no_two_concept_links_run_side_by_side(tmp_path: Path, spec: dict) -> None:
    assert_no_two_links_run_side_by_side(svg_root(tmp_path, spec))


def _links_svg(*paths: str) -> ET.Element:
    body = "".join(f'<path data-link="l{i}>x" d="{d}"/>' for i, d in enumerate(paths))
    return ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg">{body}</svg>')


def test_the_side_by_side_check_flags_parallel_links_and_lets_crossings_pass() -> None:
    line = "M0,0 C30,0 60,0 100,0"
    assert parallel_runs(_links_svg(line, "M0,5 C30,5 60,5 100,5"))["l0>x / l1>x"] > PARALLEL_STRETCH
    assert parallel_runs(_links_svg(line, "M40,-40 C40,-15 40,15 40,40"))["l0>x / l1>x"] <= PARALLEL_STRETCH
    assert parallel_runs(_links_svg(line, "M0,12 C30,12 60,12 100,12"))["l0>x / l1>x"] == 0  # 12 units apart is fine


def _flipped(first: int, second: int) -> dict:
    spec = copy.deepcopy(CONCEPT_SPEC)
    spec["links"][first], spec["links"][second] = spec["links"][second], spec["links"][first]
    return spec


@needs_dot
def test_links_that_would_hug_each_other_fail_naming_both_links_and_write_nothing(tmp_path: Path) -> None:
    result, out = render(tmp_path, _flipped(2, 3), "--png", tmp_path / "fig.png")  # Requisitos and Problema swapped
    assert result.returncode == 2
    assert re.fullmatch(r"bauhaus_maps: links\[2\] \(spec -> req\) runs side by side with links\[3\] \(spec -> problema\) "
                        r"for \d+ units within 8; move a concept or drop one of the links\n", result.stderr), result.stderr
    assert not out.exists() and not (tmp_path / "fig.png").exists()


@needs_dot
def test_a_phrase_too_close_to_another_link_fails_naming_the_label_and_the_link(tmp_path: Path, monkeypatch, capsys) -> None:
    import bauhaus_maps

    monkeypatch.setattr(bauhaus_maps, "LABEL_AIR_X", 0)  # Graphviz is no longer told to keep room around the phrases
    monkeypatch.setattr(bauhaus_maps, "LABEL_AIR_Y", 0)
    out = tmp_path / "fig.svg"
    assert bauhaus_maps.main(["render", str(write_spec(tmp_path, CONCEPT_SPEC)), "--out", str(out)]) == 2
    assert re.fullmatch(r"bauhaus_maps: 'links\[\d+\]\.label' is \d\.\d units from links\[\d+\] \(\w+ -> \w+\), under the "
                        r"8-unit minimum; shorten it, or move the concepts or the link\n", capsys.readouterr().err)
    assert not out.exists()


BRANCH_CLEARANCE = 8  # SVG units a process-map branch label keeps from every arrowhead and every box (its own line may be close)
PROCESS_ARROW_LENGTH, PROCESS_ARROW_HALF = 8 * 1.62, 4 * 1.62  # tip-ink marker: path 8 x 4 of 10 units at 9 * 1.8 / 10 scale


def process_arrowheads(root: ET.Element) -> dict[str, list[tuple[float, float]]]:
    """Outline of the arrowhead at the end of every connector and every dashed artifact line."""
    heads = {}
    for name, points in connectors(root).items():
        (ax, ay), (tx, ty) = points[-2], points[-1]
        heads[name] = _head((tx, ty), (tx - ax, ty - ay), PROCESS_ARROW_LENGTH, PROCESS_ARROW_HALF)
    for name, points in segments(root).items():
        if name.startswith("artifact:"):
            (ax, ay), (tx, ty) = points
            heads[name] = _head((tx, ty), (tx - ax, ty - ay), 8 * 1.44, 4 * 1.44)
    return heads


def _head(tip: tuple[float, float], direction: tuple[float, float], length: float, half: float) -> list[tuple[float, float]]:
    size = (direction[0] ** 2 + direction[1] ** 2) ** 0.5
    ux, uy = direction[0] / size, direction[1] / size
    bx, by = tip[0] - length * ux, tip[1] - length * uy
    corners = [tip, (bx - half * uy, by + half * ux), (bx + half * uy, by - half * ux)]
    return triangle_outline(corners, per_edge=40)


def outline_of(element: ET.Element) -> list[tuple[float, float]]:
    """Boundary of a node (rect or diamond) sampled every half unit."""
    x0, y0, x1, y1 = box(element)
    if tag(element) == "polygon":
        corners = [tuple(map(float, p.split(","))) for p in element.get("points").split()]
    else:
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    out = []
    for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1]):
        steps = max(2, int(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 * 2))
        out += [(ax + (bx - ax) * i / steps, ay + (by - ay) * i / steps) for i in range(steps)]
    return out


def assert_branch_labels_keep_clear_of_arrowheads_and_boxes(root: ET.Element) -> None:
    labels, heads = label_boxes(root), process_arrowheads(root)
    shapes = {e.get("data-node"): e for e in root.iter() if tag(e) in ("rect", "polygon") and e.get("data-node")}
    documents = {f"artifact:{e.get('data-artifact')}": artifact_box(root, e.get("data-artifact"))
                 for e in find(root, "path") if e.get("data-artifact")}
    assert labels, "no labels drawn"
    for name, rect in labels.items():
        for other, outline in heads.items():
            near = min(distance_to_box(p, rect) for p in outline)
            assert near >= BRANCH_CLEARANCE, f"label {name} is {near:.1f} units from the arrowhead of {other}"
        for node_id, element in shapes.items():
            outline = outline_of(element)
            inside = tag(element) == "polygon" and all(rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3] for x, y in outline[:1])
            near = 0.0 if inside else min(distance_to_box(p, rect) for p in outline)
            assert near >= BRANCH_CLEARANCE, f"label {name} is {near:.1f} units from node {node_id}"
        for doc_id, doc in documents.items():
            assert box_gap(rect, doc) >= BRANCH_CLEARANCE, f"label {name} is too close to {doc_id}"


@needs_dot
@pytest.mark.parametrize("spec", [PROCESS_SPEC, ENGRAM_PROCESS_SPEC, ROUTES_SPEC, STRESS_SPEC, _labelled_lattice()],
                         ids=["spec-kit", "engram", "routes", "stress", "lattice"])
def test_branch_labels_keep_clear_of_arrowheads_and_boxes(tmp_path: Path, spec: dict) -> None:
    assert_branch_labels_keep_clear_of_arrowheads_and_boxes(svg_root(tmp_path, spec))


@needs_dot
@needs_rsvg
def test_the_measured_label_ink_matches_the_pixels_rsvg_draws(tmp_path: Path) -> None:
    from PIL import Image

    result, out = render(tmp_path, CONCEPT_SPEC, "--png", tmp_path / "fig.png")
    assert result.returncode == 0, result.stderr
    root = ET.fromstring(out.read_text(encoding="utf-8"))
    pixels = Image.open(tmp_path / "fig.png").convert("RGB")
    for name in ("spec>clar", "const>plan"):  # a phrase with descenders and one with accents
        label = next(e for e in find(root, "text") if e.get("data-label") == name)
        colour = tuple(int(label.get("fill")[i:i + 2], 16) for i in (1, 3, 5))
        x0, y0, x1, y1 = label_boxes(root)[name]
        rows = [py for py in range(int((y0 - 6) * 2), int((y1 + 6) * 2))
                if any(sum(abs(a - b) for a, b in zip(pixels.getpixel((px, py)), colour)) < 90
                       for px in range(int(x0 * 2), int(x1 * 2)))]
        assert abs(min(rows) / 2 - y0) <= 1 and abs((max(rows) + 1) / 2 - y1) <= 1, (name, (y0, y1), (min(rows) / 2, (max(rows) + 1) / 2))


# --- review follow-ups: publish, last-resort spots, side-by-side runs -------


def _umask() -> int:
    import os

    mask = os.umask(0)
    os.umask(mask)
    return mask


def test_publish_gives_new_files_the_umask_mode(tmp_path: Path) -> None:
    """Review R3-publish-file-mode: a published file is not left owner-only (0600)."""
    import bauhaus_maps

    out = tmp_path / "fig.svg"
    bauhaus_maps.publish([(out, b"<svg/>")])

    assert out.stat().st_mode & 0o777 == 0o666 & ~_umask()


def test_publish_keeps_the_mode_of_a_file_it_replaces(tmp_path: Path) -> None:
    import bauhaus_maps

    out = tmp_path / "fig.svg"
    out.write_bytes(b"old")
    out.chmod(0o640)
    bauhaus_maps.publish([(out, b"<svg/>")])

    assert out.read_bytes() == b"<svg/>"
    assert out.stat().st_mode & 0o777 == 0o640


def test_publish_restores_every_replaced_file_when_a_later_one_fails(tmp_path: Path, monkeypatch) -> None:
    """Review R3-publish-partial-overwrite: all or none holds for files that already existed."""
    import os

    import bauhaus_maps

    svg, png = tmp_path / "fig.svg", tmp_path / "fig.png"
    svg.write_bytes(b"old svg")
    png.write_bytes(b"old png")
    real_replace = os.replace

    def failing_replace(source, destination):
        if Path(destination) == png and Path(source).name.endswith(".tmp"):
            raise PermissionError(13, "Permission denied", str(png))
        return real_replace(source, destination)

    monkeypatch.setattr(bauhaus_maps.os, "replace", failing_replace)
    with pytest.raises(bauhaus_maps.SpecError, match="cannot write the output"):
        bauhaus_maps.publish([(svg, b"new svg"), (png, b"new png")])

    assert svg.read_bytes() == b"old svg"
    assert png.read_bytes() == b"old png"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["fig.png", "fig.svg"]


def test_last_resort_spots_stay_bounded_on_a_tall_connector() -> None:
    """Review R3-last-resort-search-cost: the fine last-resort search does not grow with the connector."""
    import bauhaus_maps

    short = sum(1 for _ in bauhaus_maps._spots([(0, 0), (0, 600)], 50))
    tall = sum(1 for _ in bauhaus_maps._spots([(0, 0), (0, 6000)], 50))

    assert tall - short < 2_000


def test_separate_short_side_by_side_stretches_do_not_add_up() -> None:
    """Review R3-parallel-run-not-contiguous: only one unbroken stretch counts against the limit."""
    import bauhaus_maps

    model = {"links": [{"from": "a", "to": "b"}, {"from": "c", "to": "d"}]}
    straight = [(0, 0), (100, 0)]
    # Two 5-unit hugs, 40 units apart: each is under the limit, together they are over it.
    comb = [(20, 60), (20, 6), (25, 6), (25, 60), (60, 60), (60, 6), (65, 6), (65, 60)]

    bauhaus_maps._guard_links(model, {0: straight, 1: comb}, {})


def test_publish_never_restores_a_backup_that_failed_to_copy(tmp_path: Path, monkeypatch) -> None:
    """Review R3-publish-restores-incomplete-backup: a half-written backup never replaces the original."""
    import bauhaus_maps

    svg = tmp_path / "fig.svg"
    svg.write_bytes(b"precious old map")

    def failing_copy(source, destination):
        Path(destination).write_bytes(b"prec")
        raise OSError(28, "No space left on device", str(destination))

    monkeypatch.setattr(bauhaus_maps.shutil, "copy2", failing_copy)
    with pytest.raises(bauhaus_maps.SpecError, match="No space left on device"):
        bauhaus_maps.publish([(svg, b"new map")])

    assert svg.read_bytes() == b"precious old map"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["fig.svg"]

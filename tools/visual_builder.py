#!/usr/bin/env python3
"""Render and validate academic visuals for UNL report automation.

Renderers:
- Mermaid CLI for diagrams.
- Vega-Lite / vl-convert for academic charts.
- ECharts SVG SSR through Node.
- HTML screenshot through Playwright + local Chrome for custom cards.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from textwrap import dedent

from connector_geometry import audit_connector_geometry, run_geometry_audit
from report_config import CONTENT_ROOT
from visual_metadata import validate_visual_manifest
from visual_pdf_auditor import FAILURE, INFO

ROOT = Path(__file__).resolve().parents[1]
# Toolchain: node_modules is reinstalled with the code, so it stays CODE.
NODE_BIN = ROOT / "node_modules" / ".bin"
# Every file Node itself has to open — the generated .cjs renderers and the
# puppeteer config — lives HERE, inside the code checkout, and not in the
# content tree. Node resolves `require('playwright')` by walking UP from the
# script's own directory, so a script parked under CONTENT_ROOT can never reach
# ROOT/node_modules, which is exactly where NODE_BIN already expects the
# toolchain to be. `.cache/` is gitignored and already holds toolchain scratch
# (see LOCAL_CHROME_ROOTS), so nothing leaks into the checkout's status.
NODE_SCRATCH = ROOT / ".cache" / "visual-renders"
# Chrome is toolchain too, so the code checkout is searched first; the content
# tree is kept as a fallback because that is where the existing install lives.
LOCAL_CHROME_ROOTS = (
    ROOT / ".cache" / "puppeteer" / "chrome",
    CONTENT_ROOT / ".cache" / "puppeteer" / "chrome",
)
# Back-compat alias for importers of the single-root name.
LOCAL_CHROME_ROOT = LOCAL_CHROME_ROOTS[0]
# Browser layouts, per manager. @puppeteer/browsers names its builds after the
# platform, Playwright after the Chromium revision; Playwright also used a
# `chrome-linux/` directory before it moved to `chrome-linux64/`.
PUPPETEER_CHROME_GLOBS = ("linux-*/chrome-linux64/chrome",)
PLAYWRIGHT_CHROME_GLOBS = (
    "chromium-*/chrome-linux64/chrome",
    "chromium-*/chrome-linux/chrome",
)
PLAYWRIGHT_BROWSERS_PATH_ENV = "PLAYWRIGHT_BROWSERS_PATH"
DEFAULT_WIDTH = 1400
DEFAULT_HEIGHT = 900


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(str(c) for c in cmd))
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(cmd, cwd=cwd or ROOT, env=merged_env, text=True, capture_output=True)
    if proc.returncode != 0:
        if proc.stdout:
            print(proc.stdout)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"FAILED: {' '.join(str(c) for c in cmd)}")
    if proc.stdout.strip():
        print(proc.stdout.strip())
    return proc


def resolve_path(path: str | Path) -> Path:
    """Resolve a CLI path argument after the code/content split.

    A relative argument is genuinely ambiguous now: spec inputs (visuals/specs)
    and rendered outputs (assets/generated) are content, while a shipped
    stylesheet under templates/ is code. Existing files are looked up in the
    caller's cwd, then the content tree, then the code tree — so every relative
    path that worked before still resolves to the same file.

    A path that exists nowhere is an OUTPUT about to be written; everything this
    tool generates is content, so it lands under the content root.
    """
    p = Path(path)
    if p.is_absolute():
        return p
    for base in (Path.cwd(), CONTENT_ROOT, ROOT):
        candidate = base / p
        if candidate.exists():
            return candidate
    return CONTENT_ROOT / p


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def node_module_dirs(start: Path) -> list[Path]:
    """Every ``node_modules`` Node would consult for a require from ``start``.

    Node's CommonJS resolver walks up from the requiring file's own directory,
    so this is the whole reason generated scripts must live under ROOT.
    """
    return [parent / "node_modules" for parent in (start, *start.parents)]


def resolves_node_package(name: str, start: Path | None = None) -> bool:
    """True when a script in ``start`` could ``require(name)``."""
    root = start or NODE_SCRATCH
    return any((modules / name).is_dir() for modules in node_module_dirs(root))


def require_node_package(name: str, start: Path | None = None) -> None:
    """Fail early, and accurately, when the Node toolchain is not installed.

    Without this the user only ever saw a raw MODULE_NOT_FOUND stack trace from
    Node, which named neither the package to install nor the directory to
    install it in.
    """
    if shutil.which("node") is None:
        raise SystemExit(
            "Node no encontrado en el PATH. Instalá Node.js para generar visuales."
        )
    if resolves_node_package(name, start):
        return
    raise SystemExit(
        f"Dependencia Node '{name}' no encontrada en {ROOT / 'node_modules'}. "
        f"Instalá el toolchain de este repositorio con: npm install --prefix {ROOT}"
    )


def playwright_browser_roots() -> tuple[Path, ...]:
    """Where Playwright keeps its managed browsers on this machine.

    ``PLAYWRIGHT_BROWSERS_PATH=0`` is Playwright's documented way of asking for
    the browsers to be stored next to the package itself.
    """
    override = (os.environ.get(PLAYWRIGHT_BROWSERS_PATH_ENV) or "").strip()
    if override == "0":
        return (ROOT / "node_modules" / "playwright-core" / ".local-browsers",)
    if override:
        return (Path(override).expanduser(),)
    return (Path.home() / ".cache" / "ms-playwright",)


def chrome_search_plan() -> list[tuple[Path, tuple[str, ...]]]:
    """Browser roots to search, in priority order, with their layout globs.

    The puppeteer roots come first so an install that already works keeps
    working; the Playwright cache is appended because ``playwright`` is what
    package.json actually declares.
    """
    plan: list[tuple[Path, tuple[str, ...]]] = [
        (root, PUPPETEER_CHROME_GLOBS) for root in LOCAL_CHROME_ROOTS
    ]
    plan.append((Path.home() / ".cache" / "puppeteer" / "chrome", PUPPETEER_CHROME_GLOBS))
    plan.extend((root, PLAYWRIGHT_CHROME_GLOBS) for root in playwright_browser_roots())
    return plan


def newest_executable(root: Path, patterns: tuple[str, ...]) -> Path | None:
    """Newest executable matching any of ``patterns`` under ``root``."""
    candidates = [
        candidate
        for pattern in patterns
        for candidate in root.glob(pattern)
        if candidate.exists() and os.access(candidate, os.X_OK)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def newest_local_chrome() -> Path | None:
    for chrome_root, patterns in chrome_search_plan():
        found = newest_executable(chrome_root, patterns)
        if found:
            return found
    return None


def require_chrome() -> Path:
    chrome = newest_local_chrome()
    if not chrome:
        raise SystemExit(
            "Chrome/Chromium no encontrado. Instalá el navegador del toolchain "
            f"ejecutando en {ROOT}: npx playwright install chromium"
        )
    return chrome


def mmdc_bin() -> Path:
    local = NODE_BIN / "mmdc"
    if local.exists():
        return local
    global_bin = shutil.which("mmdc")
    if global_bin:
        return Path(global_bin)
    raise SystemExit("Mermaid CLI no encontrado. Instalá @mermaid-js/mermaid-cli localmente.")


def puppeteer_config() -> Path:
    NODE_SCRATCH.mkdir(parents=True, exist_ok=True)
    chrome = require_chrome()
    config = NODE_SCRATCH / "puppeteer-config.json"
    config.write_text(json.dumps({"executablePath": str(chrome), "args": ["--no-sandbox"]}, indent=2), encoding="utf-8")
    return config


def command_mermaid(args: argparse.Namespace) -> int:
    src = resolve_path(args.input)
    out = resolve_path(args.out)
    ensure_parent(out)
    if not src.exists():
        raise SystemExit(f"No existe spec Mermaid: {src}")
    cmd = [
        str(mmdc_bin()),
        "-i", str(src),
        "-o", str(out),
        "-w", str(args.width),
        "-H", str(args.height),
        "-b", args.background,
        "-p", str(puppeteer_config()),
    ]
    if args.scale is not None:
        if not math.isfinite(args.scale) or args.scale <= 0:
            raise SystemExit(
                f"--scale inválido: {args.scale}. Usá un número finito mayor que 0."
            )
        cmd.extend(["-s", str(args.scale)])
    if args.css_file:
        cmd.extend(["-C", str(resolve_path(args.css_file))])
    if args.theme:
        cmd.extend(["-t", args.theme])
    run(cmd)
    print(f"VISUAL={out}")
    return 0


def command_vegalite(args: argparse.Namespace) -> int:
    src = resolve_path(args.input)
    out = resolve_path(args.out)
    ensure_parent(out)
    if not src.exists():
        raise SystemExit(f"No existe spec Vega-Lite: {src}")
    spec = json.loads(src.read_text(encoding="utf-8"))
    fmt = args.format or out.suffix.lower().lstrip(".") or "svg"
    import vl_convert as vlc  # type: ignore

    if fmt == "svg":
        rendered = vlc.vegalite_to_svg(spec)
        out.write_text(rendered, encoding="utf-8")
    elif fmt == "png":
        rendered = vlc.vegalite_to_png(spec, scale=args.scale)
        out.write_bytes(rendered)
    elif fmt == "pdf":
        rendered = vlc.vegalite_to_pdf(spec)
        out.write_bytes(rendered)
    else:
        raise SystemExit("Formato Vega-Lite soportado: svg, png, pdf")
    print(f"VISUAL={out}")
    return 0


def command_echarts(args: argparse.Namespace) -> int:
    src = resolve_path(args.input)
    out = resolve_path(args.out)
    ensure_parent(out)
    if not src.exists():
        raise SystemExit(f"No existe spec ECharts: {src}")
    node_script = dedent(
        """
        const fs = require('fs');
        const echarts = require('echarts');
        const [specPath, outPath, widthRaw, heightRaw] = process.argv.slice(2);
        const option = JSON.parse(fs.readFileSync(specPath, 'utf8'));
        const width = Number(widthRaw || 1400);
        const height = Number(heightRaw || 900);
        const chart = echarts.init(null, null, { renderer: 'svg', ssr: true, width, height });
        chart.setOption(option);
        fs.writeFileSync(outPath, chart.renderToSVGString(), 'utf8');
        chart.dispose();
        """
    )
    require_node_package("echarts")
    NODE_SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".cjs", dir=NODE_SCRATCH, delete=False, encoding="utf-8") as tmp:
        tmp.write(node_script)
        tmp_path = Path(tmp.name)
    try:
        run(["node", str(tmp_path), str(src), str(out), str(args.width), str(args.height)])
    finally:
        tmp_path.unlink(missing_ok=True)
    print(f"VISUAL={out}")
    return 0


def command_html_shot(args: argparse.Namespace) -> int:
    src = resolve_path(args.input)
    out = resolve_path(args.out)
    ensure_parent(out)
    if not src.exists():
        raise SystemExit(f"No existe HTML: {src}")
    require_node_package("playwright")
    chrome = require_chrome()
    node_script = dedent(
        """
        const { chromium } = require('playwright');
        const path = require('path');
        const [htmlPath, outPath, widthRaw, heightRaw, selector, chromePath] = process.argv.slice(2);
        (async () => {
          const browser = await chromium.launch({ executablePath: chromePath, headless: true, args: ['--no-sandbox'] });
          const page = await browser.newPage({ viewport: { width: Number(widthRaw || 1400), height: Number(heightRaw || 900) }, deviceScaleFactor: 2 });
          await page.goto('file://' + path.resolve(htmlPath), { waitUntil: 'networkidle' });
          if (selector && selector !== 'page') {
            await page.locator(selector).screenshot({ path: outPath, omitBackground: false });
          } else {
            await page.screenshot({ path: outPath, fullPage: true, omitBackground: false });
          }
          await browser.close();
        })().catch(err => { console.error(err); process.exit(1); });
        """
    )
    NODE_SCRATCH.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".cjs", dir=NODE_SCRATCH, delete=False, encoding="utf-8") as tmp:
        tmp.write(node_script)
        tmp_path = Path(tmp.name)
    try:
        run(["node", str(tmp_path), str(src), str(out), str(args.width), str(args.height), args.selector, str(chrome)])
    finally:
        tmp_path.unlink(missing_ok=True)
    print(f"VISUAL={out}")
    return 0


def validate_image(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"no existe: {path}"]
    if path.stat().st_size < 800:
        errors.append(f"archivo demasiado pequeño: {path}")
    suffix = path.suffix.lower()
    if suffix == ".svg":
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "<svg" not in text:
            errors.append(f"SVG inválido: {path}")
        if not re.search(r"(width|viewBox)=", text):
            errors.append(f"SVG sin width/viewBox: {path}")
    elif suffix == ".png":
        from PIL import Image

        with Image.open(path) as im:
            w, h = im.size
            if max(w, h) < 800 or min(w, h) < 350:
                errors.append(f"PNG demasiado pequeño ({w}x{h}): {path}")
    elif suffix == ".pdf":
        if path.stat().st_size < 2000:
            errors.append(f"PDF visual demasiado pequeño: {path}")
    else:
        errors.append(f"formato no validable: {path}")
    return errors


def metadata_errors(folder: Path) -> list[str]:
    meta = folder / "figures.yml"
    return validate_visual_manifest(folder, meta).errors


def command_validate(args: argparse.Namespace) -> int:
    target = resolve_path(args.target)
    if not target.exists():
        raise SystemExit(f"No existe target: {target}")
    files = [target] if target.is_file() else sorted(
        p for p in target.rglob("*") if p.suffix.lower() in {".svg", ".png", ".pdf"}
    )
    if not files:
        # Nothing to work on is a hard failure, not a quality finding.
        raise SystemExit("VALIDATION FAILED:\n- no hay visuales SVG/PNG/PDF para validar")
    errors: list[str] = []
    for file in files:
        errors.extend(validate_image(file))
        if file.suffix.lower() == ".svg":
            # Connector geometry is a FAILURE-severity gate for diagrams; chart
            # SVGs simply carry no nodes/edges and stay silent. ANY geometry
            # exception (malformed XML, corrupted path/point data) becomes a
            # reported finding here too, through the same guard
            # validate_report.py's final-size stage uses (#43 T2) — one bad
            # file must not crash an entire folder validate run.
            issues = run_geometry_audit(file.name, lambda file=file: audit_connector_geometry(file))
            errors.extend(f"{i.tag}: {i.detail}" for i in issues if i.level == FAILURE)
            # INFO findings (e.g. CONNECTOR_DIRECTION_NO_SOURCE) never block
            # validation, but they must still be visible -- silently
            # dropping them would hide that the direction/marker check ran
            # in its strict fallback mode (R3-no-source-info-dropped-in-
            # validate, native review).
            for i in issues:
                if i.level == INFO:
                    print(f"INFO {i.tag}: {i.detail}")
    if target.is_dir() and not args.no_metadata:
        errors.extend(metadata_errors(target))
    if errors:
        # warn-only-gates S2: a finding judges the figures' quality; it is
        # reported on stderr, the figures stay and the command exits 0.
        print("warning: VALIDATION FAILED:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 0
    print(f"VALIDATION_OK {target}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Academic visual renderer for UNL report automation")
    sub = parser.add_subparsers(dest="command", required=True)

    mermaid = sub.add_parser("mermaid", help="Render Mermaid spec to SVG/PNG/PDF")
    mermaid.add_argument("input")
    mermaid.add_argument("--out", required=True)
    mermaid.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    mermaid.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    mermaid.add_argument("--background", default="white")
    mermaid.add_argument("--theme", default="neutral")
    mermaid.add_argument(
        "--scale",
        type=float,
        default=None,
        help="Raster scale factor passed to mermaid (-s); omit for the native default",
    )
    mermaid.add_argument("--css-file", help="CSS file to style Mermaid output")
    mermaid.set_defaults(func=command_mermaid)

    vegalite = sub.add_parser("vegalite", help="Render Vega-Lite JSON spec")
    vegalite.add_argument("input")
    vegalite.add_argument("--out", required=True)
    vegalite.add_argument("--format", choices=["svg", "png", "pdf"])
    vegalite.add_argument("--scale", type=float, default=2.0)
    vegalite.set_defaults(func=command_vegalite)

    echarts = sub.add_parser("echarts", help="Render ECharts JSON option to SVG")
    echarts.add_argument("input")
    echarts.add_argument("--out", required=True)
    echarts.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    echarts.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    echarts.set_defaults(func=command_echarts)

    html = sub.add_parser("html-shot", help="Screenshot local HTML through Playwright + local Chrome")
    html.add_argument("input")
    html.add_argument("--out", required=True)
    html.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    html.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    html.add_argument("--selector", default="page")
    html.set_defaults(func=command_html_shot)

    validate = sub.add_parser("validate", help="Validate generated visual file/folder")
    validate.add_argument("target")
    validate.add_argument("--no-metadata", action="store_true")
    validate.set_defaults(func=command_validate)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

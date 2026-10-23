"""RED tests for the contextual table style catalog and selector (issue #13).

Covers spec scenarios R1-R4:
  R1 test_issue_13_exact_versioned_catalog
  R2 test_issue_13_catalog_is_runtime_self_contained
  R3 test_issue_13_context_matrix_is_deterministic
  R4 test_issue_13_applicability_and_avoidance
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from table_styles import (  # noqa: E402
    APPROVED_STYLE_IDS,
    CatalogError,
    REQUIRED_TOKEN_KEYS,
    TableContext,
    eligible_candidates,
    load_catalog,
    select_style,
)

ROOT = TOOLS.parent


def test_issue_13_exact_versioned_catalog() -> None:
    catalog = load_catalog()

    assert catalog.schema_version == 1
    assert isinstance(catalog.catalog_version, str) and catalog.catalog_version.strip()
    assert set(catalog.styles) == APPROVED_STYLE_IDS

    for style_id, style in catalog.styles.items():
        assert style.id == style_id
        assert style.label.strip()
        assert set(style.tokens) == REQUIRED_TOKEN_KEYS
        assert style.applicability is not None
        assert style.avoidance is not None


def test_issue_13_catalog_is_runtime_self_contained() -> None:
    # Neither the loader source nor the catalog file may depend on the
    # private evaluation artifact's absolute path or parse a PDF at runtime.
    source = (TOOLS / "table_styles.py").read_text(encoding="utf-8")
    catalog_text = (ROOT / "templates" / "table_styles.yml").read_text(encoding="utf-8")
    for forbidden in ("reports-system", ".pdf", "PyPDF", "pdfplumber"):
        assert forbidden not in source
        assert forbidden not in catalog_text

    # Selection succeeds without touching any private/content-root path.
    catalog = load_catalog()
    context = TableContext(
        purpose="reference", length="short", density="low", columns=3, rows=5,
        pagination="single",
    )
    result = select_style(context, catalog)
    assert result.style_id in APPROVED_STYLE_IDS


SHORT = TableContext(purpose="reference", length="short", density="low", columns=3, rows=5, pagination="single")
LONG = TableContext(purpose="reference", length="long", density="medium", columns=3, rows=10, pagination="single")
COMPARISON = TableContext(
    purpose="comparison", length="short", density="medium", columns=4, rows=6,
    pagination="single", emphasis="column", meaning="comparison",
)
STATUS = TableContext(
    purpose="status", length="short", density="medium", columns=4, rows=6,
    pagination="single", meaning="status",
)
DENSE = TableContext(purpose="dense", length="long", density="high", columns=6, rows=20, pagination="single")
MULTIPAGE = TableContext(
    purpose="reference", length="long", density="medium", columns=3, rows=40,
    pagination="multipage",
)


def test_issue_13_context_matrix_is_deterministic() -> None:
    catalog = load_catalog()
    expected = {
        "short": ("TAB-CL-01", SHORT),
        "long": ("TAB-ZB-04", LONG),
        "comparison": ("TAB-CE-05", COMPARISON),
        "status": ("TAB-ES-06", STATUS),
        "dense": ("TAB-CC-07", DENSE),
        "multipage": ("TAB-ZB-04", MULTIPAGE),
    }
    for name, (expected_id, context) in expected.items():
        first = select_style(context, catalog)
        second = select_style(context, catalog)
        assert first.style_id == expected_id, name
        assert second.style_id == expected_id, name
        assert first.rationale == second.rationale, name
        assert first.rationale.strip()


def test_status_indicators_are_versioned_symbol_plus_color_plus_label() -> None:
    """Extends R1: status markers (`[[status:<value>]]`) never rely on color
    alone -- every approved value defines a distinct symbol and an
    accessible text label alongside its color (authoring convention
    approved 2026-09-22, see odd/tasks/contextual-table-styles.md)."""
    catalog = load_catalog()

    assert catalog.status_indicators
    for value, indicator in catalog.status_indicators.items():
        assert indicator.symbol.strip()
        assert indicator.color.strip()
        assert indicator.label.strip()
    # Every symbol is visually distinct -- color is never the only signal.
    symbols = [indicator.symbol for indicator in catalog.status_indicators.values()]
    assert len(symbols) == len(set(symbols))


def _valid_raw_catalog() -> dict:
    text = (ROOT / "templates" / "table_styles.yml").read_text(encoding="utf-8")
    return yaml.safe_load(text)


def _write_catalog(tmp_path: Path, raw) -> Path:
    path = tmp_path / "table_styles.yml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def _mutate(raw: dict, *path_and_value) -> dict:
    """``_mutate(raw, "styles", "TAB-CL-01", "deprecated", "bad")`` sets a
    nested key; the last positional argument is the value."""
    *keys, value = path_and_value
    cursor = raw
    for key in keys[:-1]:
        cursor = cursor[key]
    cursor[keys[-1]] = value
    return raw


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda raw: "not-a-mapping", "top level must be a mapping"),
        (lambda raw: {**raw, "extra_top_level_key": True}, "unknown top-level keys"),
        (lambda raw: {k: v for k, v in raw.items() if k != "catalog_version"}, "missing top-level keys"),
        (lambda raw: _mutate(raw, "schema_version", 2), "unsupported schema_version"),
        (lambda raw: _mutate(raw, "catalog_version", ""), "'catalog_version' must be a non-empty string"),
        (lambda raw: _mutate(raw, "styles", "not-a-mapping"), "'styles' must be a mapping"),
        (lambda raw: {**raw, "styles": {k: v for k, v in raw["styles"].items() if k != "TAB-CL-01"}},
         "styles must define exactly the approved IDs"),
        (lambda raw: _mutate(raw, "styles", "TAB-CL-01", "not-a-mapping"), "style entry must be a mapping"),
        (lambda raw: _mutate(raw, "styles", "TAB-CL-01", "extra_key", True), "unknown keys"),
        (lambda raw: {**raw, "styles": {**raw["styles"], "TAB-CL-01":
            {k: v for k, v in raw["styles"]["TAB-CL-01"].items() if k != "label"}}}, "missing required keys"),
        (lambda raw: _mutate(raw, "styles", "TAB-CL-01", "label", ""), "'label' must be a non-empty string"),
        (lambda raw: _mutate(raw, "styles", "TAB-CL-01", "deprecated", "yes"), "'deprecated' must be a bool"),
        (lambda raw: _mutate(raw, "styles", "TAB-CL-01", "priority", "high"), "'priority' must be an int"),
        (lambda raw: _mutate(raw, "styles", "TAB-CL-01", "tokens", "not-a-mapping"), "'tokens' must be a mapping"),
        (lambda raw: {**raw, "styles": {**raw["styles"], "TAB-CL-01":
            {**raw["styles"]["TAB-CL-01"], "tokens":
                {k: v for k, v in raw["styles"]["TAB-CL-01"]["tokens"].items() if k != "borders"}}}},
         "tokens must define exactly"),
        (lambda raw: _mutate(raw, "styles", "TAB-CL-01", "tokens", "borders", "diagonal"),
         "is not one of"),
        (lambda raw: _mutate(raw, "styles", "TAB-CL-01", "applicability", "not-a-mapping"),
         "'applicability' must be a mapping"),
        (lambda raw: _mutate(raw, "styles", "TAB-CL-01", "applicability", "purposes", []),
         "applicability.purposes must be a non-empty list"),
        (lambda raw: _mutate(raw, "styles", "TAB-CL-01", "applicability", "purposes", ["invented"]),
         "applicability.purposes has invalid values"),
        (lambda raw: _mutate(raw, "styles", "TAB-CL-01", "applicability", "max_columns", "four"),
         "applicability.max_columns must be an int"),
        (lambda raw: {**raw, "status_indicators": "not-a-mapping"},
         "'status_indicators' must be a non-empty mapping"),
        (lambda raw: _mutate(raw, "status_indicators", "ok", "color", "not-a-hex"),
         "'color' must be a #RRGGBB hex string"),
        (lambda raw: _mutate(raw, "status_indicators", "ok", "symbol", raw["status_indicators"]["fail"]["symbol"]),
         "symbol .* reused"),
    ],
)
def test_issue_13_loader_rejects_every_malformed_shape(tmp_path: Path, mutate, match: str) -> None:
    """The strict loader's own contract (design: "Unknown keys, missing
    tokens, invalid enums/colors, duplicate IDs, or non-approved ID sets block
    load") was entirely unexercised -- every named rejection path is now
    proven to actually raise ``CatalogError`` (T1+T2 review
    R3-untested-loader-rejections)."""
    raw = mutate(copy.deepcopy(_valid_raw_catalog()))
    path = _write_catalog(tmp_path, raw)
    with pytest.raises(CatalogError, match=match):
        load_catalog(path)


def _bump(context: TableContext, **fields: object) -> TableContext:
    return TableContext(**{**context.__dict__, **fields})


def test_issue_13_avoidance_and_applicability_coverage() -> None:
    """Every avoidance/applicability rule actually declared in the catalog
    must exclude/admit a style, not merely exist as unexercised YAML (T1+T2
    review R3-catalog-coverage-gaps): for every style and every constraint
    key its avoidance block declares, a context that hits that constraint
    must exclude the style from ``eligible_candidates`` -- generic over the
    catalog, so a future avoidance rule is covered automatically."""
    catalog = load_catalog()
    base = SHORT

    for style_id, style in catalog.styles.items():
        for key, allowed_values in style.avoidance.items():
            field_name = {
                "purposes": "purpose", "lengths": "length", "meanings": "meaning",
                "emphasis": "emphasis", "density": "density", "color_policy": "color_policy",
            }[key]
            triggering = _bump(base, **{field_name: allowed_values[0]})
            candidates = eligible_candidates(triggering, catalog)
            assert style_id not in candidates, (
                f"{style_id}: avoidance.{key}={allowed_values[0]!r} did not exclude it"
            )

    for style_id, style in catalog.styles.items():
        max_columns = style.applicability.get("max_columns")
        if max_columns is not None:
            too_wide = _bump(base, purpose=style.applicability["purposes"][0], columns=max_columns + 1)
            assert style_id not in eligible_candidates(too_wide, catalog), (
                f"{style_id}: applicability.max_columns={max_columns} did not exclude a wider table"
            )


def test_issue_13_applicability_and_avoidance() -> None:
    catalog = load_catalog()

    # Avoidance: TAB-CL-01 explicitly avoids high-density contexts.
    high_density_reference = TableContext(
        purpose="reference", length="short", density="high", columns=3, rows=5, pagination="single",
    )
    candidates = eligible_candidates(high_density_reference, catalog)
    assert "TAB-CL-01" not in candidates

    # Applicability: TAB-MN-03 only applies to short tables.
    long_reference = TableContext(
        purpose="reference", length="long", density="low", columns=3, rows=10, pagination="single",
    )
    candidates = eligible_candidates(long_reference, catalog)
    assert "TAB-MN-03" not in candidates

    # Sanity: both exclusions leave at least one eligible style.
    assert eligible_candidates(high_density_reference, catalog)
    assert eligible_candidates(long_reference, catalog)

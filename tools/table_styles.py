"""Versioned catalog and deterministic selector for contextual table styles.

Issue #13: replace the single generic table treatment with an explainable,
institutionally controllable selection among approved styles. This
module owns exactly two things:

1. A strict loader for ``templates/table_styles.yml`` — the executable
   source of truth. It never reads a private path or parses a PDF; the
   original human-review catalog exists only as design-time prose that this
   file's tokens/applicability/avoidance rules were derived from once (see
   ``templates/table_styles.yml`` header).
2. A pure ``select_style(context, catalog)`` that maps a normalized
   ``TableContext`` to one approved, applicable, non-avoided style — or
   raises ``UnsupportedContextError`` when none qualifies. It has no
   knowledge of overrides or evidence receipts; those belong to
   ``tools/table_model.py`` (issue #13 slice 2), which calls this selector
   only after teacher/institution overrides are checked.

Determinism: identical context input always yields the identical
``SelectionResult`` (same ID, same rationale text) because selection depends
only on the loaded catalog and the context fields — no randomness, no
filesystem/time reads inside ``select_style`` itself.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml

from report_config import ROOT

DEFAULT_CATALOG_PATH = ROOT / "templates" / "table_styles.yml"

APPROVED_STYLE_IDS = frozenset({
    "TAB-CL-01",
    "TAB-TC-02",
    "TAB-MN-03",
    "TAB-ZB-04",
    "TAB-CE-05",
    "TAB-ES-06",
    "TAB-CC-07",
    "TAB-IN-08",
})

REQUIRED_TOKEN_KEYS = frozenset({
    "borders", "header", "alignment", "padding", "density", "row_rhythm",
    "palette", "indicators", "caption", "notes",
})

TOKEN_ENUMS: dict[str, frozenset[str]] = {
    "borders": frozenset({"full_grid", "horizontal_only", "minimal"}),
    "header": frozenset({"gray_shaded", "dark_shaded", "institutional_shaded", "plain"}),
    "alignment": frozenset({"centered", "left", "numeric_right"}),
    "padding": frozenset({"generous", "standard", "compact", "minimal"}),
    "density": frozenset({"low", "medium", "high"}),
    "row_rhythm": frozenset({"uniform", "alternating", "column_emphasis"}),
    "palette": frozenset({"monochrome", "functional_color", "accent_color"}),
    "indicators": frozenset({"none", "symbol_color"}),
    "caption": frozenset({"above", "below"}),
    "notes": frozenset({"below", "inline"}),
}

# Allowed keys inside a style's applicability/avoidance block, and the enum
# each maps to for validation. `max_columns` is the only numeric constraint.
_CONSTRAINT_ENUMS: dict[str, frozenset[str] | None] = {
    "purposes": frozenset({"reference", "comparison", "status", "evidence", "dense"}),
    "lengths": frozenset({"short", "long"}),
    "meanings": frozenset({"none", "comparison", "status"}),
    "emphasis": frozenset({"none", "column"}),
    "density": frozenset({"low", "medium", "high"}),
    "color_policy": frozenset({"color", "grayscale"}),
    "max_columns": None,
}

_APPLICABILITY_KEYS = frozenset(_CONSTRAINT_ENUMS) - {"color_policy"}
_AVOIDANCE_KEYS = frozenset(_CONSTRAINT_ENUMS) - {"max_columns"}

# Constraint key -> TableContext field name (constraint keys are plural,
# context fields are singular; color_policy already matches both).
_CONSTRAINT_FIELD = {
    "purposes": "purpose",
    "lengths": "length",
    "meanings": "meaning",
    "emphasis": "emphasis",
    "density": "density",
    "color_policy": "color_policy",
}

_TOP_LEVEL_KEYS = frozenset({"schema_version", "catalog_version", "styles", "status_indicators"})
_STYLE_KEYS = frozenset({"label", "deprecated", "priority", "automatic", "tokens", "applicability", "avoidance"})

# Shared literal shading colors every backend's token mapper renders for the
# same token, so LaTeX/DOCX/HTML stay coherent (spec: "backend mappings MUST
# preserve meaning"; `test_issue_13_backend_style_coherence`) instead of each
# mapper hand-picking its own hex value that silently drifts from the
# others. Uppercase, no leading `#` -- DOCX/OOXML's native ``w:fill`` format;
# each mapper (and any test needing these colors) derives its own spelling.
HEADER_FILL_HEX = {"gray_shaded": "EAEAEA", "dark_shaded": "404040", "institutional_shaded": "1F5F8B"}
# Header fills that carry white bold text on top (contrast against the fill).
WHITE_TEXT_HEADERS = frozenset({"dark_shaded", "institutional_shaded"})
ROW_ALTERNATING_FILL_HEX = "F2F2F2"
COLUMN_EMPHASIS_FILL_HEX = "D9D9D9"


class CatalogError(ValueError):
    """The catalog file is malformed, incomplete, or not the approved set."""


class UnsupportedContextError(ValueError):
    """No approved, applicable, non-avoided style exists for a context."""

    def __init__(self, context: "TableContext") -> None:
        self.context = context
        super().__init__(
            "No approved table style supports this context "
            f"(purpose={context.purpose!r}, length={context.length!r}, "
            f"density={context.density!r}, columns={context.columns!r}, "
            f"meaning={context.meaning!r}, emphasis={context.emphasis!r}); "
            "stop and choose a teacher/institution override or adjust the table."
        )


@dataclass(frozen=True)
class TableContext:
    """Normalized, backend-independent facts a table style selects from.

    Every enum-valued field below is validated against ``_CONSTRAINT_ENUMS``
    (the applicability/avoidance vocabulary a catalog entry may declare) --
    the inline comments here are a reading aid, not a second source of
    truth; ``_CONSTRAINT_ENUMS``/``TOKEN_ENUMS`` above are authoritative.
    """

    purpose: str  # reference | comparison | status | evidence | dense
    length: str  # short | long
    density: str  # low | medium | high
    columns: int
    rows: int
    pagination: str = "single"  # single | multipage
    emphasis: str = "none"  # none | column
    meaning: str = "none"  # none | comparison | status
    color_policy: str = "color"  # color | grayscale
    accessibility_needs: bool = False
    emphasis_column: int | None = None  # 0-indexed protagonist column for TAB-CE-05


@dataclass(frozen=True)
class StyleDefinition:
    id: str
    label: str
    deprecated: bool
    priority: int
    tokens: dict[str, str]
    applicability: dict[str, Any]
    avoidance: dict[str, Any]
    # False = explicit-override-only: never a candidate for automatic
    # selection, still valid for a teacher/institution override.
    automatic: bool = True


@dataclass(frozen=True)
class StatusIndicator:
    """One approved `[[status:<value>]]` marker: symbol, color, accessible label.

    Never color alone (approved 2026-09-22): the symbol and the label both
    carry the meaning independently of the color, so grayscale or
    colorblind rendering never loses information.
    """

    value: str
    symbol: str
    color: str
    label: str


@dataclass(frozen=True)
class Catalog:
    schema_version: int
    catalog_version: str
    styles: dict[str, StyleDefinition]
    status_indicators: dict[str, StatusIndicator]
    source_path: Path


@dataclass(frozen=True)
class SelectionResult:
    style_id: str
    rationale: str


def _validate_constraints(style_id: str, block_name: str, block: Any, allowed_keys: frozenset[str]) -> dict[str, Any]:
    if not isinstance(block, dict):
        raise CatalogError(f"{style_id}: '{block_name}' must be a mapping")
    unknown = set(block) - allowed_keys
    if unknown:
        raise CatalogError(f"{style_id}: unknown {block_name} keys {sorted(unknown)}")
    for key, value in block.items():
        if key == "max_columns":
            if not isinstance(value, int) or isinstance(value, bool):
                raise CatalogError(f"{style_id}: {block_name}.max_columns must be an int")
            continue
        enum = _CONSTRAINT_ENUMS[key]
        if not isinstance(value, list) or not value:
            raise CatalogError(f"{style_id}: {block_name}.{key} must be a non-empty list")
        invalid = [item for item in value if item not in enum]
        if invalid:
            raise CatalogError(f"{style_id}: {block_name}.{key} has invalid values {invalid}")
    return block


def _validate_style(style_id: str, raw: Any) -> StyleDefinition:
    if not isinstance(raw, dict):
        raise CatalogError(f"{style_id}: style entry must be a mapping")
    unknown = set(raw) - _STYLE_KEYS
    if unknown:
        raise CatalogError(f"{style_id}: unknown keys {sorted(unknown)}")
    missing = _STYLE_KEYS - {"priority", "automatic"} - set(raw)
    if missing:
        raise CatalogError(f"{style_id}: missing required keys {sorted(missing)}")

    label = raw["label"]
    if not isinstance(label, str) or not label.strip():
        raise CatalogError(f"{style_id}: 'label' must be a non-empty string")

    deprecated = raw["deprecated"]
    if not isinstance(deprecated, bool):
        raise CatalogError(f"{style_id}: 'deprecated' must be a bool")

    priority = raw.get("priority", 50)
    if not isinstance(priority, int) or isinstance(priority, bool):
        raise CatalogError(f"{style_id}: 'priority' must be an int")

    automatic = raw.get("automatic", True)
    if not isinstance(automatic, bool):
        raise CatalogError(f"{style_id}: 'automatic' must be a bool")

    tokens = raw["tokens"]
    if not isinstance(tokens, dict):
        raise CatalogError(f"{style_id}: 'tokens' must be a mapping")
    if set(tokens) != REQUIRED_TOKEN_KEYS:
        missing_tokens = REQUIRED_TOKEN_KEYS - set(tokens)
        extra_tokens = set(tokens) - REQUIRED_TOKEN_KEYS
        raise CatalogError(
            f"{style_id}: tokens must define exactly {sorted(REQUIRED_TOKEN_KEYS)} "
            f"(missing {sorted(missing_tokens)}, extra {sorted(extra_tokens)})"
        )
    for key, value in tokens.items():
        if value not in TOKEN_ENUMS[key]:
            raise CatalogError(f"{style_id}: tokens.{key}={value!r} is not one of {sorted(TOKEN_ENUMS[key])}")

    applicability = _validate_constraints(style_id, "applicability", raw["applicability"], _APPLICABILITY_KEYS)
    avoidance = _validate_constraints(style_id, "avoidance", raw["avoidance"], _AVOIDANCE_KEYS)

    return StyleDefinition(
        id=style_id, label=label, deprecated=deprecated, priority=priority,
        tokens=dict(tokens), applicability=dict(applicability), avoidance=dict(avoidance),
        automatic=automatic,
    )


def load_catalog(path: Path | None = None) -> Catalog:
    """Load and strictly validate the versioned table style catalog.

    Reads only the repository-owned YAML file (``path`` or
    ``DEFAULT_CATALOG_PATH``); no private path, no PDF, no network.
    """
    source_path = path or DEFAULT_CATALOG_PATH
    raw = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CatalogError(f"{source_path}: top level must be a mapping")

    unknown = set(raw) - _TOP_LEVEL_KEYS
    if unknown:
        raise CatalogError(f"{source_path}: unknown top-level keys {sorted(unknown)}")
    missing = _TOP_LEVEL_KEYS - set(raw)
    if missing:
        raise CatalogError(f"{source_path}: missing top-level keys {sorted(missing)}")

    schema_version = raw["schema_version"]
    if schema_version != 1:
        raise CatalogError(f"{source_path}: unsupported schema_version {schema_version!r}")

    catalog_version = raw["catalog_version"]
    if not isinstance(catalog_version, str) or not catalog_version.strip():
        raise CatalogError(f"{source_path}: 'catalog_version' must be a non-empty string")

    raw_styles = raw["styles"]
    if not isinstance(raw_styles, dict):
        raise CatalogError(f"{source_path}: 'styles' must be a mapping")
    if set(raw_styles) != APPROVED_STYLE_IDS:
        missing_ids = APPROVED_STYLE_IDS - set(raw_styles)
        extra_ids = set(raw_styles) - APPROVED_STYLE_IDS
        raise CatalogError(
            f"{source_path}: styles must define exactly the approved IDs "
            f"(missing {sorted(missing_ids)}, unapproved {sorted(extra_ids)})"
        )

    styles = {style_id: _validate_style(style_id, body) for style_id, body in raw_styles.items()}
    status_indicators = _validate_status_indicators(source_path, raw["status_indicators"])
    return Catalog(
        schema_version=schema_version, catalog_version=catalog_version,
        styles=styles, status_indicators=status_indicators, source_path=source_path,
    )


_STATUS_INDICATOR_KEYS = frozenset({"symbol", "color", "label"})
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _validate_status_indicators(source_path: Path, raw: Any) -> dict[str, StatusIndicator]:
    """Validate `status_indicators:` -- the approved `[[status:<value>]]` vocabulary.

    Each value must define a distinct symbol, a hex color, and an accessible
    label: the inline-marker authoring convention (approved 2026-09-22)
    never renders color alone, so an incomplete entry blocks the catalog
    load rather than silently degrading to color-only meaning.
    """
    if not isinstance(raw, dict) or not raw:
        raise CatalogError(f"{source_path}: 'status_indicators' must be a non-empty mapping")
    indicators: dict[str, StatusIndicator] = {}
    seen_symbols: set[str] = set()
    for value, body in raw.items():
        if not isinstance(body, dict):
            raise CatalogError(f"status_indicators.{value}: must be a mapping")
        unknown = set(body) - _STATUS_INDICATOR_KEYS
        if unknown:
            raise CatalogError(f"status_indicators.{value}: unknown keys {sorted(unknown)}")
        missing = _STATUS_INDICATOR_KEYS - set(body)
        if missing:
            raise CatalogError(f"status_indicators.{value}: missing keys {sorted(missing)}")
        symbol, color, label = body["symbol"], body["color"], body["label"]
        if not isinstance(symbol, str) or not symbol.strip():
            raise CatalogError(f"status_indicators.{value}: 'symbol' must be a non-empty string")
        if symbol in seen_symbols:
            raise CatalogError(f"status_indicators.{value}: symbol {symbol!r} reused -- color must never be the only signal")
        seen_symbols.add(symbol)
        if not isinstance(color, str) or not _HEX_COLOR_RE.match(color):
            raise CatalogError(f"status_indicators.{value}: 'color' must be a #RRGGBB hex string")
        if not isinstance(label, str) or not label.strip():
            raise CatalogError(f"status_indicators.{value}: 'label' must be a non-empty string")
        indicators[value] = StatusIndicator(value=value, symbol=symbol, color=color, label=label)
    return indicators


def _matches_all(context: TableContext, constraints: dict[str, Any]) -> bool:
    """True when every given applicability constraint holds for ``context``."""
    for key, allowed in constraints.items():
        if key == "max_columns":
            if context.columns > allowed:
                return False
            continue
        value = getattr(context, _CONSTRAINT_FIELD[key])
        if value not in allowed:
            return False
    return True


def _matches_any(context: TableContext, constraints: dict[str, Any]) -> bool:
    """True when any given avoidance constraint matches ``context``."""
    for key, allowed in constraints.items():
        value = getattr(context, _CONSTRAINT_FIELD[key])
        if value in allowed:
            return True
    return False


def eligible_candidates(context: TableContext, catalog: Catalog) -> list[str]:
    """Approved, non-deprecated, automatic style IDs applicable to ``context`` and not avoided.

    Sorted alphabetically — this is the candidate *set*, not the winner;
    ``select_style`` applies the priority tie-break on top of it.
    """
    candidates = []
    for style_id, style in catalog.styles.items():
        if style.deprecated or not style.automatic:
            continue
        if not _matches_all(context, style.applicability):
            continue
        if _matches_any(context, style.avoidance):
            continue
        candidates.append(style_id)
    return sorted(candidates)


def select_style(context: TableContext, catalog: Catalog) -> SelectionResult:
    """Deterministically select one approved style for ``context``.

    Ties among equally-applicable candidates break on each style's explicit
    ``priority`` (lower wins), then alphabetically on ID — both stable and
    auditable, never on insertion order or randomness.
    """
    candidates = eligible_candidates(context, catalog)
    if not candidates:
        raise UnsupportedContextError(context)

    winner_id = min(candidates, key=lambda style_id: (catalog.styles[style_id].priority, style_id))
    winner = catalog.styles[winner_id]
    rationale = (
        f"{winner_id} ({winner.label}) selected: matches purpose={context.purpose!r}, "
        f"length={context.length!r}, density={context.density!r}, columns={context.columns}, "
        f"meaning={context.meaning!r}, emphasis={context.emphasis!r} among candidates "
        f"{candidates}; priority={winner.priority}."
    )
    return SelectionResult(style_id=winner_id, rationale=rationale)

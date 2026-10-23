"""Override precedence and evidence receipts for contextual table styles.

Issue #13, slice 2. This module sits between ``tools/table_styles.py``
(the versioned catalog and the pure automatic selector) and the per-report
configuration (``tools/report_config.py``): it resolves, for one table, the
approved style that actually applies once a teacher override and an
institutional default are taken into account, in that precedence order, and
records the decision as a path-free ``SelectionReceipt``.

Precedence (spec `test_issue_13_override_precedence`):
    teacher override > institution override > automatic selection

Any override that is not one of the approved, non-deprecated IDs, or
that the table's context does not admit, blocks generation instead of being
replaced silently (spec `test_issue_13_invalid_override_rejection`). An
unsupported context with no override at all blocks the same way through
``table_styles.UnsupportedContextError`` (spec
`test_issue_13_unsupported_context_blocks`).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from report_config import ReportConfig
from table_styles import (
    APPROVED_STYLE_IDS,
    Catalog,
    TableContext,
    _matches_all,
    _matches_any,
    select_style,
)


class OverrideRejectedError(ValueError):
    """A teacher/institution override was rejected instead of applied.

    ``reason`` is one of ``"unapproved"``, ``"missing"``, ``"deprecated"``,
    or ``"incompatible with this table's context"`` — the four rejection
    causes spec scenario `test_issue_13_invalid_override_rejection` names.
    """

    def __init__(self, table_key: str, source: str, rejected_id: str, reason: str) -> None:
        self.table_key = table_key
        self.source = source
        self.rejected_id = rejected_id
        self.reason = reason
        super().__init__(
            f"Table '{table_key}': {source} override {rejected_id!r} rejected ({reason}). "
            "Generation blocked — choose an approved, applicable style ID, or "
            "drop the override so the next precedence level decides."
        )


@dataclass(frozen=True)
class TableRequest:
    """One table's resolution input: its key, context, and any overrides."""

    table_key: str
    context: TableContext
    teacher_override: str | None = None
    institution_override: str | None = None


@dataclass(frozen=True)
class SelectionReceipt:
    """Path-free evidence of which style was selected for one table, and why."""

    table_key: str
    style_id: str
    catalog_version: str
    context: TableContext
    precedence_source: str  # "teacher" | "institution" | "automatic"
    rationale: str


def _validate_override(table_key: str, source: str, override_id: str, context: TableContext, catalog: Catalog) -> None:
    if not override_id:
        raise OverrideRejectedError(table_key, source, override_id, "missing (empty style ID)")
    if override_id not in APPROVED_STYLE_IDS or override_id not in catalog.styles:
        raise OverrideRejectedError(table_key, source, override_id, "unapproved (not in the catalog)")
    style = catalog.styles[override_id]
    if style.deprecated:
        raise OverrideRejectedError(table_key, source, override_id, "deprecated")
    # Both applicability (must hold) and avoidance (must not match) decide
    # eligibility for automatic selection (see table_styles.eligible_candidates);
    # an override bypasses automatic selection but not the same context rules
    # -- checking applicability alone let an explicitly avoided style through
    # silently (T1+T2 review R3-override-ignores-avoidance).
    if not _matches_all(context, style.applicability) or _matches_any(context, style.avoidance):
        raise OverrideRejectedError(table_key, source, override_id, "incompatible with this table's context")


@dataclass(frozen=True)
class TableStylesContext:
    """One report's resolved table-style configuration: catalog + overrides.

    Built once per build (``TableStylesContext.from_config``) and threaded
    into a backend renderer's Markdown-to-native pass; ``request_for``
    turns a parsed table's key/context into the ``TableRequest``
    ``resolve_table_style`` needs, applying that report's teacher override
    (per table key) ahead of its institution-wide default.
    """

    catalog: Catalog
    teacher_overrides: dict[str, str]
    institution_override: str | None

    @classmethod
    def from_config(cls, config: ReportConfig, catalog: Catalog | None = None) -> "TableStylesContext":
        from table_styles import load_catalog

        return cls(
            catalog=catalog or load_catalog(),
            teacher_overrides=dict(config.table_style_overrides),
            institution_override=config.institution_table_style,
        )

    def request_for(self, table_key: str, context: TableContext) -> TableRequest:
        return TableRequest(
            table_key=table_key,
            context=context,
            teacher_override=self.teacher_overrides.get(table_key),
            institution_override=self.institution_override,
        )


def resolve_table_style(request: TableRequest, catalog: Catalog) -> SelectionReceipt:
    """Resolve one table's style: teacher override, then institution, then automatic.

    Raises ``OverrideRejectedError`` for an invalid override, or
    ``UnsupportedContextError`` when no override is given and no approved
    style is applicable. Never substitutes a generic fallback.
    """
    for source, override_id in (
        ("teacher", request.teacher_override),
        ("institution", request.institution_override),
    ):
        if override_id is None:
            continue
        _validate_override(request.table_key, source, override_id, request.context, catalog)
        style = catalog.styles[override_id]
        rationale = (
            f"{override_id} ({style.label}) selected by {source} override for table "
            f"'{request.table_key}', overriding automatic contextual selection."
        )
        return SelectionReceipt(
            table_key=request.table_key,
            style_id=override_id,
            catalog_version=catalog.catalog_version,
            context=request.context,
            precedence_source=source,
            rationale=rationale,
        )

    result = select_style(request.context, catalog)
    return SelectionReceipt(
        table_key=request.table_key,
        style_id=result.style_id,
        catalog_version=catalog.catalog_version,
        context=request.context,
        precedence_source="automatic",
        rationale=result.rationale,
    )

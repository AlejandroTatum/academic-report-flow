#!/usr/bin/env python3
"""Shared configuration helpers for university report automation.

Two roots, on purpose
---------------------
``ROOT`` is the CODE root: the checkout that ships templates, logo/background
assets, the Node toolchain and these tools. ``CONTENT_ROOT`` is the CONTENT
root: the tree that holds the actual coursework — ``reports/``,
``academic-sources/``, ``assets/generated/``, ``outputs/``, ``backups/``,
``build/`` and ``visuals/``.

They are separate because they have different lifecycles and different privacy
profiles. The code lives in a shared monorepo: it is versioned, reviewed,
rebuilt (``node_modules``, ``.venv``) and potentially public. The content is
personal academic work: it is private, it is not part of the monorepo history,
it grows per semester and it may live on a different disk or be relocated
entirely. Deriving both from ``Path(__file__).parents[1]`` silently routed every
report, source and rendered figure into the code checkout the moment the code
moved, which is exactly the failure this split prevents.

``CONTENT_ROOT`` is resolved once at import time from ``REPORT_CONTENT_ROOT``
when that environment variable is set, otherwise from ``DEFAULT_CONTENT_ROOT``.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Where the coursework lives when REPORT_CONTENT_ROOT says nothing else.
DEFAULT_CONTENT_ROOT = Path("/home/alejo/devwork/.projects/university/.reports-system/automation")

CONTENT_ROOT_ENV = "REPORT_CONTENT_ROOT"


def resolve_content_root(environ: dict[str, str] | None = None) -> Path:
    """Return the absolute, resolved content root.

    Kept as a function so tests can exercise the environment override without
    reimplementing the precedence rule. Production code should read the
    module-level ``CONTENT_ROOT``, which binds this once at import time.
    """
    env = os.environ if environ is None else environ
    override = (env.get(CONTENT_ROOT_ENV) or "").strip()
    base = Path(override) if override else DEFAULT_CONTENT_ROOT
    return base.expanduser().resolve()


CONTENT_ROOT = resolve_content_root()

# ``output_router`` already imports from this module (``CONTENT_ROOT``,
# ``relative_label``, ``relative_subpath``), so this module cannot import
# ``output_router`` at module scope without a cycle. ``GLOBAL_OUTPUTS`` is
# recomputed here instead of imported — it is one line, not worth moving.
GLOBAL_OUTPUTS = CONTENT_ROOT / "outputs"

DEFAULT_FORMAT = ROOT / "templates" / "academic_format.yml"

LATEX_TYPES = {
    "essay",
    "ensayo",
    "research",
    "investigation",
    "investigacion",
    "informe",
    "report",
    "mixed_report",
    "technical_report",
}
VISUAL_TYPES = {
    "visual",
    "visual_map",
    "mapa_conceptual",
    "concept_map",
    "infographic",
    "infografia",
    "diagram",
    "diagrama",
}
DOCX_TYPES = {"docx", "word", "docx_required", "plantilla_word"}

# Sentinel telling "key absent" apart from a stored None/False value.
MISSING = object()

# Intake placeholders: bracket templates such as `[Nombre del estudiante]` are
# instructions left in a template, not identity. A value that is entirely
# bracketed can never be a real name/title/date, so it fails identity
# validation wherever route or format metadata requires a concrete value.
# Defined here (not in validate_report) so the route checks and the format
# checks share one definition; validate_report re-exports the name.
PLACEHOLDER_RE = re.compile(r"^\[.*\]$")

# Word-style fill-in marks: the teacher's templates leave "X", "XXX" or "00X"
# in fields the student must replace. A value made entirely of X/0 characters
# is one of those marks, never a real name, number or date.
EXAMPLE_VALUE_RE = re.compile(r"^[xX0]+$")


def is_placeholder_value(value: Any) -> bool:
    """True for bracket templates ("[Nombre]") and X/0 fill-in marks ("XXX").

    An empty value is NOT a placeholder: emptiness is reported as "missing",
    placeholders as "example value", and the two messages name different
    corrections.
    """
    text = str(value or "").strip()
    if not text:
        return False
    return PLACEHOLDER_RE.match(text) is not None or EXAMPLE_VALUE_RE.fullmatch(text) is not None

# academic_format.yml sections a single report.yml may relax for itself.
# Deliberately narrow: every other section stays globally owned.
OVERRIDABLE_SECTIONS = frozenset({"cover"})

# ---------------------------------------------------------------------------
# Document routes
# ---------------------------------------------------------------------------
#
# `route:` in report.yml binds a report to one of the five routes defined in
# skills/academic-report-flow/references/routing.md. It is a
# CONTENT classification and is deliberately independent of `type:`/`backend:`
# (LATEX_TYPES/VISUAL_TYPES/DOCX_TYPES above are BACKEND classifications: they
# choose a renderer, they say nothing about whether the document is university
# coursework).
#
# Accepted values — the canonical name, or the route letter used by the
# contract:
#
#     route: academic   (or `a`)  Route A — university academic work
#     route: project    (or `b`)  Route B — project documentation
#     route: business   (or `c`)  Route C — professional/business report
#     route: technical  (or `d`)  Route D — technical document
#     route: other      (or `e`)  Route E — other
#
# Values are compared case-insensitively and trimmed. An absent key means
# Route A, which is what every existing report already relies on. An
# unrecognised value is a hard error: the routing contract is emphatic that
# nothing may fall back silently to the academic route.
ROUTE_KEY = "route"
DEFAULT_ROUTE = "academic"

ROUTE_ALIASES = {
    "a": "academic",
    "b": "project",
    "c": "business",
    "d": "technical",
    "e": "other",
}

PUBLICATION_CATEGORIES = {
    "academic": "Academicos",
    "project": "Proyectos",
    "business": "Profesionales",
    "technical": "Tecnicos",
    "other": "Otros",
}


def resolve_documents_root(documents_root: Path | str | None = None) -> Path:
    """Return the delivery root: ``~/Documents``, or the given test override.

    The delivery tree is neither code (``ROOT``) nor production content
    (``CONTENT_ROOT``): it is the clean, user-owned Documents library whose
    course folders the user may turn into Git repositories. The publisher and
    the status derivation resolve it through this one function so they can
    never disagree about where a delivery lives.
    """
    if documents_root is None:
        return Path.home() / "Documents"
    return Path(documents_root)


def versioned_artifact_pattern(slug: str, suffix: str) -> re.Pattern[str]:
    """Match one document's ``<slug>-vNNN<suffix>`` delivery versions (3+ digits).

    Publisher and status derivation must scan for the same version names, so
    the pattern is built here instead of being rebuilt by each caller.
    """
    return re.compile(rf"^{re.escape(slug)}-v(\d{{3,}})\{suffix}$")


def versioned_pdf_pattern(slug: str) -> re.Pattern[str]:
    """Match one document's ``<slug>-vNNN.pdf`` delivery versions."""
    return versioned_artifact_pattern(slug, ".pdf")


def versioned_bib_pattern(slug: str) -> re.Pattern[str]:
    """Match one document's paired ``<slug>-vNNN.bib`` delivery versions."""
    return versioned_artifact_pattern(slug, ".bib")


def _raw_ascii_slug(value: object) -> str:
    """ASCII slug of ``value``; empty when it holds no ASCII alphanumerics."""
    normalized = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")


def ascii_slug(value: object) -> str:
    """Return a stable filesystem-safe ASCII slug for a confirmed identity."""
    return _raw_ascii_slug(value) or "documento"

# Metadata report.yml must carry, per route. Only Route A may demand the
# academic machinery (`subject`, `teacher`); the other routes are forbidden by
# the contract from auto-including it, so requiring it there forced users to
# invent fake values. Title, author and date stay universal: every document has
# a name, someone who wrote it and a date.
ROUTE_REQUIRED_METADATA: dict[str, tuple[str, ...]] = {
    "academic": ("title", "subject", "teacher", "student", "date"),
    "project": ("title", "student", "date"),
    "business": ("title", "student", "date"),
    "technical": ("title", "student", "date"),
    "other": ("title", "student", "date"),
}

# Metadata that belongs to the academic shell only. Present on another route it
# is a contract smell, not a build failure — hence a warning.
ACADEMIC_ONLY_METADATA = ("subject", "teacher")

# Cover defaults derived from the confirmed route (routing.md): the
# non-academic routes default to no cover, no logo requirement and a body that
# starts on page 1 — exactly what templates/plain-report.tex renders. These are
# DEFAULTS, not a rewrite: an explicit `cover:` block in report.yml overrides
# per key, and an absent (or academic) route keeps reading academic_format.yml
# exactly as every historical report always has. Cover keys not listed here
# (e.g. `full_first_page`, `source_model`) stay globally owned by
# academic_format.yml for every route.
ROUTE_COVER_DEFAULTS: dict[str, dict[str, Any]] = {
    "project": {"required": False, "logo_required": False, "body_starts_on_page": 1},
    "business": {"required": False, "logo_required": False, "body_starts_on_page": 1},
    "technical": {"required": False, "logo_required": False, "body_starts_on_page": 1},
    "other": {"required": False, "logo_required": False, "body_starts_on_page": 1},
}

# Cover defaults derived from the chosen FORMAT (aa-acd-templates S8): the
# `ape`, `aa`, `acd` and `ieee` templates have no cover page, so a report of
# those formats is not asked for one and report.yml does not have to say
# `cover: {required: false}`. The body therefore starts on page 1. The logo
# check is left alone for ape, aa and acd, which print the faculty logo; the
# IEEE essay prints no logo, so it also drops the logo requirement. The format
# is the more specific choice, so it outranks the route default on the keys it
# sets, and an explicit `cover:` block in report.yml outranks both.
FORMAT_COVER_DEFAULTS: dict[str, dict[str, Any]] = {
    "ape": {"required": False, "body_starts_on_page": 1},
    "aa": {"required": False, "body_starts_on_page": 1},
    "acd": {"required": False, "body_starts_on_page": 1},
    "ieee": {"required": False, "body_starts_on_page": 1, "logo_required": False},
}


def unknown_route_message(route: str) -> str:
    """Spanish guidance for a `route:` value no route table recognises."""
    accepted = ", ".join(sorted(ROUTE_REQUIRED_METADATA))
    return (
        f"Ruta de documento desconocida en report.yml: '{route}'. "
        f"Valores aceptados en 'route': {accepted} "
        "(o las letras a, b, c, d, e). Sin 'route' se asume ruta académica."
    )


# ---------------------------------------------------------------------------
# Document formats (new-report-flow)
# ---------------------------------------------------------------------------
#
# `format:` in report.yml is the ONE format choice the user makes per document,
# after content approval. It is a presentation classification, deliberately
# independent of `route:` (the content classification): every format keeps IEEE
# citations (biblatex style=ieee) unless report.yml opts into `citation_style: apa`,
# and always builds a PDF through the existing LaTeX pipeline.
#
#     format: ape     the teacher's Word replica (templates/ape-report.tex)
#     format: aa      the current academic look (unl-report.tex), unchanged
#     format: acd     the "Aprendizaje en Contacto con el Docente" session
#                     record sheet (templates/acd-report.tex)
#     format: ieee    an IEEE conference-style two-column essay, no cover
#                     (templates/ieee-report.tex)
#     format: libre   a user-specified format: `format_spec:` in report.yml is
#                     mandatory, and the plain template applies by default
#
# An absent key means the format has not been chosen yet, which is valid while
# the flow is still content-first. An unrecognised value is a hard error, like
# an unrecognised route: nothing may fall back silently to a look the user did
# not pick.
FORMAT_KEY = "format"
FORMAT_HINT_KEY = "format_hint"
MIN_SOURCES_KEY = "min_sources"
UNCITED_BIBLIOGRAPHY_KEY = "uncited_bibliography"
FIGURE_PLACEMENT_KEY = "figure_placement"
FIGURE_PLACEMENTS = ("float", "here")
CITATION_STYLE_KEY = "citation_style"
CITATION_STYLES = ("ieee", "apa")
DEFAULT_STUDENT = "Alejandro Padilla"

# Metadata report.yml must carry, per chosen format. `aa` demands exactly what
# the academic route already demands; `ape` extends it with the identification
# fields the teacher's table prints; `libre` keeps the universal three plus the
# `format_spec` description (validated separately, since it lives outside
# `metadata:`). English canonical keys; the metadata aliases below accept the
# obvious Spanish spellings.
# APE identification fields a teacher may leave out of the table
# (`ape_omit_fields:` in report.yml); the core academic fields stay required.
APE_OMITTABLE_FIELDS: tuple[str, ...] = (
    "cycle", "unit", "learning_outcome", "practice_number",
    "practice_type", "schedule", "place", "planned_time",
)

FORMAT_REQUIRED_METADATA: dict[str, tuple[str, ...]] = {
    "aa": ("title", "subject", "teacher", "student", "date"),
    "ape": (
        "title", "subject", "teacher", "student", "date",
        "cycle", "unit", "learning_outcome", "practice_number",
        "practice_type", "schedule", "place", "planned_time",
    ),
    # The ACD session block reuses the APE keys where the meaning is the same:
    # `title` is the session topic, `date` the session date and
    # `practice_number` the ACD number. The parallel is data with a default
    # (see `metadata`), so it is not required.
    "acd": (
        "title", "subject", "teacher", "student", "date",
        "cycle", "unit", "learning_outcome", "practice_number",
        "schedule", "place", "planned_time",
    ),
    "libre": ("title", "student", "date"),
    # The IEEE essay prints the title and an author block; `date` is required
    # like in every format but is not typeset, and the optional `affiliation`
    # and `email` are printed only when report.yml sets them.
    "ieee": ("title", "student", "date"),
}


def unknown_format_message(format_value: str) -> str:
    """Spanish guidance for a `format:` value no format table recognises."""
    accepted = ", ".join(sorted(FORMAT_REQUIRED_METADATA))
    return (
        f"Formato de documento desconocido en report.yml: '{format_value}'. "
        f"Valores aceptados en 'format': {accepted}. "
        "Sin 'format' el documento aún no tiene formato elegido "
        "(válido durante las fases de contenido)."
    )


# ---------------------------------------------------------------------------
# Final-output layout rule
# ---------------------------------------------------------------------------

LOCAL_OUTPUTS_ERROR = (
    "No guardar resultados finales en reports/<trabajo>/outputs/: "
    "usar solamente outputs/<materia>/ para evitar duplicados"
)


def targets_local_outputs(config: "ReportConfig") -> bool:
    """True when the configured final PDF lands in ``<report folder>/outputs/``.

    The rule has no exemptions, and this is the single predicate behind it: the
    load-time guard in ``load_report_config`` and the post-build check in
    ``validate_report`` both ask this function, so the two can never disagree
    about the same report.

    Folders named with a leading ``_`` used to be exempt, on the grounds that an
    example report kept its output next to itself. That justification named
    ``_example_latex_essay``, which is not versioned here — it lives in the
    private content tree — so a validation rule carved out an exception for a
    file no reader of this repository can open. It never needed the exception
    either: it writes its final PDF to ``build/``. The example that IS shipped
    here, ``examples/ejemplo_informe_academico``, satisfies this rule outright,
    which is the point of shipping it — the pattern people copy is the pattern
    the validator enforces.

    The ``_`` prefix keeps its one genuine meaning in ``publish_global``:
    scratch work, no global copy. That is a publication decision. Where the
    final file may be written is a layout decision. Reading one prefix as both
    meant that marking a report as scratch silently switched off a layout rule
    nobody asked to switch off.
    """
    if config.output_format != "pdf":
        return False
    return (config.folder / "outputs").resolve() in config.pdf_path.resolve().parents


def dig(source: Any, keys: tuple[str, ...]) -> Any:
    """Walk nested mappings, returning MISSING when any key is absent."""
    cursor: Any = source
    for key in keys:
        if not isinstance(cursor, dict) or key not in cursor:
            return MISSING
        cursor = cursor[key]
    return cursor


def strict_bool(value: Any, field: str) -> bool:
    """Accept only YAML booleans; never coerce strings or numeric values."""
    if type(value) is not bool:
        raise ValueError(f"{field} debe ser un booleano YAML (true o false)")
    return value


@dataclass
class ReportConfig:
    folder: Path
    raw: dict[str, Any]
    academic_format: dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> str:
        return str(self.raw.get("type") or self.raw.get("tipo") or "essay").strip().lower()

    @property
    def route(self) -> str:
        """Canonical document route for this report.

        Returns the canonical name (``academic``, ``project``, ``business``,
        ``technical``, ``other``) for a recognised value, ``DEFAULT_ROUTE``
        when the key is absent, and the written value verbatim when it is not
        recognised — so the caller can name it in the error instead of
        guessing a route on the user's behalf.
        """
        written = str(self.raw.get(ROUTE_KEY) or "").strip().lower()
        if not written:
            return DEFAULT_ROUTE
        return ROUTE_ALIASES.get(written, written)

    @property
    def route_is_known(self) -> bool:
        return self.route in ROUTE_REQUIRED_METADATA

    @property
    def required_metadata(self) -> tuple[str, ...]:
        """Metadata keys this report's route genuinely needs.

        Raises ValueError for an unrecognised route: there is no defensible
        default here, and silently answering with the academic set is exactly
        the fallback the routing contract forbids. Callers check
        ``route_is_known`` first and report ``unknown_route_message``.
        """
        if not self.route_is_known:
            raise ValueError(unknown_route_message(self.route))
        return ROUTE_REQUIRED_METADATA[self.route]

    @property
    def format(self) -> str | None:
        """Canonical document format (``ape``, ``aa``, ``acd``, ``ieee`` or ``libre``).

        Returns ``None`` when the key is absent: the format has not been
        chosen yet, which is valid while the flow is still content-first.
        An unrecognised value is returned verbatim so callers can name it in
        the error instead of guessing a format on the user's behalf — the
        same contract as ``route``.
        """
        written = str(self.raw.get(FORMAT_KEY) or "").strip().lower()
        return written or None

    @property
    def format_is_known(self) -> bool:
        return self.format in FORMAT_REQUIRED_METADATA

    @property
    def format_hint(self) -> str | None:
        written = str(self.raw.get(FORMAT_HINT_KEY) or "").strip().lower()
        return written or None

    @property
    def format_hint_is_known(self) -> bool:
        return self.format_hint in FORMAT_REQUIRED_METADATA

    @property
    def format_spec(self) -> str:
        """The user's free-form format description (`format_spec:`), for libre."""
        return str(self.raw.get("format_spec") or "").strip()

    @property
    def format_required_metadata(self) -> tuple[str, ...]:
        """Metadata keys this report's chosen format genuinely needs.

        Raises ValueError for an unrecognised format, exactly like
        ``required_metadata`` does for an unrecognised route.
        """
        chosen = self.format
        if chosen not in FORMAT_REQUIRED_METADATA:
            raise ValueError(unknown_format_message(chosen or ""))
        required = FORMAT_REQUIRED_METADATA[chosen]
        if chosen == "ape":
            omitted = set(self.ape_omit_fields)
            required = tuple(key for key in required if key not in omitted)
        return required

    @property
    def ape_omit_fields(self) -> tuple[str, ...]:
        """APE identification fields the teacher left out (`ape_omit_fields:`).

        Only keys in ``APE_OMITTABLE_FIELDS`` count; anything else is reported
        by the APE structure validation and ignored here.
        """
        value = self.raw.get("ape_omit_fields") or []
        if not isinstance(value, list):
            return ()
        return tuple(key for key in value if key in APE_OMITTABLE_FIELDS)

    @property
    def min_sources(self) -> int | None:
        """Per-report academic source minimum (``min_sources:``), or ``None``.

        ``None`` means the key is absent and the shared default applies (see
        ``source_count.effective_min_sources``). Only an integer is accepted --
        booleans, strings, floats, null and negatives raise ValueError rather
        than silently falling back to the default. ``0`` (no bibliography) is
        allowed only on a known non-academic route; the academic route keeps a
        minimum of at least 1.
        """
        if MIN_SOURCES_KEY not in self.raw:
            return None
        value = self.raw[MIN_SOURCES_KEY]
        if type(value) is int and value == 0:
            if self.route_is_known and self.route != DEFAULT_ROUTE:
                return 0
            raise ValueError(
                f"{MIN_SOURCES_KEY}: 0 solo se permite fuera de la ruta academic; "
                "la ruta academic exige al menos 1 fuente en report.yml"
            )
        if type(value) is not int or value < 1:
            raise ValueError(
                f"{MIN_SOURCES_KEY} debe ser un entero positivo en report.yml (recibido: {value!r})"
            )
        return value

    @property
    def figure_placement(self) -> str:
        """Where figures sit: ``float`` (default, LaTeX decides) or ``here``.

        ``here`` pins each figure right after the text that introduces it.
        Any other value raises ValueError.
        """
        value = self.raw.get(FIGURE_PLACEMENT_KEY, "float")
        if not isinstance(value, str) or value not in FIGURE_PLACEMENTS:
            raise ValueError(
                f"{FIGURE_PLACEMENT_KEY} debe ser uno de {', '.join(FIGURE_PLACEMENTS)} "
                f"en report.yml (recibido: {value!r})"
            )
        return value

    @property
    def citation_style(self) -> str:
        """Citation style: ``ieee`` (default) or ``apa`` (opt-in, any route).

        Any other value raises ValueError.
        """
        value = self.raw.get(CITATION_STYLE_KEY, "ieee")
        if not isinstance(value, str) or value not in CITATION_STYLES:
            raise ValueError(
                f"{CITATION_STYLE_KEY} debe ser uno de {', '.join(CITATION_STYLES)} "
                f"en report.yml (recibido: {value!r})"
            )
        return value

    @property
    def uncited_bibliography(self) -> bool:
        """Whether the report prints its bibliography without in-text citations.

        Strict boolean in report.yml (``uncited_bibliography: true``), default
        ``False``. The opt-in is explicit and narrow: academic route only, a
        bibliography file must exist (every entry in it is printed), and it is
        mutually exclusive with ``min_sources``. Violations raise ValueError.
        """
        enabled = strict_bool(self.raw.get(UNCITED_BIBLIOGRAPHY_KEY, False), UNCITED_BIBLIOGRAPHY_KEY)
        if not enabled:
            return False
        if self.route != DEFAULT_ROUTE:
            raise ValueError(f"{UNCITED_BIBLIOGRAPHY_KEY}: solo se permite en la ruta academic")
        if MIN_SOURCES_KEY in self.raw:
            raise ValueError(f"{UNCITED_BIBLIOGRAPHY_KEY}: no se puede combinar con {MIN_SOURCES_KEY}")
        if self.bib_path is None:
            raise ValueError(
                f"{UNCITED_BIBLIOGRAPHY_KEY}: la bibliografía declarada no existe; "
                "crea el archivo .bib que se imprimirá completo"
            )
        return True

    @property
    def backend(self) -> str:
        backend = str(self.raw.get("backend") or "auto").strip().lower()
        if backend != "auto":
            return backend
        if self.type in VISUAL_TYPES:
            return "visual"
        if self.type in DOCX_TYPES or str(self.raw.get("output", "")).lower() == "docx":
            return "docx"
        return "latex"

    @property
    def output_format(self) -> str:
        return str(self.raw.get("output") or "pdf").strip().lower()

    @property
    def publish_global(self) -> bool:
        """Whether a copy of the final file belongs in ``outputs/<materia>/``.

        A leading ``_`` in the folder name is the default answer for scratch
        work — drafts and experiments are not deliverables, so they are not
        published. That is the prefix's only meaning: it says nothing about
        where the final file may be written, which is
        ``targets_local_outputs``' business. Writing ``publish_global:`` in
        report.yml overrides the guess in either direction, and a report whose
        ``pdf:`` already points into ``outputs/<materia>/`` normally sets it to
        false so the deliverable is not copied on top of itself.
        """
        if "publish_global" in self.raw:
            return strict_bool(self.raw["publish_global"], "publish_global")
        return not self.folder.name.startswith("_")

    @property
    def publication_category(self) -> str:
        """Documents category derived only from the confirmed route."""
        return PUBLICATION_CATEGORIES[self.route]

    @property
    def document_slug(self) -> str:
        """Stable ASCII identity derived from the confirmed report title."""
        return ascii_slug(self.metadata.get("title") or self.folder.name)

    @property
    def delivery_subject_slug(self) -> str | None:
        """Subject slug that scopes academic delivery, or ``None``.

        Only the academic route carries a delivery subject level, and a
        confirmed subject always yields one: the canonical alias when
        ``output_router.subject_slug`` knows it, otherwise the subject's own
        stable ASCII slug (``ascii_slug``), so a newly named course gets its
        own delivery folder without being registered anywhere. ``None`` only
        when there is no confirmed subject at all — the academic route's own
        validation refuses that before delivery, and no generic fallback
        bucket is invented. Imported lazily to avoid the ``output_router``
        import cycle.
        """
        if self.route != DEFAULT_ROUTE:
            return None
        subject = self.metadata.get("subject")
        if not subject:
            return None
        from output_router import subject_slug

        return subject_slug(subject) or ascii_slug(subject)

    def delivery_relative_folder(self) -> Path:
        """This report's delivery folder, relative to the Documents root.

        Academic route with a confirmed subject:
        ``<Academicos>/<subject-slug>/<document-slug>/`` — canonical alias
        when the shared vocabulary knows the subject, otherwise the subject's
        stable ASCII slug. Every other case -- non-academic categories, or an
        academic report without a confirmed subject -- keeps the flat
        ``<category>/<document-slug>/`` layout that legacy deliveries use.

        Publisher and status derivation must both ask this method instead of
        rebuilding the path, or the deliver phase could look somewhere other
        than where publication actually wrote.
        """
        slug = self.document_slug
        subject = self.delivery_subject_slug
        if subject:
            return Path(self.publication_category) / subject / slug
        return Path(self.publication_category) / slug

    @property
    def delivery_dir(self) -> Path | None:
        """The ``delivery_dir:`` override from report.yml, or ``None`` when unset.

        A non-empty string; ``~`` is expanded and a relative path resolves
        against the report folder. Any other value is a configuration error,
        like the other strict keys. The override only moves the destination:
        the version register, hashing and locking are the publisher's.
        """
        if "delivery_dir" not in self.raw:
            return None
        value = self.raw["delivery_dir"]
        if not isinstance(value, str) or not value.strip():
            raise ValueError("delivery_dir debe ser una ruta de texto no vacía")
        path = Path(value.strip()).expanduser()
        if not path.is_absolute():
            path = self.folder / path
        return Path(os.path.normpath(path))

    def delivery_folder(self, documents_root: Path | str | None = None) -> Path:
        """Absolute delivery folder for this report's final PDF.

        ``delivery_dir`` wins when set; otherwise the shared Documents layout.
        """
        override = self.delivery_dir
        if override is not None:
            return override
        return resolve_documents_root(documents_root) / self.delivery_relative_folder()

    @property
    def body_path(self) -> Path:
        """The body the builders and validators render.

        An explicit ``body:`` wins. Otherwise a ``body.typeset.md`` whose
        ``typeset.yml`` binding matches the current ``body.md`` (issue #96: the
        formatted copy of the approved plain text), else ``body.md``.
        """
        value = self.raw.get("body")
        if value:
            return resolve_in_folder(self.folder, value)
        if typeset_binding_current(self.folder):
            return self.folder / TYPESET_BODY_NAME
        return resolve_in_folder(self.folder, "body.md")

    @property
    def bib_path(self) -> Path | None:
        value = self.raw.get("bibliography") or self.raw.get("bib") or "sources.bib"
        path = resolve_in_folder(self.folder, value)
        return path if path.exists() else None

    @property
    def deliver_bibliography(self) -> bool:
        """Whether the user explicitly declared the bibliography a deliverable.

        Strict boolean in report.yml (``deliver_bibliography: true``), default
        ``False``: a ``sources.bib`` existing for citations never travels on
        its own. Any other YAML type is a configuration error, exactly like
        the other strict booleans.
        """
        return strict_bool(self.raw.get("deliver_bibliography", False), "deliver_bibliography")

    def delivery_bibliography(self) -> Path | None:
        """The declared `.bib` to deliver, validated; ``None`` when not opted in.

        The refusal rule is fail-closed: when the option is enabled, the source
        must exist as a regular ``.bib`` file inside the report work folder
        (traversal, absolute paths and symlink escapes refuse), be non-empty,
        and parse as BibTeX with the project's own minimal parser. Anything
        else raises ``ValueError`` naming the refusal — before any delivery
        gate or destination is touched. No DOI or citation-style policy is
        imposed here: exporting the declared bytes is not a re-review.
        """
        if not self.deliver_bibliography:
            return None
        declared = self.raw.get("bibliography") or self.raw.get("bib") or "sources.bib"
        path = resolve_in_folder(self.folder, declared)
        folder = self.folder.resolve()
        if not path.is_file():
            raise ValueError(
                f"deliver_bibliography: la bibliografía declarada no existe o no es un "
                f"archivo regular: {path}"
            )
        if path.suffix.lower() != ".bib":
            raise ValueError(
                f"deliver_bibliography: la bibliografía declarada debe ser un "
                f"archivo .bib: {path}"
            )
        if not path.resolve().is_relative_to(folder):
            raise ValueError(
                f"deliver_bibliography: la bibliografía declarada debe vivir dentro "
                f"de la carpeta del reporte: {path}"
            )
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(
                f"deliver_bibliography: la bibliografía declarada no se pudo leer: {path}: {exc}"
            ) from exc
        if not text.strip():
            raise ValueError(
                f"deliver_bibliography: la bibliografía declarada está vacía: {path}"
            )
        # The same minimal parser the DOCX renderer uses; no new dependency.
        from build_docx_report import parse_bib

        if not parse_bib(text):
            raise ValueError(
                f"deliver_bibliography: la bibliografía declarada no tiene entradas "
                f"BibTeX válidas: {path}"
            )
        return path

    @property
    def tex_path(self) -> Path:
        value = self.raw.get("tex") or "build/main.tex"
        return resolve_in_folder(self.folder, value)

    @property
    def output_folder_slug(self) -> str:
        """Output subfolder for the derived default final path.

        ``outputs/<materia>/`` when metadata names a subject ``output_router``
        recognises (the academic route's own vocabulary), otherwise
        ``outputs/<route category>/`` derived from the confirmed route. Only
        consulted when a report leaves ``pdf:``/``docx:`` unset; an explicit
        path never asks this question.

        Imported lazily to avoid a cycle: ``output_router`` already imports
        ``CONTENT_ROOT`` from this module at its own module scope.
        """
        from output_router import subject_slug

        slug = subject_slug(self.metadata.get("subject"))
        return slug or ascii_slug(self.publication_category)

    @property
    def work_folder_slug(self) -> str:
        """Unique name of the default working build file.

        Keyed by the work folder, not the title: two folders whose titles share
        a slug must not overwrite each other's build. A folder name with no
        ASCII content falls back to the title slug. The delivery file name
        stays ``document_slug``-based.
        """
        name = self.folder.resolve().name
        return _raw_ascii_slug(name) or self.document_slug

    def _default_build_path(self, suffix: str) -> Path:
        """Default build file; keeps a legacy ``<title-slug>`` build that exists."""
        directory = GLOBAL_OUTPUTS / self.output_folder_slug
        current = directory / f"{self.work_folder_slug}{suffix}"
        legacy = directory / f"{self.document_slug}{suffix}"
        if not current.exists() and legacy.exists():
            return legacy
        return current

    @property
    def pdf_path(self) -> Path:
        value = self.raw.get("pdf") or self.raw.get("output_pdf")
        if value:
            return resolve_in_folder(self.folder, value)
        return self._default_build_path(".pdf")

    @property
    def docx_path(self) -> Path:
        value = self.raw.get("docx") or self.raw.get("output_docx")
        if value:
            return resolve_in_folder(self.folder, value)
        return self._default_build_path(".docx")

    @property
    def log_path(self) -> Path:
        value = self.raw.get("latex_log") or "build/main.log"
        return resolve_in_folder(self.folder, value)

    @property
    def quality_report_path(self) -> Path:
        value = self.raw.get("quality_report") or "backups/quality_report.md"
        return resolve_in_folder(self.folder, value)

    @property
    def table_style_receipts_path(self) -> Path:
        """Path-free, machine-readable ``SelectionReceipt`` evidence (issue #13).

        Written by ``tools/validate_report.py`` beside ``quality_report.md``
        for every table a directive resolved, so "the selected ID and
        rationale appear in validation evidence" holds for every backend
        that applies styles (T5's disclosed "What remains" gap).
        """
        return resolve_in_folder(self.folder, "backups/table_style_receipts.json")

    @property
    def metadata(self) -> dict[str, Any]:
        meta = dict(self.raw.get("metadata") or {})
        aliases = {
            "title": ["title", "titulo", "tema"],
            "subject": ["subject", "asignatura"],
            "teacher": ["teacher", "docente"],
            # Non-academic routes name the same field "author"; it is the same
            # person, so it resolves to the same canonical key.
            "student": ["student", "estudiante", "nombre", "author", "autor"],
            "date": ["date", "fecha"],
            "career": ["career", "carrera"],
            "parallel": ["parallel", "paralelo"],
            "members": ["members", "integrantes", "miembros"],
            # APE identification-table fields (new-report-flow): canonical
            # English keys, with the obvious Spanish spellings the report.yml
            # of a Spanish-language course naturally uses.
            "cycle": ["cycle", "ciclo"],
            "unit": ["unit", "unidad"],
            "learning_outcome": [
                "learning_outcome", "resultado_aprendizaje", "resultado_de_aprendizaje",
            ],
            "practice_number": [
                "practice_number", "practica_numero", "practica_nro",
                "numero_de_practica", "numero_practica",
            ],
            "practice_type": ["practice_type", "tipo_practica", "practica_tipo", "tipo"],
            "schedule": ["schedule", "horario"],
            "place": ["place", "lugar"],
            "planned_time": [
                "planned_time", "tiempo_planificado", "tiempo_planificado_en_el_silabo",
            ],
            # IEEE essay author block: optional, printed only when present.
            "affiliation": ["affiliation", "afiliacion", "afiliación"],
            "email": ["email", "correo", "correo_electronico", "correo_electrónico"],
        }
        for canonical, keys in aliases.items():
            if canonical in meta and meta[canonical]:
                continue
            for key in keys:
                value = meta.get(key) or self.raw.get(key)
                if value:
                    meta[canonical] = value
                    break
        # Paralelo is data, not a question (#8): the intake never asks for it,
        # renderers default to A, and an explicit assignment value in report.yml
        # (metadata.parallel/metadata.paralelo) overrides the default.
        meta.setdefault("parallel", "A")
        return meta

    @property
    def validators(self) -> dict[str, bool]:
        configured_value = self.raw.get("validators", {})
        if not isinstance(configured_value, dict):
            raise ValueError("validators debe ser un mapa de booleanos YAML")
        configured = dict(configured_value)
        validators = {
            "common": True,
            "ieee": True,
            "pdf_layout": self.output_format == "pdf" or self.pdf_path.exists(),
            "latex": self.backend == "latex",
            "latex_log": self.backend == "latex",
            "visual": self.backend == "visual" or self.type in VISUAL_TYPES,
            "visual_pdf": False,  # opt-in via report.yml: validators: {visual_pdf: true}
            "docx": self.backend == "docx" or self.output_format == "docx",
        }
        for key, value in configured.items():
            name = str(key)
            if name not in validators:
                continue
            enabled = strict_bool(value, f"validators.{name}")
            if name == "common" and not enabled:
                raise ValueError("validators.common es obligatorio y no puede desactivarse")
            if name == "pdf_layout" and self.output_format == "pdf" and not enabled:
                raise ValueError("validators.pdf_layout es obligatorio para salida PDF")
            validators[name] = enabled
        return validators

    @property
    def table_styles_enabled(self) -> bool:
        """Opt-in switch for issue #13 contextual table styles.

        Declared as ``table_styles: {enabled: true}`` in report.yml.
        Defaults to ``False``, which keeps every existing report's LaTeX,
        DOCX and HTML output byte-for-byte unchanged: opting in is what
        activates directive-driven per-table style selection (and, once
        opted in, requires every table to declare a directive -- see
        ``tools/table_directives.py``).
        """
        value = dig(self.raw, ("table_styles", "enabled"))
        if value is MISSING:
            return False
        return strict_bool(value, "table_styles.enabled")

    @property
    def table_style_overrides(self) -> dict[str, str]:
        """Teacher per-table style overrides: ``table_key -> approved style ID``.

        Declared as ``table_styles: {overrides: {<table_key>: <ID>}}`` in
        report.yml (issue #13). A teacher override always wins over the
        institutional default (``institution_table_style``) and over
        automatic contextual selection — see
        ``tools/table_model.py::resolve_table_style``.
        """
        overrides = dig(self.raw, ("table_styles", "overrides"))
        return dict(overrides) if isinstance(overrides, dict) else {}

    @property
    def institution_table_style(self) -> str | None:
        """Institution-wide default table style ID, or ``None`` when unset.

        Read only from ``tables.institution_override`` in
        academic_format.yml — deliberately not in ``OVERRIDABLE_SECTIONS``,
        since a per-report override of the institutional default belongs
        under ``table_style_overrides`` (explicit per table key), not a
        blanket ``report.yml`` relaxation.
        """
        value = self.academic_value("tables", "institution_override")
        return str(value) if value else None

    def academic_value(self, *keys: str, default: Any = None) -> Any:
        """Resolve a format value: report.yml -> academic_format.yml -> default.

        A report may relax a global rule for itself only (e.g. `cover:
        {required: false}` for a non-institutional deliverable). The override is
        resolved per key, so a partial block never shadows the rest of its
        section in academic_format.yml.

        Only sections in OVERRIDABLE_SECTIONS may be overridden. Top-level
        report.yml keys share a namespace with academic_format.yml sections, and
        several names already collide by accident: 31 reports carry a
        `validators:` block, and 15 carry a list-shaped `figures:` key. Without
        the allowlist those would silently shadow the format defaults the day
        someone reads them through this method.
        """
        if keys and keys[0] in OVERRIDABLE_SECTIONS and isinstance(self.raw.get(keys[0]), dict):
            override = dig(self.raw, keys)
            if override is not MISSING:
                return override
        value = dig(self.academic_format, keys)
        return default if value is MISSING else value

    def cover_value(self, key: str, default: Any = None) -> Any:
        """Resolve a cover value: report.yml -> format/route default -> academic_format.yml.

        The precedence here is the heart of the route contract: an explicit
        `cover:` block in report.yml always wins (per key, so a partial block
        never shadows the rest), a coverless format (``FORMAT_COVER_DEFAULTS``)
        or a non-academic route derives its default from its table, the format
        outranking the route, and anything else falls through to the global
        academic_format.yml values — which is what every route-omitted report
        has always read, including its own `cover:` relaxation.
        """
        explicit = self.raw.get("cover")
        if isinstance(explicit, dict) and key in explicit:
            return explicit[key]
        derived = {
            **ROUTE_COVER_DEFAULTS.get(self.route, {}),
            **FORMAT_COVER_DEFAULTS.get(self.format or "", {}),
        }
        if key in derived:
            value = derived[key]
            if key != "required" and not self.cover_value("required", default=True):
                return value
            # Dependent coherence: an explicitly required cover carries the
            # validation expectations that make "required" meaningful — the
            # body cannot start on page 1 (the validator would compare the
            # cover page with itself) and the cover needs its logo. Each stays
            # explicitly overridable key by key.
            if key == "body_starts_on_page" and value != 2:
                return 2
            if key == "logo_required" and not value:
                return True
            return value
        return self.academic_value("cover", key, default=default)

    @classmethod
    def load(cls, folder: Path) -> "ReportConfig":
        """Load a report folder's configuration (alias of load_report_config)."""
        return load_report_config(folder)


def relative_label(path: Path, base: Path) -> str:
    """Return ``path`` relative to ``base`` for logs, never raising.

    ``Path.relative_to`` raises ValueError for anything outside ``base``. Now
    that reports may live anywhere on disk, that turned every log line into a
    potential crash. A log message must never kill a build, so a path outside
    ``base`` degrades to its absolute form.
    """
    for candidate, root in ((path, base), (path.resolve(), base.resolve())):
        try:
            return str(candidate.relative_to(root))
        except ValueError:
            continue
    return str(path)


def relative_subpath(path: Path, base: Path) -> Path:
    """Return a RELATIVE path for ``path`` under ``base``, never raising.

    Used when the result is joined onto another directory (a backup mirror, for
    instance). Falling back to the absolute path would be actively harmful
    there — ``Path("/backup") / Path("/etc/x")`` is ``/etc/x`` — so anything
    outside ``base`` degrades to its basename instead.
    """
    for candidate, root in ((path, base), (path.resolve(), base.resolve())):
        try:
            return candidate.relative_to(root)
        except ValueError:
            continue
    return Path(path.name)


def resolve_in_folder(folder: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else folder / path


TYPESET_BODY_NAME = "body.typeset.md"
TYPESET_BINDING_NAME = "typeset.yml"


def typeset_binding_current(folder: Path) -> bool:
    """True when ``body.typeset.md`` exists and ``typeset.yml`` binds the current ``body.md``.

    Read-only and fail-closed: any missing, unreadable or malformed file is
    ``False``, so the build falls back to ``body.md``.
    """
    import hashlib

    folder = Path(folder)
    try:
        if not (folder / TYPESET_BODY_NAME).is_file():
            return False
        recorded = str(read_yaml(folder / TYPESET_BINDING_NAME).get("body_sha256") or "").strip().lower()
        if not recorded:
            return False
        return recorded == hashlib.sha256((folder / "body.md").read_bytes()).hexdigest()
    except Exception:
        return False


def read_yaml(path: Path) -> dict[str, Any]:
    # Imported lazily so that importing this module (and therefore CONTENT_ROOT)
    # stays dependency-free: source_library.py deliberately runs without PyYAML.
    import yaml

    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def load_report_config(folder: Path) -> ReportConfig:
    """Load and sanity-check a report folder's configuration.

    Two rules are enforced here rather than after the build, because both are
    knowable from report.yml alone and both otherwise cost the user three
    LuaLaTeX passes before they hear about it:

    * an unrecognised ``route:`` value (no silent fallback to Route A);
    * a final PDF pointed at ``reports/<work>/outputs/``.

    The output rule only fires for a path the report actually declares. A
    report that never wrote ``pdf:`` has nothing to correct in its own file;
    the post-build check in ``validate_report`` still covers that case.
    """
    folder = folder.resolve()
    report_yml = folder / "report.yml"
    if not report_yml.exists():
        raise SystemExit(f"No existe report.yml en {folder}")
    raw = read_yaml(report_yml)
    academic = read_yaml(DEFAULT_FORMAT)
    config = ReportConfig(folder=folder, raw=raw, academic_format=academic)

    if not config.route_is_known:
        raise SystemExit(unknown_route_message(config.route))
    if FORMAT_KEY in raw and not config.format_is_known:
        raise SystemExit(unknown_format_message(config.format or ""))
    if FORMAT_HINT_KEY in raw and not config.format_hint_is_known:
        raise SystemExit(unknown_format_message(config.format_hint or "").replace("'format'", "'format_hint'"))

    declares_final_pdf = any(key in raw for key in ("pdf", "output_pdf"))
    if declares_final_pdf and targets_local_outputs(config):
        raise SystemExit(f"{LOCAL_OUTPUTS_ERROR}\nRuta configurada: {config.pdf_path}")
    try:
        _ = config.publish_global
        _ = config.validators
        _ = config.deliver_bibliography
        _ = config.min_sources
        _ = config.uncited_bibliography
        _ = config.figure_placement
        _ = config.citation_style
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    return config


def latex_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)

#!/usr/bin/env python3
"""Extract only explicitly stated facts from a teacher's guide.

``extract_guide_inventory`` is the heuristic sibling: a numbered list (``G1``,
``G2``...) of the sentences that read as a demand. Three kinds, first match wins:
``question`` (``¿...?``), ``deliverable`` (the sentence names something to hand
in: entregable, adjuntar, enlace, captura...) and ``mandate`` (it opens with a
mandate verb such as ``Elabore``/``Compare``/``Justificar``, or carries a modal
cue such as ``debe``/``se solicita``). It over-detects on purpose (a rubric
waives an item with a reasoned ``not_applicable:`` entry) and under-detects
(it never replaces reading the guide), and it is kept apart from
``extract_guide_facts`` so the explicit facts stay exactly as they were.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path


def extract_guide_facts(text: str) -> dict:
    """Return explicit guide facts without interpreting missing information."""
    try:
        normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
        facts: dict = {}
        conflicts: dict[str, list[str]] = {}

        def record(key: str, values: list[str]) -> None:
            unique = list(dict.fromkeys(values))
            if len(unique) > 1:
                conflicts[key] = unique
            elif unique:
                facts[key] = unique[0]

        record("family", [value for pattern, value in (
            (r"\bape\b|\bpractico[\s-]+experimental(?:es)?\b", "ape"),
            (r"\baprendizaje\s+autonomo\b", "aa"),
        ) if re.search(pattern, normalized)])
        record("practice_number", [value.lstrip("0") or "0" for value in re.findall(
            r"\b(?:semana|practica)\s+(?:nro\.?\s*)?(\d+)\b", normalized)])
        record("practice_type", [value for pattern, value in (
            (r"\bindividual\b", "Individual"),
            (r"\bgrupal\b|\ben\s+grupo\b", "Grupal"),
        ) if re.search(pattern, normalized)])
        record("planned_time", [f"{value} horas" for value in re.findall(
            r"\btiempo\s+planificado(?:\s+en\s+el\s+silabo)?\s*:?\s*(\d+)(?:\s+horas)?\b", normalized)])
        if conflicts:
            facts["conflicts"] = conflicts
        return facts
    except (TypeError, ValueError, UnicodeError):
        return {}


_MANDATE_VERBS = (
    "analice analizar argumente argumentar calcule calcular compare comparar complete completar configure "
    "configurar construya construir cree crear defina definir describa describir desarrolle desarrollar "
    "disene disenar documente documentar elabore elaborar enumere enumerar escriba escribir explique explicar "
    "grafique graficar identifique identificar implemente implementar indique indicar investigue investigar "
    "justifique justificar liste listar muestre mostrar plantee plantear presente presentar proponga proponer "
    "realice realizar redacte redactar registre registrar resuelva resolver responda responder resuma resumir "
    "sintetice sintetizar simule simular sustente sustentar utilice utilizar verifique verificar"
).split()
_MARKER = re.compile(r"^\s*(?:\d+[.)]|[a-z][.)]|[-*•\u2022])\s+", re.IGNORECASE)
_STARTS_UNIT = re.compile(r"^\s*(?:\d+[.)]|[a-z][.)]|[-*•\u2022])\s+|^\s*¿")
_LEADING_VERB = re.compile(r"^(?:(?:el|la)\s+estudiante\s+)?(?:" + "|".join(_MANDATE_VERBS) + r")\b")
_MODAL = re.compile(r"\b(?:debe|deben|debera|deberan|se\s+pide|se\s+solicita|se\s+requiere|es\s+obligatori[oa])\b")
_DELIVERABLE = re.compile(
    r"\b(?:entregables?|productos?\s+esperados?|entregar|entregue|entregara|adjunt\w+|enlaces?|links?|capturas?)\b")
_MIN_WORDS = 3
_MAX_TEXT = 240


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _units(text: str) -> list[str]:
    """Join wrapped lines: a new unit starts at a bullet/number marker or after a sentence end."""
    units: list[str] = []
    ended = True
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            ended = True
            continue
        if units and not ended and not _STARTS_UNIT.match(raw):
            units[-1] += " " + line
        else:
            units.append(line)
        ended = line.endswith((".", ":", ";", "?", "!"))
    return units


def _kind(sentence: str) -> str | None:
    folded = _fold(_MARKER.sub("", sentence)).lstrip("¿ ")
    if sentence.rstrip().endswith("?") or sentence.lstrip().startswith("¿"):
        return "question"
    if _DELIVERABLE.search(folded):
        return "deliverable"
    if _LEADING_VERB.match(folded) or _MODAL.search(folded):
        return "mandate"
    return None


def extract_guide_inventory(text: str) -> list[dict]:
    """Return ``[{id, kind, text}]`` for each demand-like sentence, in guide order; ``[]`` on any failure."""
    try:
        items: list[dict] = []
        seen: set[str] = set()
        for unit in _units(text):
            for sentence in re.split(r"(?<=[.?!;])\s+", unit):
                clean = _MARKER.sub("", sentence).strip()
                key = _fold(clean)
                if len(clean.split()) < _MIN_WORDS or key in seen:
                    continue
                kind = _kind(sentence)
                if kind is not None:
                    seen.add(key)
                    items.append({"id": f"G{len(items) + 1}", "kind": kind, "text": clean[:_MAX_TEXT]})
        return items
    except (TypeError, ValueError, UnicodeError, AttributeError):
        return []


def _guide_text(report_dir: Path, config: object) -> str | None:
    """The declared UTF-8 guide text when it resolves within the report folder."""
    try:
        raw = config.raw if hasattr(config, "raw") else config
        declared = raw.get("guide")
        if not isinstance(declared, str) or not declared.strip():
            return None
        root = Path(report_dir).resolve()
        target = (root / declared).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            return None
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError):
        return None


def load_guide_inventory(report_dir: Path, config: object) -> list[dict]:
    """The inventory of a declared guide inside the report folder; ``[]`` without one."""
    text = _guide_text(report_dir, config)
    return extract_guide_inventory(text) if text is not None else []


def load_guide_facts(report_dir: Path, config: object) -> dict[str, str]:
    """Read a declared UTF-8 guide only when it resolves within the report folder."""
    text = _guide_text(report_dir, config)
    return extract_guide_facts(text) if text is not None else {}


def main(argv: list[str] | None = None) -> int:
    import yaml
    from report_config import read_yaml

    args = sys.argv[1:] if argv is None else argv
    inventory = "--inventory" in args
    args = [arg for arg in args if arg != "--inventory"]
    if len(args) != 1:
        print("usage: guide_facts.py <folder> [--inventory]", file=sys.stderr)
        return 2
    folder = Path(args[0])
    try:
        config = read_yaml(folder / "report.yml")
    except (OSError, UnicodeError, yaml.YAMLError):
        config = {}
    payload = {"inventory": load_guide_inventory(folder, config)} if inventory else load_guide_facts(folder, config)
    print(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

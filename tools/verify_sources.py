#!/usr/bin/env python3
"""Check report bibliography identifiers against Crossref, DataCite and Open Library.

A DOI is looked up in Crossref and, when Crossref has no record (arXiv, Zenodo
and other DataCite DOIs), in DataCite. A web-only entry (``@misc``/``@online``)
without a DOI or ISBN is ``VERIFIED_URL`` when its URL answers; it proves the
page exists, never a scholarly record, and web-only entries never count toward
the source minimum (``source_count``).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import yaml

from report_config import load_report_config
from source_count import _ENTRY_HEADER

USER_AGENT = "academic-report-flow/1.0 (mailto omitted)"
WEB_TYPES = {"misc", "online"}
PASSING = {"VERIFIED", "VERIFIED_WITH_WARNINGS", "VERIFIED_URL"}
_URL = re.compile(r"https?://[^\s{}]+")
_UNESCAPED_PERCENT_IN_URL = re.compile(r"\\url\{[^}]*(?<!\\)%")


def entries(text: str):
    """Split entries using the shared BibTeX header; extract simple braced/quoted fields."""
    headers = list(_ENTRY_HEADER.finditer(text))
    for index, header in enumerate(headers):
        if header.group(1).lower() in {"string", "comment", "preamble"}:
            continue
        body = text[header.end():headers[index + 1].start() if index + 1 < len(headers) else len(text)]
        fields = {"_type": header.group(1).lower()}
        for match in re.finditer(r"\b(title|author|year|doi|isbn|url|howpublished)\s*=\s*", body, re.I):
            value = body[match.end():].lstrip()
            if value.startswith("{"):
                depth = 0
                for pos, char in enumerate(value):
                    depth += (char == "{") - (char == "}")
                    if depth == 0:
                        value = value[1:pos]
                        break
            elif value.startswith('"'):
                value = value[1:].split('"', 1)[0]
            else:
                value = value.split(",", 1)[0].strip().rstrip("}")
            fields[match.group(1).lower()] = value.strip()
        yield header.group(2), fields


_LATEX_ACCENTS = {"`": "\u0300", "'": "\u0301", "^": "\u0302", "~": "\u0303", "=": "\u0304",
                  ".": "\u0307", '"': "\u0308", "u": "\u0306", "v": "\u030c", "H": "\u030b",
                  "c": "\u0327", "k": "\u0328"}
_LATEX_ACCENT_RE = re.compile(r"\\([`'^~=.\"]|[uvHck](?=\s*\{|\s+[A-Za-z]))\s*(?:\{\s*(\\?[A-Za-z])\s*\}|([A-Za-z]))")
_LATEX_LETTERS = {"\\i": "i", "\\j": "j", "\\ss": "ss", "\\o": "o", "\\ae": "ae", "\\l": "l"}


def unescape_latex(value: str) -> str:
    """Turn BibTeX accent escapes (``M{\\'e}todos``, ``{\\~n}``) into plain Unicode."""
    def accent(match: re.Match) -> str:
        letter = match.group(2) or match.group(3)
        letter = _LATEX_LETTERS.get(letter, letter)
        return unicodedata.normalize("NFC", letter + _LATEX_ACCENTS[match.group(1)])

    value = _LATEX_ACCENT_RE.sub(accent, value)
    value = re.sub(r"\\(ss|ae|oe|[ijol])(?![A-Za-z])", lambda m: _LATEX_LETTERS.get("\\" + m.group(1), m.group(1)), value)
    return value.replace("{", "").replace("}", "")


def normalized(value: str) -> str:
    value = unescape_latex(value)
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()


def tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", normalized(value)))


class RegistryDataError(ValueError):
    """Registry answered 200 but the payload or a required field is unusable."""


def _covers(reference: set[str], candidate: set[str]) -> bool:
    return bool(reference) and len(reference & candidate) / len(reference) >= 0.8


def _title_matches(expected: str, found: str) -> bool:
    """Match full titles, or a registry that stores only the main title.

    Open Library often drops the subtitle, so a found title that covers the
    expected main title (text before ':') and adds no foreign words also matches.
    """
    expected_tokens, found_tokens = tokens(expected), tokens(found)
    if _covers(expected_tokens, found_tokens):
        return True
    main_tokens = tokens(expected.split(":", 1)[0])
    return _covers(main_tokens, found_tokens) and _covers(found_tokens, expected_tokens)


def year_of(value: object) -> int | None:
    match = re.search(r"\b(?:19|20)\d{2}\b", str(value or ""))
    return int(match.group()) if match else None


def _family_tokens(value: str) -> list[str]:
    return [word for word in re.findall(r'[a-z0-9]+', normalized(value))
            if word not in {'de', 'del', 'van', 'von', 'da', 'der'}]


def compare(fields: dict, remote: dict, kind: str) -> dict:
    mismatches = {}
    warnings = {}
    if not isinstance(remote, dict):
        raise RegistryDataError('registry response is not an object')
    message = remote.get("message", {}) if kind == "doi" else remote
    if not isinstance(message, dict):
        raise RegistryDataError('registry record is not an object')
    titles = message.get('title')
    if kind == 'doi':
        if not isinstance(titles, list) or not titles or not isinstance(titles[0], str) or not titles[0].strip():
            raise RegistryDataError('registry title missing or malformed')
        found_title = titles[0]
    else:
        if not isinstance(titles, str) or not titles.strip():
            raise RegistryDataError('registry title missing or malformed')
        found_title = titles
    expected_title = fields.get("title", "")
    if not _title_matches(expected_title, found_title):
        mismatches["title"] = {"expected": expected_title, "found": found_title}
    if kind == "doi":
        date = message.get("issued") or message.get("published-print") or {}
        if not isinstance(date, dict):
            raise RegistryDataError('registry issued date is not an object')
        parts = date.get("date-parts") or [[]]
        if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
            raise RegistryDataError('registry date-parts is not a list of lists')
        found_year = year_of(parts[0][0] if parts[0] else None)
    else:
        found_year = year_of(message.get("publish_date"))
    expected_year = year_of(fields.get("year"))
    if expected_year != found_year:
        target = warnings if expected_year is not None and found_year is not None and abs(expected_year - found_year) == 1 else mismatches
        target["year"] = {"expected": expected_year, "found": found_year}
    authors = message.get("author")
    if kind == "doi" and authors and fields.get("author"):
        if not isinstance(authors, list) or not isinstance(authors[0], dict):
            raise RegistryDataError('registry author list is not a list of objects')
        author = fields["author"].split(" and ", 1)[0]
        expected = author.split(",", 1)[0].strip() if "," in author else author.split()[-1]
        found = authors[0].get("family", "")
        if not isinstance(found, str):
            raise RegistryDataError('registry author family name is not a string')
        if expected and found and _family_tokens(expected) != _family_tokens(found):
            mismatches["author"] = {"expected": expected, "found": found}
    result = {"status": "MISMATCH" if mismatches else "VERIFIED_WITH_WARNINGS" if warnings else "VERIFIED"}
    if mismatches:
        result["mismatches"] = mismatches
    if warnings:
        result["warnings"] = warnings
    return result


def default_fetch(request: Request, timeout: int):
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def default_probe(url: str, timeout: int) -> int:
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=timeout) as response:
        return response.status


def from_datacite(remote: object) -> dict:
    """Reshape a DataCite record into the Crossref fields ``compare`` reads."""
    attributes = remote.get("data", {}).get("attributes") if isinstance(remote, dict) else None
    if not isinstance(attributes, dict):
        raise RegistryDataError("DataCite record has no attributes")
    titles = attributes.get("titles") or []
    title = titles[0].get("title") if titles and isinstance(titles[0], dict) else None
    creators = [c for c in attributes.get("creators") or [] if isinstance(c, dict)]
    family = (creators[0].get("familyName") or str(creators[0].get("name", "")).split(",", 1)[0]) if creators else ""
    message = {"title": [title] if isinstance(title, str) else [],
               "issued": {"date-parts": [[attributes.get("publicationYear")]]}}
    if family:
        message["author"] = [{"family": family}]
    return {"message": message}


def _web_url(fields: dict) -> str:
    if fields["_type"] not in WEB_TYPES:
        return ""
    match = _URL.search(fields.get("url", "") or fields.get("howpublished", ""))
    return match.group().rstrip(".,") if match else ""


def _with_retry(call, sleep):
    try:
        return call()
    except HTTPError as error:
        if error.code not in (429, 503):
            raise
        (sleep or time.sleep)(2)
        return call()


def _summary_line(row: dict) -> str:
    """One line per entry: ``key: STATUS`` plus the reason for anything not verified."""
    reasons = [row["detail"]] if row.get("detail") else []
    for kind in ("mismatches", "warnings"):
        reasons += [f"{field}: expected {v['expected']!r}, found {v['found']!r}" for field, v in row.get(kind, {}).items()]
    return f"{row['key'] or '(bibliography)'}: {row['status']}" + (f" ({'; '.join(reasons)})" if reasons else "")


def verify_sources(folder: Path, fetch=None, sleep=None, probe=None) -> int:
    folder = Path(folder)
    if not (folder / "report.yml").is_file():
        raise ValueError("report.yml does not exist")
    config = load_report_config(folder)
    bib = config.bib_path
    if bib is None:
        raise ValueError("report bibliography does not exist")
    data = bib.read_bytes()
    results = []
    for key, fields in entries(data.decode("utf-8")):
        result = {"key": key}
        doi = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi:)', '', fields.get('doi', '').strip(), flags=re.I)
        isbn = re.sub(r"[^0-9Xx]", "", fields.get("isbn", ""))
        web = _web_url(fields)
        if _UNESCAPED_PERCENT_IN_URL.search(fields.get("howpublished", "")):
            # LaTeX reads % as a comment once biber copies the field into the
            # .bbl, truncating it and aborting the build (#102).
            result["status"] = "MALFORMED_FIELD"
            result["detail"] = "howpublished: unescaped % inside \\url{}; move the address to the url field"
            results.append(result)
            continue
        if doi:
            url, kind = "https://api.crossref.org/works/" + quote(doi, safe="/"), "doi"
        elif isbn:
            url, kind = f"https://openlibrary.org/isbn/{isbn}.json", "isbn"
        elif web:
            url, kind = web, "url"
        else:
            result["status"] = "NO_IDENTIFIER"
            results.append(result)
            continue
        request = Request(url, headers={"User-Agent": USER_AGENT})
        get = fetch or default_fetch
        try:
            if kind == "url":
                _with_retry(lambda: (probe or default_probe)(url, 15), sleep)
                result["status"] = "VERIFIED_URL"
                result["detail"] = url
                results.append(result)
                continue
            try:
                remote = _with_retry(lambda: get(request, 15), sleep)
            except HTTPError as error:
                if kind != "doi" or error.code != 404:
                    raise
                datacite = Request("https://api.datacite.org/dois/" + quote(doi, safe="/"),
                                   headers={"User-Agent": USER_AGENT})
                remote = from_datacite(_with_retry(lambda: get(datacite, 15), sleep))
            result.update(compare(fields, remote, kind))
        except RegistryDataError as error:
            result['status'] = 'MISMATCH'
            result['detail'] = f'Registry data unusable: {error}'
        except HTTPError as error:
            result['status'] = 'NOT_FOUND' if error.code == 404 else 'NETWORK_ERROR'
            result['detail'] = f'HTTP {error.code}: {error.reason}'
        except json.JSONDecodeError as error:
            result['status'] = 'MISMATCH'
            result['detail'] = f'Registry returned malformed JSON: {error}'
        except (URLError, TimeoutError, OSError) as error:
            result['status'] = 'NETWORK_ERROR'
            result['detail'] = f'Registry unreachable: {error}'
        results.append(result)
    if not results:
        results.append({'key': '', 'status': 'NO_IDENTIFIER', 'detail': 'Empty bibliography: no entries to verify'})
    output = {"schema": "academic.sources-verification/v1", "bib_sha256": hashlib.sha256(data).hexdigest(),
              "checked_at": datetime.now(timezone.utc).isoformat(), "results": results}
    destination = folder / "research" / "sources-verification.yml"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(output, allow_unicode=True, sort_keys=False), encoding="utf-8")
    for row in results:
        print(_summary_line(row))
    failed = [row for row in results if row["status"] not in PASSING]
    if failed:
        print(f"verify_sources: {len(failed)} of {len(results)} entries failed; details in {destination}")
    return 1 if failed else 0


def main(argv=None, fetch=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args(argv)
    try:
        return verify_sources(args.folder, fetch=fetch)
    except (OSError, ValueError, UnicodeError) as error:
        parser.print_usage()
        print(f"verify_sources: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Offline contract tests for bibliography verification."""
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import yaml

import verify_sources as verify_sources_module
from verify_sources import verify_sources, main


def report(tmp_path, entry):
    folder = tmp_path / "report"
    folder.mkdir(parents=True)
    (folder / "report.yml").write_text("title: Test report\n", encoding="utf-8")
    (folder / "sources.bib").write_text(entry, encoding="utf-8")
    return folder


def doi_response(year=2020, title="A Study of Trees", author="García"):
    return {"message": {"title": [title], "issued": {"date-parts": [[year]]}, "author": [{"family": author}]}}


def result_rows(folder):
    return yaml.safe_load((folder / 'research/sources-verification.yml').read_text())['results']


def test_empty_bib_fails_with_reason(tmp_path):
    folder = report(tmp_path, '')
    assert verify_sources(folder, fetch=lambda *_: (_ for _ in ()).throw(AssertionError())) == 1
    assert 'empty' in result_rows(folder)[0]['detail'].lower()


def test_malformed_registry_continues(tmp_path):
    for bad in ('not json', [], {'message': []}, {'message': {'issued': {}}}):
        folder = report(tmp_path / str(len(list(tmp_path.iterdir()))), '@article{x, title={A Study of Trees}, doi={10.1/x}}\n@article{y, title={A Study of Trees}, year={2020}, doi={10.1/y}}')
        calls = iter([bad, doi_response()])
        assert verify_sources(folder, fetch=lambda *_: next(calls)) == 1
        rows = result_rows(folder)
        assert rows[0]['status'] == 'MISMATCH' and rows[0].get('detail')
        assert rows[1]['status'] == 'VERIFIED'


def test_doi_url_forms_normalized(tmp_path):
    for index, value in enumerate(('https://doi.org/10.1234/tree', 'http://dx.doi.org/10.1234/tree', 'doi:10.1234/tree')):
        folder = report(tmp_path / str(index), '@article{x, title={A Study of Trees}, year={2020}, doi={' + value + '}}')
        urls = []
        assert verify_sources(folder, fetch=lambda request, timeout: (urls.append(request.full_url), doi_response())[1]) == 0
        assert urls == ['https://api.crossref.org/works/10.1234/tree']


def test_author_particles_accents_hyphens_and_missing(tmp_path):
    for index, (author, remote) in enumerate((('de García-López, Ana', 'Garcia Lopez'), ('Van der García, Ana', 'garcia'), ('García, Ana', ''), ('', 'García'))):
        folder = report(tmp_path / str(index), '@article{x, title={A Study of Trees}, year={2020}, doi={10.1/x}, author={' + author + '}}')
        assert verify_sources(folder, fetch=lambda *_: doi_response(author=remote)) == 0


def test_retry_429_and_503_once_with_injected_sleep(tmp_path):
    for index, code in enumerate((429, 503)):
        folder = report(tmp_path / str(index), '@article{x, title={A Study of Trees}, year={2020}, doi={10.1/x}}')
        calls, sleeps = [], []
        def fetch(request, timeout):
            calls.append(timeout)
            raise HTTPError(request.full_url, code, 'busy', {}, None)
        assert verify_sources(folder, fetch=fetch, sleep=sleeps.append) == 1
        assert calls == [15, 15] and sleeps == [2]
        assert result_rows(folder)[0]['status'] == 'NETWORK_ERROR'


def test_verified_doi_and_bib_hash(tmp_path):
    folder = report(tmp_path, '@article{tree, title={A Study of Trees}, author={García, Ana}, year={2020}, doi={10.1234/tree}}')
    seen = []

    def fetch(request, timeout):
        seen.append((request.full_url, request.get_header("User-agent"), timeout))
        return doi_response()

    assert verify_sources(folder, fetch=fetch) == 0
    output = yaml.safe_load((folder / "research/sources-verification.yml").read_text())
    assert output["schema"] == "academic.sources-verification/v1"
    assert output["bib_sha256"] == hashlib.sha256((folder / "sources.bib").read_bytes()).hexdigest()
    assert output["checked_at"]
    assert output["results"][0]["status"] == "VERIFIED"
    assert seen == [("https://api.crossref.org/works/10.1234/tree", "academic-report-flow/1.0 (mailto omitted)", 15)]


def test_verified_isbn(tmp_path):
    folder = report(tmp_path, '@book{b, title={A Study of Trees}, year={2020}, isbn={978-1-234-56789-7}}')
    seen = []

    def fetch(request, timeout):
        seen.append(request.full_url)
        return {"title": "A Study of Trees", "publish_date": "2020"}

    assert verify_sources(folder, fetch=fetch) == 0
    assert seen == ["https://openlibrary.org/isbn/9781234567897.json"]


def test_year_warning(tmp_path):
    folder = report(tmp_path, '@article{x, title={A Study of Trees}, year={2021}, doi={10.1/x}}')
    assert verify_sources(folder, fetch=lambda request, timeout: doi_response()) == 0
    assert yaml.safe_load((folder / "research/sources-verification.yml").read_text())["results"][0]["status"] == "VERIFIED_WITH_WARNINGS"


def test_main_title_without_subtitle_matches(tmp_path):
    # Open Library often stores only the main title (seen for Humble 2010, Adzic 2011).
    folder = report(tmp_path, '@book{b, title={Specification by Example: How Successful Teams Deliver the Right Software}, year={2011}, isbn={978-1-61729-008-4}}')
    fetch = lambda request, timeout: {"title": "Specification by example", "publish_date": "2011"}
    assert verify_sources(folder, fetch=fetch) == 0


def test_shared_prefix_word_is_not_a_title_match(tmp_path):
    folder = report(tmp_path, '@book{b, title={Specification by Example: How Teams Work}, year={2011}, isbn={978-1-61729-008-4}}')
    fetch = lambda request, timeout: {"title": "Specification of Real-Time Systems", "publish_date": "2011"}
    assert verify_sources(folder, fetch=fetch) == 1


def test_title_mismatch(tmp_path):
    folder = report(tmp_path, '@article{x, title={Completely Different Work}, year={2020}, doi={10.1/x}}')
    assert verify_sources(folder, fetch=lambda request, timeout: doi_response()) == 1
    result = yaml.safe_load((folder / "research/sources-verification.yml").read_text())["results"][0]
    assert result["status"] == "MISMATCH"
    assert result["mismatches"]["title"] == {"expected": "Completely Different Work", "found": "A Study of Trees"}


def test_not_found(tmp_path):
    folder = report(tmp_path, '@article{x, title={A Study of Trees}, doi={10.1/x}}')

    def missing(request, timeout):
        raise HTTPError(request.full_url, 404, "missing", {}, None)

    assert verify_sources(folder, fetch=missing) == 1
    assert yaml.safe_load((folder / "research/sources-verification.yml").read_text())["results"][0]["status"] == "NOT_FOUND"


def test_network_error(tmp_path):
    folder = report(tmp_path, '@article{x, title={A Study of Trees}, doi={10.1/x}}')

    def unavailable(request, timeout):
        raise URLError("offline")

    assert verify_sources(folder, fetch=unavailable) == 1
    assert yaml.safe_load((folder / "research/sources-verification.yml").read_text())["results"][0]["status"] == "NETWORK_ERROR"


def test_no_identifier_and_usage_exit(tmp_path):
    folder = report(tmp_path, '@book{x, title={A Study of Trees}, year={2020}}')

    def forbidden(request, timeout):
        raise AssertionError("network access")

    assert verify_sources(folder, fetch=forbidden) == 1
    assert yaml.safe_load((folder / "research/sources-verification.yml").read_text())["results"][0]["status"] == "NO_IDENTIFIER"
    assert main([str(tmp_path / "missing")], fetch=forbidden) == 2


def test_malformed_json_from_default_fetch_reports_mismatch(tmp_path, monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return self.payload

    payloads = iter([FakeResponse(b'<html>not json</html>'),
                     FakeResponse(json.dumps({'title': 'A Study of Trees', 'publish_date': '2020'}).encode())])
    monkeypatch.setattr(verify_sources_module, 'urlopen', lambda request, timeout: next(payloads))
    bib = '@article{x, title={A Study of Trees}, doi={10.1/x}}\n@book{y, title={A Study of Trees}, year={2020}, isbn={978-1-234-56789-7}}'
    folder = report(tmp_path, bib)
    assert verify_sources(folder) == 1
    rows = result_rows(folder)
    assert rows[0]['status'] == 'MISMATCH' and 'json' in rows[0]['detail'].lower()
    assert rows[1]['status'] == 'VERIFIED'


def test_crossref_shape_errors_report_mismatch_and_continue(tmp_path):
    bad_payloads = (
        {'message': {'title': ['A Study of Trees'], 'issued': '2020'}},
        {'message': {'title': ['A Study of Trees'], 'issued': {'date-parts': 2020}}},
        {'message': {'title': ['A Study of Trees'], 'issued': {'date-parts': [[2020]]}, 'author': 'Garcia'}},
    )
    for index, bad in enumerate(bad_payloads):
        bib = '@article{x, title={A Study of Trees}, year={2020}, doi={10.1/x}, author={Garcia, Ana}}\n@article{y, title={A Study of Trees}, year={2020}, doi={10.1/y}}'
        folder = report(tmp_path / str(index), bib)
        calls = iter([bad, doi_response()])
        assert verify_sources(folder, fetch=lambda *_: next(calls)) == 1
        rows = result_rows(folder)
        assert rows[0]['status'] == 'MISMATCH' and rows[0].get('detail')
        assert rows[1]['status'] == 'VERIFIED'


def test_openlibrary_shape_errors_report_mismatch_and_continue(tmp_path):
    bad_payloads = ([], {'title': ['A Study of Trees'], 'publish_date': '2020'}, {'publish_date': '2020'})
    for index, bad in enumerate(bad_payloads):
        bib = '@book{b, title={A Study of Trees}, year={2020}, isbn={978-1-234-56789-7}}\n@book{c, title={A Study of Trees}, year={2020}, isbn={978-1-234-56789-7}}'
        folder = report(tmp_path / str(index), bib)
        calls = iter([bad, {'title': 'A Study of Trees', 'publish_date': '2020'}])
        assert verify_sources(folder, fetch=lambda *_: next(calls)) == 1
        rows = result_rows(folder)
        assert rows[0]['status'] == 'MISMATCH' and rows[0].get('detail')
        assert rows[1]['status'] == 'VERIFIED'


def test_network_error_keeps_status_and_later_entries_run(tmp_path):
    for index, boom in enumerate((URLError('offline'), TimeoutError('slow'))):
        bib = '@article{x, title={A Study of Trees}, doi={10.1/x}}\n@article{y, title={A Study of Trees}, year={2020}, doi={10.1/y}}'
        folder = report(tmp_path / str(index), bib)

        def flaky(request, timeout, boom=boom):
            if request.full_url.endswith('10.1/x'):
                raise boom
            return doi_response()

        assert verify_sources(folder, fetch=flaky) == 1
        rows = result_rows(folder)
        assert rows[0]['status'] == 'NETWORK_ERROR' and rows[0].get('detail')
        assert rows[1]['status'] == 'VERIFIED'


def test_prints_one_summary_line_per_entry(tmp_path, capsys):
    folder = report(
        tmp_path,
        '@article{a, title={A Study of Trees}, year={2020}, doi={10.1/a}}\n@book{b, title={Sin id}}',
    )
    assert main([str(folder)], fetch=lambda *_: doi_response()) == 1
    lines = capsys.readouterr().out.strip().splitlines()
    assert any(line.startswith("a: VERIFIED") for line in lines)
    assert any(line.startswith("b: NO_IDENTIFIER") for line in lines)


def test_failure_prints_a_clear_error_and_exits_non_zero(tmp_path, capsys):
    folder = report(tmp_path, '@article{a, title={A Study of Trees}, year={2020}, doi={10.1/a}}')
    assert main([str(folder)], fetch=lambda *_: doi_response(title="Other Topic Entirely")) == 1
    out = capsys.readouterr().out
    assert "a: MISMATCH" in out and "title" in out
    assert "verify_sources: 1 of 1 entries failed" in out


def test_latex_accent_escapes_do_not_cause_a_title_mismatch(tmp_path):
    cases = ("M{\\'e}todos Num{\\'e}ricos", "Ense{\\~n}anza de M{\\'e}todos", "M\\'etodos Num\\'ericos")
    for index, escaped in enumerate(cases):
        folder = report(
            tmp_path / str(index),
            '@article{a, title={' + escaped + '}, year={2020}, doi={10.1/a}}',
        )
        remote = escaped.replace("{\\'e}", "é").replace("\\'e", "é").replace("{\\~n}", "ñ")
        assert verify_sources(folder, fetch=lambda *_: doi_response(title=remote)) == 0, escaped


def datacite_response(year=2026, title="A Study of Trees", family="García"):
    return {"data": {"attributes": {"titles": [{"title": title}], "publicationYear": year,
                                    "creators": [{"name": f"{family}, Ana", "familyName": family}]}}}


def not_found(request):
    return HTTPError(request.full_url, 404, "Not Found", {}, None)


def crossref_404_then(*answers):
    calls = iter(answers)
    urls = []

    def fetch(request, timeout):
        urls.append(request.full_url)
        if request.full_url.startswith("https://api.crossref.org/"):
            raise not_found(request)
        answer = next(calls)
        if isinstance(answer, Exception):
            raise answer
        return answer
    return fetch, urls


def test_datacite_doi_verifies_when_crossref_has_no_record(tmp_path):
    folder = report(tmp_path, '@article{x, title={A Study of Trees}, year={2026}, author={García, Ana}, doi={10.48550/arXiv.2602.00180}}')
    fetch, urls = crossref_404_then(datacite_response())
    assert verify_sources(folder, fetch=fetch) == 0
    assert urls == ['https://api.crossref.org/works/10.48550/arXiv.2602.00180',
                    'https://api.datacite.org/dois/10.48550/arXiv.2602.00180']
    assert result_rows(folder)[0]['status'] == 'VERIFIED'


def test_datacite_record_is_compared_like_crossref(tmp_path):
    folder = report(tmp_path, '@article{x, title={A Study of Trees}, year={2026}, author={García, Ana}, doi={10.48550/x}}')
    fetch, _ = crossref_404_then(datacite_response(title="Something Else Entirely", family="Pérez"))
    assert verify_sources(folder, fetch=fetch) == 1
    row = result_rows(folder)[0]
    assert row['status'] == 'MISMATCH' and set(row['mismatches']) == {'title', 'author'}


def test_doi_missing_from_both_registries_is_not_found(tmp_path):
    folder = report(tmp_path, '@article{x, title={A Study of Trees}, year={2026}, doi={10.48550/x}}')
    fetch, urls = crossref_404_then(HTTPError('https://api.datacite.org/dois/10.48550/x', 404, 'Not Found', {}, None))
    assert verify_sources(folder, fetch=fetch) == 1
    assert result_rows(folder)[0]['status'] == 'NOT_FOUND'
    assert len(urls) == 2


def test_web_entry_with_a_reachable_url_is_verified_url(tmp_path, capsys):
    folder = report(tmp_path, '@misc{w, title={Spec Kit reference}, howpublished={\\url{https://example.org/doc}}}\n'
                              '@online{o, title={Docs}, url={https://example.org/b}}')
    probed = []
    assert verify_sources(folder, fetch=lambda *_: (_ for _ in ()).throw(AssertionError()),
                          probe=lambda url, timeout: (probed.append(url), 200)[1]) == 0
    assert probed == ['https://example.org/doc', 'https://example.org/b']
    assert [row['status'] for row in result_rows(folder)] == ['VERIFIED_URL', 'VERIFIED_URL']
    assert 'w: VERIFIED_URL' in capsys.readouterr().out


def test_web_entry_with_a_dead_or_unreachable_url_fails(tmp_path):
    folder = report(tmp_path, '@misc{a, title={A}, url={https://example.org/gone}}\n@misc{b, title={B}, url={https://example.org/down}}')

    def probe(url, timeout):
        if url.endswith('gone'):
            raise HTTPError(url, 404, 'Not Found', {}, None)
        raise URLError('no route')
    assert verify_sources(folder, probe=probe) == 1
    assert [row['status'] for row in result_rows(folder)] == ['NOT_FOUND', 'NETWORK_ERROR']


def test_scholarly_entry_with_only_a_url_stays_unidentified(tmp_path):
    folder = report(tmp_path, '@book{b, title={A Book}, year={2020}, url={https://example.org/book}}\n@misc{m, title={No link}}')
    probed = []
    assert verify_sources(folder, probe=lambda url, timeout: (probed.append(url), 200)[1]) == 1
    assert [row['status'] for row in result_rows(folder)] == ['NO_IDENTIFIER', 'NO_IDENTIFIER']
    assert probed == []


def test_datacite_record_without_creators_or_attributes(tmp_path):
    folder = report(tmp_path, '@article{x, title={A Study of Trees}, year={2026}, author={García, Ana}, doi={10.48550/x}}\n'
                              '@article{y, title={A Study of Trees}, year={2026}, doi={10.48550/y}}')
    no_creators = datacite_response()
    no_creators['data']['attributes']['creators'] = []
    fetch, _ = crossref_404_then(no_creators, {'data': {}})
    assert verify_sources(folder, fetch=fetch) == 1
    rows = result_rows(folder)
    assert rows[0]['status'] == 'VERIFIED'
    assert rows[1]['status'] == 'MISMATCH' and 'DataCite' in rows[1]['detail']


def test_percent_inside_url_in_howpublished_is_malformed(tmp_path, capsys):
    folder = report(tmp_path, '@misc{p, title={P}, howpublished={\\url{https://example.org/a%20b}}}\n'
                              '@online{u, title={U}, url={https://example.org/a%20b}}')
    probed = []
    assert verify_sources(folder, probe=lambda url, timeout: (probed.append(url), 200)[1]) == 1
    rows = result_rows(folder)
    assert [row['status'] for row in rows] == ['MALFORMED_FIELD', 'VERIFIED_URL']
    assert '%' in rows[0]['detail'] and 'url' in rows[0]['detail']
    assert probed == ['https://example.org/a%20b']
    assert 'p: MALFORMED_FIELD' in capsys.readouterr().out

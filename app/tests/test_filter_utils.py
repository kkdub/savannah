import os
from importlib import reload


def reload_fetch_jobs():
    # Ensure project root is on sys.path for dynamic reload
    import sys
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if root not in sys.path:
        sys.path.insert(0, root)
    from app.jobs import fetch_jobs as fj
    reload(fj)
    return fj


def test_text_contains_any_substring_vs_boundaries(monkeypatch):
    fj = reload_fetch_jobs()
    # With boundaries required, 'go' should not match 'Django'
    monkeypatch.setenv("FILTER_REQUIRE_WORD_BOUNDARIES", "true")
    assert fj._text_contains_any("Senior Django Engineer", ["go"], True) is False
    # Without boundaries, substring matches
    assert fj._text_contains_any("Senior Django Engineer", ["go"], False) is True


def test_matches_any_regex():
    fj = reload_fetch_jobs()
    assert fj._matches_any_regex("We love Python and FastAPI", ["python", "fastapi"]) is True
    assert fj._matches_any_regex("We love Java", ["python", "fastapi"]) is False


def test_passes_local_filters_text_and_location(monkeypatch):
    fj = reload_fetch_jobs()
    # Configure title filter and location allow
    monkeypatch.setenv("FILTER_TITLE_KEYWORDS", "[\"python\"]")
    monkeypatch.setenv("FILTER_LOCATION_ALLOW", "[\"remote\"]")
    # Must reload config and module to pick up env changes
    from app import config
    reload(config)
    fj = reload_fetch_jobs()

    j_pass = {"job_title": "Senior Python Developer", "job_location": "Remote - US"}
    j_block_loc = {"job_title": "Senior Python Developer", "job_location": "Onsite NYC"}
    j_block_text = {"job_title": "Senior Java Developer", "job_location": "Remote - US"}

    assert fj._passes_local_filters(j_pass) is True
    assert fj._passes_local_filters(j_block_loc) is False
    assert fj._passes_local_filters(j_block_text) is False

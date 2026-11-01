"""Unit tests for AI explanations using a fake provider. No network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from schemalens.explain import (
    AIDisabled,
    Explanation,
    FakeProvider,
    ProviderError,
    build_user_prompt,
    cross_check,
    explain_routine,
    get_or_create,
)
from schemalens.store import open_cache

GOOD = json.dumps(
    {
        "summary": "Counts rentals for a film.",
        "purpose": "Aggregate rentals via inventory.",
        "parameters": [{"name": "p_film_id", "meaning": "the film"}],
        "reads": ["public.inventory", "public.rental"],
        "writes": [],
        "side_effects": [],
        "caveats": ["business meaning of a rental not visible in code"],
    }
)


def test_build_user_prompt_lists_relations():
    prompt = build_user_prompt(
        {"definition": "SELECT 1"},
        {"public.film": [{"name": "film_id", "data_type": "integer"}]},
    )
    assert "SELECT 1" in prompt
    assert "public.film" in prompt
    assert "film_id integer" in prompt


def test_build_user_prompt_handles_no_relations():
    prompt = build_user_prompt({"definition": "SELECT now()"}, {})
    assert "none found" in prompt


def test_explain_routine_validates_and_cross_checks():
    provider = FakeProvider(response=GOOD)
    explanation = explain_routine(
        provider,
        {"definition": "SELECT ..."},
        {},
        analyzer_reads={"public.inventory"},
        analyzer_writes=set(),
    )
    assert isinstance(explanation, Explanation)
    assert explanation.summary.startswith("Counts")
    # LLM claimed public.rental, analyzer didn't -> disagreement
    assert any("public.rental" in d for d in explanation.disagreements)


def test_explain_routine_retries_once_on_bad_json():
    provider = FakeProvider(response=GOOD, fail_first=True)
    explanation = explain_routine(provider, {"definition": "x"}, {}, set(), set())
    assert provider.calls == 2
    assert explanation.summary.startswith("Counts")


def test_explain_routine_raises_after_two_failures():
    provider = FakeProvider(response="still not json {")
    with pytest.raises(ProviderError):
        explain_routine(provider, {"definition": "x"}, {}, set(), set())


def test_cross_check_detects_missing_and_extra():
    expl = Explanation(summary="s", purpose="p", reads=["a"], writes=["b"])
    diffs = cross_check(expl, analyzer_reads={"a", "c"}, analyzer_writes=set())
    assert any("c" in d and "LLM did not mention" in d for d in diffs)
    assert any("b" in d and "analyzer did not find" in d for d in diffs)


def test_get_or_create_caches(tmp_path: Path):
    cache_path = tmp_path / "cache.db"
    provider = FakeProvider(response=GOOD)
    routine = {"definition": "SELECT count(*) FROM public.inventory"}
    with open_cache(cache_path) as cache:
        first = get_or_create(cache, provider, routine, {}, {"public.inventory"}, set())
        assert provider.calls == 1
        # second call hits the cache
        second = get_or_create(cache, provider, routine, {}, {"public.inventory"}, set())
        assert provider.calls == 1
        assert first == second


def test_get_or_create_without_provider_and_no_cache_raises(tmp_path: Path):
    cache_path = tmp_path / "cache.db"
    with open_cache(cache_path) as cache:
        with pytest.raises(AIDisabled):
            get_or_create(cache, None, {"definition": "SELECT 1"}, {}, set(), set())

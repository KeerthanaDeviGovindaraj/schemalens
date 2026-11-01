"""AI explanations for routines (design.md section 6, requirement 6).

A provider returns JSON only. We validate it, cross-check its reads/writes
against the deterministic analyzer, cache by (definition hash, model, prompt
version), and never send row data. Works fully without a key (cache-only).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ValidationError

from schemalens.store import cache_get, cache_put, definition_hash

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = (
    "You explain PostgreSQL routines to developers new to a codebase. "
    "Respond with JSON only, matching this schema: "
    "summary (max 2 sentences), purpose, parameters [{name, meaning}], "
    "reads [schema.table], writes [schema.table], side_effects [string], caveats [string]. "
    "Do not guess business meaning you cannot see in the code; say so in caveats."
)


class Parameter(BaseModel):
    name: str
    meaning: str


class Explanation(BaseModel):
    summary: str
    purpose: str
    parameters: list[Parameter] = []
    reads: list[str] = []
    writes: list[str] = []
    side_effects: list[str] = []
    caveats: list[str] = []
    disagreements: list[str] = []


class Provider(Protocol):
    name: str

    def complete_json(self, system: str, user: str) -> str:  # pragma: no cover - interface
        ...


class AIDisabled(Exception):
    """Raised when explanation is requested but no provider is configured."""


class ProviderError(Exception):
    """Raised when a provider fails after the one allowed retry."""


@dataclass
class FakeProvider:
    """Deterministic provider for tests and offline use. No network."""

    response: str
    name: str = "fake"
    calls: int = 0
    fail_first: bool = False

    def complete_json(self, system: str, user: str) -> str:
        self.calls += 1
        if self.fail_first and self.calls == 1:
            return "not json at all {"
        return self.response


class GeminiProvider:
    """Google Gemini via the generativelanguage REST API. Key from GEMINI_API_KEY."""

    name = "gemini-1.5-flash"

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash") -> None:
        self.api_key = api_key
        self.name = model

    def complete_json(self, system: str, user: str) -> str:
        import httpx

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.name}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        resp = httpx.post(url, params={"key": self.api_key}, json=payload, timeout=60.0)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


def get_provider() -> Provider | None:
    """Select a provider from the environment. Returns None if no key is set."""
    choice = os.environ.get("SCHEMALENS_LLM_PROVIDER", "gemini").lower()
    if choice == "gemini":
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if key:
            return GeminiProvider(key)
    return None


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
    return text.strip()


def _parse(raw: str) -> Explanation:
    data = json.loads(_strip_fences(raw))
    return Explanation.model_validate(data)


def build_user_prompt(routine: dict, relation_meta: dict[str, list[dict]]) -> str:
    """routine: {definition, ...}. relation_meta: {relation_id: [{name, data_type}, ...]}."""
    lines = ["Routine definition:", routine["definition"], "", "Relations it references:"]
    if relation_meta:
        for rel_id, cols in relation_meta.items():
            col_text = ", ".join(f"{c['name']} {c['data_type']}" for c in cols)
            lines.append(f"- {rel_id}: {col_text}")
    else:
        lines.append("- (none found by the analyzer)")
    return "\n".join(lines)


def cross_check(explanation: Explanation, analyzer_reads: set[str], analyzer_writes: set[str]) -> list[str]:
    """Record where the LLM's claimed reads/writes differ from the analyzer."""
    disagreements: list[str] = []
    llm_reads = set(explanation.reads)
    llm_writes = set(explanation.writes)
    for rel in sorted(llm_reads - analyzer_reads):
        disagreements.append(f"LLM claims read of {rel}, analyzer did not find it")
    for rel in sorted(analyzer_reads - llm_reads):
        disagreements.append(f"Analyzer found read of {rel}, LLM did not mention it")
    for rel in sorted(llm_writes - analyzer_writes):
        disagreements.append(f"LLM claims write to {rel}, analyzer did not find it")
    for rel in sorted(analyzer_writes - llm_writes):
        disagreements.append(f"Analyzer found write to {rel}, LLM did not mention it")
    return disagreements


def explain_routine(
    provider: Provider,
    routine: dict,
    relation_meta: dict[str, list[dict]],
    analyzer_reads: set[str],
    analyzer_writes: set[str],
) -> Explanation:
    """Call the provider, validate (retry once), and attach disagreements."""
    user = build_user_prompt(routine, relation_meta)
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            raw = provider.complete_json(SYSTEM_PROMPT, user)
            explanation = _parse(raw)
            explanation.disagreements = cross_check(explanation, analyzer_reads, analyzer_writes)
            return explanation
        except (json.JSONDecodeError, ValidationError, KeyError) as exc:
            last_error = exc
        except Exception as exc:  # provider/network error
            last_error = exc
    raise ProviderError(f"explanation failed after retry: {last_error}")


def get_or_create(
    cache_conn,
    provider: Provider | None,
    routine: dict,
    relation_meta: dict[str, list[dict]],
    analyzer_reads: set[str],
    analyzer_writes: set[str],
) -> dict:
    """Return a cached explanation or generate and cache one.

    Raises AIDisabled if no provider and nothing is cached.
    """
    def_hash = definition_hash(routine["definition"])
    model = provider.name if provider else "none"
    cached = cache_get(cache_conn, def_hash, model, PROMPT_VERSION)
    if cached is not None:
        return cached
    # Also serve any cached explanation regardless of model (static/offline mode).
    if provider is None:
        any_model = cache_get(cache_conn, def_hash, "none", PROMPT_VERSION)
        if any_model is not None:
            return any_model
        raise AIDisabled("no LLM provider configured and no cached explanation")

    explanation = explain_routine(provider, routine, relation_meta, analyzer_reads, analyzer_writes)
    body = explanation.model_dump()
    cache_put(cache_conn, def_hash, model, PROMPT_VERSION, body, datetime.now(UTC).isoformat())
    return body

"""Name / definition normalization helpers."""

from __future__ import annotations

import re
import unicodedata


_PUNCT_RE = re.compile(r"[^\w\s%./+-]+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for matching."""
    text = unicodedata.normalize("NFKC", name or "").lower().strip()
    text = text.replace("&", " and ")
    text = _PUNCT_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    # Common expansions
    replacements = {
        "arr": "annual recurring revenue",
        "mrr": "monthly recurring revenue",
        "wau": "weekly active users",
        "mau": "monthly active users",
        "dau": "daily active users",
        "nps": "net promoter score",
        "cac": "customer acquisition cost",
        "ltv": "lifetime value",
        "au": "active users",
    }
    return replacements.get(text, text)


def normalize_definition(definition: str) -> str:
    text = unicodedata.normalize("NFKC", definition or "").lower().strip()
    text = _PUNCT_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def token_set(text: str) -> set[str]:
    return {t for t in normalize_definition(text).split() if len(t) > 1}


def jaccard(a: str, b: str) -> float:
    ta, tb = token_set(a), token_set(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def definitions_equivalent(old: str, new: str, threshold: float = 0.62) -> bool:
    """Heuristic sameness check — intentionally strict so silent redefinitions surface."""
    o = normalize_definition(old)
    n = normalize_definition(new)
    if not o or not n:
        return True  # missing definition ≠ drift by itself
    if o == n:
        return True
    # One contains the other nearly completely
    if o in n or n in o:
        shorter, longer = (o, n) if len(o) <= len(n) else (n, o)
        if len(shorter) >= 12 and len(shorter) / max(len(longer), 1) >= 0.55:
            return True
    if jaccard(o, n) >= threshold:
        return True
    # Short paraphrase of a longer definition ("signup + email verification").
    ta, tb = _content_tokens(o), _content_tokens(n)
    if not ta or not tb:
        return False
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    overlap = len(shorter & longer) / len(shorter)
    return len(shorter) >= 2 and overlap >= 0.8


_STOP = frozenset(
    "a an the and or of to for in on at by with within their its who that this is are be".split()
)


def _content_tokens(text: str) -> set[str]:
    tokens = set()
    for raw in text.split():
        if raw in _STOP or len(raw) < 3:
            continue
        # Light stemming for common KPI verbs/nouns
        tok = raw
        for suffix in ("ation", "ing", "ies", "ied", "ed", "es", "s"):
            if len(tok) > len(suffix) + 3 and tok.endswith(suffix):
                tok = tok[: -len(suffix)]
                break
        tokens.add(tok)
    return tokens


# Too generic to be safe index keys on their own — they collide across metrics.
GENERIC_ALIAS_KEYS = frozenset(
    {
        "actives",
        "active users",
        "au",
        "users",
        "metric",
        "kpi",
        "number",
        "rate",
    }
)


def alias_candidates(name: str, aliases: list[str] | None = None) -> set[str]:
    keys = {normalize_name(name)}
    for alias in aliases or []:
        if alias:
            keys.add(normalize_name(alias))
    return {k for k in keys if k}


def indexable_alias_keys(name: str, aliases: list[str] | None = None) -> set[str]:
    """Keys safe to store in the alias index (excludes ultra-generic tokens)."""
    primary = normalize_name(name)
    keys = {primary} if primary else set()
    for alias in aliases or []:
        key = normalize_name(alias)
        if not key or key in GENERIC_ALIAS_KEYS:
            continue
        keys.add(key)
    return keys


def lookup_keys(name: str, aliases: list[str] | None = None) -> list[str]:
    """Ordered lookup keys: primary name first, then specific aliases."""
    primary = normalize_name(name)
    ordered: list[str] = []
    if primary:
        ordered.append(primary)
    for alias in aliases or []:
        key = normalize_name(alias)
        if not key or key in ordered or key in GENERIC_ALIAS_KEYS:
            continue
        ordered.append(key)
    return ordered

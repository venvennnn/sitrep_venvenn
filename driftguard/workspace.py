"""Resolve a stable workspace key so glossary memory doesn't mix orgs."""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any


_WORKSPACE_RE = re.compile(
    r"(?im)^\s*workspace\s*[:=]\s*([A-Za-z0-9_./@-]+)\s*$"
)


def resolve_workspace(
    *,
    instructions: str = "",
    attendees: list[dict[str, Any]] | None = None,
    task: dict[str, Any] | None = None,
) -> str:
    """Priority: env → Studio instructions → task description → attendees hash → default."""
    env = os.getenv("DRIFTGUARD_WORKSPACE", "").strip()
    if env:
        return _slug(env)

    for blob in (
        instructions or "",
        (task or {}).get("description") or "",
        (task or {}).get("title") or "",
    ):
        match = _WORKSPACE_RE.search(blob)
        if match:
            return _slug(match.group(1))

    attendees = attendees or []
    names = sorted(
        {
            str(a.get("id") or a.get("email") or a.get("name") or "").strip().lower()
            for a in attendees
            if a
        }
    )
    names = [n for n in names if n]
    if names:
        digest = hashlib.sha256("|".join(names).encode()).hexdigest()[:12]
        return f"attendees-{digest}"

    return "default"


def _slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9_./@-]+", "-", value)
    return value[:80] or "default"

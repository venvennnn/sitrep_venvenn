"""Shared data models for DriftGuard."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MetricMention:
    """A metric/KPI as stated in a single meeting."""

    name: str
    definition: str = ""
    value: str | None = None
    previous_value: str | None = None
    unit: str | None = None
    owner: str | None = None
    team: str | None = None
    speaker: str | None = None
    aliases: list[str] = field(default_factory=list)
    confidence: float = 0.7

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetricMention":
        return cls(
            name=(data.get("name") or "").strip(),
            definition=(data.get("definition") or "").strip(),
            value=_clean_optional(data.get("value")),
            previous_value=_clean_optional(
                data.get("previous_value") or data.get("previous_value_mentioned")
            ),
            unit=_clean_optional(data.get("unit")),
            owner=_clean_optional(data.get("owner")),
            team=_clean_optional(data.get("team")),
            speaker=_clean_optional(data.get("speaker")),
            aliases=[a.strip() for a in (data.get("aliases") or []) if str(a).strip()],
            confidence=float(data.get("confidence") or 0.7),
        )


@dataclass
class GlossaryEntry:
    """Canonical metric record in the living glossary."""

    metric_id: str
    canonical_name: str
    definition: str
    aliases: list[str] = field(default_factory=list)
    owner: str | None = None
    team: str | None = None
    latest_value: str | None = None
    first_seen_at: str = ""
    last_seen_at: str = ""
    meeting_count: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    open_conflicts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Finding:
    """A drift / confound / conflict finding."""

    kind: str  # definition_drift | confounded_value | cross_team_conflict
    severity: str  # high | medium | low
    metric_name: str
    title: str
    summary: str
    recommendation: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractionResult:
    metrics: list[MetricMention]
    meeting_title: str = ""
    meeting_date: str | None = None
    raw_model_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": [m.to_dict() for m in self.metrics],
            "meeting_title": self.meeting_title,
            "meeting_date": self.meeting_date,
        }


def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "unknown", "-"}:
        return None
    return text

"""LLM extraction of metric mentions from a meeting summary."""

from __future__ import annotations

import json
import re
from typing import Any

from sitrep_agent.sdk import Ctx

from .models import ExtractionResult, MetricMention

EXTRACT_SYSTEM = """You are DriftGuard's metric extractor.
Read meeting notes and extract EVERY metric, KPI, or business number people discussed —
especially when someone states what the metric means / counts / includes / excludes.

Return ONLY valid JSON (no markdown fences) with this shape:
{
  "meeting_title": "short title",
  "meeting_date": "YYYY-MM-DD or null",
  "metrics": [
    {
      "name": "Activation",
      "aliases": ["activated users"],
      "definition": "working definition as the speaker described what it counts",
      "value": "55% or null",
      "previous_value": "45% or null if they compared to a prior number",
      "unit": "% or null",
      "owner": "person who owns the metric or null",
      "team": "Marketing|Product|Growth|Finance|Sales|RevOps|Data|Engineering|Leadership|Other|null",
      "speaker": "who stated this",
      "confidence": 0.0
    }
  ]
}

Rules:
- Capture the working definition in the speaker's words when available.
- If two teams define the same metric differently, emit TWO metric objects (same name, different team/definition).
- Include aliases people used in the meeting.
- Do not invent metrics that were not discussed.
- Prefer concrete definitions ("signup + email verification") over vague ones ("engaged users").
- confidence is 0-1 for how clearly the metric was stated.
"""


async def extract_metrics(
    ctx: Ctx,
    summary: str,
    attendees: list[dict[str, Any]],
    task_title: str = "",
    task_description: str = "",
) -> ExtractionResult:
    attendee_lines = ", ".join(
        f"{a.get('name') or a.get('id') or 'Unknown'}" for a in attendees
    ) or "(not provided)"

    prompt = (
        f"Task title: {task_title or 'Metric drift review'}\n"
        f"Task details: {task_description or '(none)'}\n"
        f"Attendees: {attendee_lines}\n\n"
        f"Meeting summary / notes:\n{summary.strip()}"
    )

    raw = await ctx.llm.complete(system=EXTRACT_SYSTEM, prompt=prompt, temperature=0.0)
    parsed = _parse_json_object(raw)
    metrics: list[MetricMention] = []
    for item in parsed.get("metrics") or []:
        if not isinstance(item, dict):
            continue
        mention = MetricMention.from_dict(item)
        if mention.name:
            metrics.append(mention)

    return ExtractionResult(
        metrics=metrics,
        meeting_title=(parsed.get("meeting_title") or task_title or "Meeting").strip(),
        meeting_date=parsed.get("meeting_date"),
        raw_model_output=raw,
    )


def extract_metrics_from_fixture(payload: dict[str, Any]) -> ExtractionResult:
    """Offline path for demos/tests — skip the LLM."""
    metrics = [MetricMention.from_dict(m) for m in payload.get("metrics") or []]
    metrics = [m for m in metrics if m.name]
    return ExtractionResult(
        metrics=metrics,
        meeting_title=(payload.get("meeting_title") or "Meeting").strip(),
        meeting_date=payload.get("meeting_date"),
        raw_model_output="",
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        return {"metrics": []}

    # Strip markdown fences if the model ignored instructions.
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Last resort: first {...} block
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(cleaned[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    return {"metrics": []}

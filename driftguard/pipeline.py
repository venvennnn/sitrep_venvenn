"""End-to-end DriftGuard pipeline used by handler.py and demos."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sitrep_agent.sdk import Ctx

from .detect import apply_updates, detect_findings
from .extract import extract_metrics, extract_metrics_from_fixture
from .models import ExtractionResult
from .report import build_glossary_artifact, build_report
from .store import GlossaryStore
from .workspace import resolve_workspace


async def run_driftguard(
    *,
    summary: str,
    attendees: list[dict[str, Any]],
    task: dict[str, Any],
    ctx: Ctx,
    store: GlossaryStore | None = None,
    fixture_extraction: dict[str, Any] | None = None,
) -> dict[str, Any]:
    store = store or GlossaryStore()
    workspace = resolve_workspace(
        instructions=ctx.instructions,
        attendees=attendees,
        task=task,
    )
    ctx.log(f"workspace={workspace}")

    prior = store.list_entries(workspace)
    ctx.log(f"glossary_size_before={len(prior)}")

    if fixture_extraction is not None:
        extraction = extract_metrics_from_fixture(fixture_extraction)
        ctx.log("extraction=fixture")
    else:
        extraction = await extract_metrics(
            ctx,
            summary=summary,
            attendees=attendees,
            task_title=task.get("title") or "",
            task_description=task.get("description") or "",
        )
        ctx.log(f"extraction=llm metrics={len(extraction.metrics)}")

    findings = detect_findings(extraction.metrics, prior)
    ctx.log(f"findings={len(findings)}")

    meeting_id = str(task.get("id") or uuid.uuid4())
    meeting_title = (
        extraction.meeting_title
        or task.get("title")
        or "Meeting"
    )

    apply_updates(
        store=store,
        workspace=workspace,
        mentions=extraction.metrics,
        findings=findings,
        meeting_id=meeting_id,
        meeting_title=meeting_title,
    )

    store.record_meeting(
        workspace=workspace,
        meeting_id=meeting_id,
        title=meeting_title,
        summary_hash=hashlib.sha256((summary or "").encode()).hexdigest()[:16],
        metrics=extraction.metrics,
        findings=[f.to_dict() for f in findings],
    )

    glossary = store.list_entries(workspace)
    meetings_seen = store.meeting_count(workspace)
    ctx.log(f"glossary_size_after={len(glossary)} meetings_seen={meetings_seen}")

    report_md = build_report(
        workspace=workspace,
        meeting_title=meeting_title,
        extraction=extraction,
        findings=findings,
        glossary=glossary,
        meetings_seen=meetings_seen,
        logs=list(ctx.logs),
    )
    glossary_md = build_glossary_artifact(glossary, workspace)

    alert_count = len(findings)
    title_suffix = (
        f"{alert_count} alert{'s' if alert_count != 1 else ''}"
        if alert_count
        else "glossary updated"
    )

    return {
        "artifacts": [
            {
                "type": "markdown",
                "title": f"DriftGuard — {title_suffix}",
                "content": report_md,
            },
            {
                "type": "markdown",
                "title": "Living metric glossary",
                "content": glossary_md,
            },
        ],
        "meta": {
            "workspace": workspace,
            "findings": [f.to_dict() for f in findings],
            "metrics": extraction.to_dict(),
            "glossary_count": len(glossary),
            "meetings_seen": meetings_seen,
        },
    }


async def run_driftguard_offline(
    *,
    summary: str,
    attendees: list[dict[str, Any]],
    task: dict[str, Any],
    fixture_extraction: dict[str, Any],
    instructions: str = "",
    store: GlossaryStore | None = None,
) -> dict[str, Any]:
    """Async helper for tests/demos without an LLM."""

    class _DummyLLM:
        model = "offline"

        async def complete(self, *args, **kwargs):
            raise RuntimeError("offline mode")

    class _OfflineCtx:
        def __init__(self):
            self.instructions = instructions
            self.tools = []
            self.llm = _DummyLLM()
            self.logs: list[str] = []

        def log(self, message: str) -> None:
            self.logs.append(message)

    return await run_driftguard(
        summary=summary,
        attendees=attendees,
        task=task,
        ctx=_OfflineCtx(),  # type: ignore[arg-type]
        store=store,
        fixture_extraction=fixture_extraction,
    )

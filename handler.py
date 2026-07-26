"""DriftGuard AI — SitRep code-track handler.

After every meeting, DriftGuard:
  1) Extracts metrics/KPIs + working definitions from the summary
  2) Compares them to a persistent living glossary (SQLite memory)
  3) Flags definition drift, confounded value changes, and cross-team conflicts
  4) Returns a plain-language report + updated glossary as Markdown artifacts

Optional Studio instructions:
  workspace: acme-corp
"""
from __future__ import annotations

from pathlib import Path

from driftguard.pipeline import run_driftguard
from sitrep_agent.sdk import AgentInput, Ctx

# Kept for Studio / no-code fallback compatibility with the starter kit.
SYSTEM_PROMPT = Path(__file__).with_name("prompt.txt").read_text(encoding="utf-8").strip()


async def handler(input: AgentInput, ctx: Ctx) -> dict:
    if not (ctx.instructions or "").strip():
        # Surface the local prompt in Studio test runs that send empty instructions.
        ctx.instructions = SYSTEM_PROMPT

    summary = (input.summary or "").strip()
    if not summary:
        return {
            "artifacts": [
                {
                    "type": "markdown",
                    "title": "DriftGuard — needs a meeting summary",
                    "content": (
                        "# DriftGuard\n\n"
                        "No meeting summary was provided. "
                        "Run this agent on a SitRep meeting task so it can extract "
                        "metrics, compare definitions, and update the living glossary.\n"
                    ),
                }
            ]
        }

    ctx.log(f"DriftGuard starting model={ctx.llm.model}")
    result = await run_driftguard(
        summary=summary,
        attendees=input.attendees or [],
        task=input.task or {},
        ctx=ctx,
    )
    # SitRep only needs artifacts; meta is useful for local demos/tests.
    return {"artifacts": result["artifacts"]}

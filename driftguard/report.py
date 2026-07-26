"""Render DriftGuard findings + living glossary as polished Markdown."""

from __future__ import annotations

from .models import ExtractionResult, Finding, GlossaryEntry
from .normalize import normalize_name


def build_report(
    *,
    workspace: str,
    meeting_title: str,
    extraction: ExtractionResult,
    findings: list[Finding],
    glossary: list[GlossaryEntry],
    meetings_seen: int,
    logs: list[str] | None = None,
) -> str:
    drifts = [f for f in findings if f.kind == "definition_drift"]
    confounds = [f for f in findings if f.kind == "confounded_value"]
    conflicts = [f for f in findings if f.kind == "cross_team_conflict"]

    lines: list[str] = []
    lines.append("# DriftGuard Report")
    lines.append("")
    lines.append(f"**Meeting:** {meeting_title}")
    lines.append(f"**Workspace:** `{workspace}`")
    lines.append(
        f"**Memory:** {meetings_seen} meeting(s) indexed · "
        f"{len(glossary)} metric(s) in glossary · "
        f"{len(extraction.metrics)} mention(s) this meeting"
    )
    lines.append("")

    # Alert strip
    if findings:
        lines.append("## Alerts")
        lines.append("")
        # Confounded value changes imply a definition move even when the
        # standalone drift finding was folded into a cross-team conflict.
        drift_metrics = {normalize_name(f.metric_name) for f in drifts}
        drift_signals = len(drifts) + sum(
            1
            for f in confounds
            if normalize_name(f.metric_name) not in drift_metrics
        )
        lines.append(
            f"- Definition drifts: **{drift_signals}**  \n"
            f"- Confounded value changes: **{len(confounds)}**  \n"
            f"- Cross-team conflicts: **{len(conflicts)}**"
        )
        lines.append("")
    else:
        lines.append("## Alerts")
        lines.append("")
        if extraction.metrics:
            lines.append(
                "No definition drift, confounded changes, or cross-team conflicts detected "
                "against the living glossary. New mentions were recorded."
            )
        else:
            lines.append(
                "No metrics/KPIs with clear definitions or values were found in this meeting."
            )
        lines.append("")

    if findings:
        lines.append("## Findings")
        lines.append("")
        for i, finding in enumerate(findings, 1):
            badge = finding.kind.replace("_", " ").title()
            lines.append(f"### {i}. {finding.title}")
            lines.append("")
            lines.append(f"**Type:** {badge} · **Severity:** {finding.severity}")
            lines.append("")
            lines.append(finding.summary)
            lines.append("")
            lines.append(f"**Recommendation:** {finding.recommendation}")
            lines.append("")
            details = finding.details or {}
            useful = {
                k: v
                for k, v in details.items()
                if v not in (None, "", []) and k != "metric_id"
            }
            if useful:
                lines.append("<details><summary>Evidence</summary>")
                lines.append("")
                for k, v in useful.items():
                    label = k.replace("_", " ").title()
                    lines.append(f"- **{label}:** {v}")
                lines.append("")
                lines.append("</details>")
                lines.append("")

    lines.append("## Metrics captured this meeting")
    lines.append("")
    if not extraction.metrics:
        lines.append("_None extracted._")
        lines.append("")
    else:
        lines.append("| Metric | Team | Value | Working definition | Speaker |")
        lines.append("|---|---|---|---|---|")
        for m in extraction.metrics:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _cell(m.name),
                        _cell(m.team),
                        _cell(m.value),
                        _cell(m.definition, limit=120),
                        _cell(m.speaker or m.owner),
                    ]
                )
                + " |"
            )
        lines.append("")

    lines.append("## Living glossary")
    lines.append("")
    lines.append(
        "Single source of truth for what your numbers mean — built automatically "
        "from meetings. Aliases resolve to one metric; open conflicts stay visible "
        "until someone reconciles them."
    )
    lines.append("")
    if not glossary:
        lines.append("_Glossary is empty — run DriftGuard on more meetings to build memory._")
        lines.append("")
    else:
        for entry in glossary:
            alias_txt = ", ".join(entry.aliases) if entry.aliases else "—"
            lines.append(f"### {entry.canonical_name}")
            lines.append("")
            lines.append(f"- **Definition:** {entry.definition or '_not yet captured_'}")
            lines.append(f"- **Aliases:** {alias_txt}")
            lines.append(
                f"- **Owner / team:** {entry.owner or '—'} / {entry.team or '—'}"
            )
            lines.append(f"- **Latest value:** {entry.latest_value or '—'}")
            lines.append(
                f"- **First seen:** {entry.first_seen_at or '—'} · "
                f"**Last seen:** {entry.last_seen_at or '—'} · "
                f"**Meetings:** {entry.meeting_count}"
            )
            if entry.open_conflicts:
                lines.append(f"- **Open conflicts:** {len(entry.open_conflicts)}")
                for c in entry.open_conflicts:
                    lines.append(
                        f"  - {c.get('team_a')} vs {c.get('team_b')}: "
                        f"“{c.get('definition_a')}” vs “{c.get('definition_b')}”"
                    )
            if entry.history:
                lines.append("- **Recent history:**")
                for h in entry.history[-5:]:
                    bit = h.get("definition") or h.get("value") or ""
                    lines.append(
                        f"  - `{h.get('seen_at', '')}` · {h.get('event')} · "
                        f"{h.get('meeting_title') or h.get('meeting_id')} · {bit}"
                    )
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_DriftGuard compounds: every meeting makes the glossary sharper. "
        "Install once — memory is the product._"
    )
    if logs:
        lines.append("")
        lines.append("<details><summary>Agent logs</summary>")
        lines.append("")
        for log in logs:
            lines.append(f"- {log}")
        lines.append("")
        lines.append("</details>")

    return "\n".join(lines).strip() + "\n"


def build_glossary_artifact(glossary: list[GlossaryEntry], workspace: str) -> str:
    lines = [
        "# Metric Glossary",
        "",
        f"Workspace: `{workspace}`",
        "",
    ]
    if not glossary:
        lines.append("_No metrics recorded yet._")
        return "\n".join(lines) + "\n"

    lines.append("| Metric | Definition | Team | Owner | Latest | Aliases | Conflicts |")
    lines.append("|---|---|---|---|---|---|---|")
    for e in glossary:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(e.canonical_name),
                    _cell(e.definition, 100),
                    _cell(e.team),
                    _cell(e.owner),
                    _cell(e.latest_value),
                    _cell(", ".join(e.aliases) if e.aliases else "—", 60),
                    _cell(str(len(e.open_conflicts))),
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _cell(value: str | None, limit: int = 80) -> str:
    text = (value or "—").replace("|", "/").replace("\n", " ").strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text

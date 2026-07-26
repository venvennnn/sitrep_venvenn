"""Compare new metric mentions against the living glossary."""

from __future__ import annotations

from .models import Finding, GlossaryEntry, MetricMention
from .normalize import definitions_equivalent, lookup_keys, normalize_name


def detect_findings(
    mentions: list[MetricMention],
    prior_entries: list[GlossaryEntry],
) -> list[Finding]:
    """Return definition drifts, confounded value changes, and cross-team conflicts."""
    findings: list[Finding] = []
    by_key = _index_entries(prior_entries)

    # Cross-team conflicts inside THIS meeting (same metric, different defs/teams)
    findings.extend(_intra_meeting_conflicts(mentions))

    for mention in mentions:
        if not mention.name:
            continue
        entry = _match_entry(mention, by_key)
        if entry is None:
            continue

        old_def = (entry.definition or "").strip()
        new_def = (mention.definition or "").strip()
        drifted = bool(old_def and new_def and not definitions_equivalent(old_def, new_def))

        value_moved = _value_moved(entry.latest_value, mention)

        if drifted:
            findings.append(
                Finding(
                    kind="definition_drift",
                    severity="high",
                    metric_name=entry.canonical_name,
                    title=f"Definition drift: {entry.canonical_name}",
                    summary=(
                        f"**{entry.canonical_name}** no longer means what it used to. "
                        f"Previously: “{old_def}”. "
                        f"Now ({mention.team or mention.speaker or 'this meeting'}): “{new_def}”. "
                        f"Every historical comparison across this change is no longer valid."
                    ),
                    recommendation=(
                        "Reconcile on one definition and announce it org-wide, "
                        "or version the metric (e.g. Activation v1 / Activation v2) "
                        "so old and new numbers stop being confused for each other."
                    ),
                    details={
                        "metric_id": entry.metric_id,
                        "old_definition": old_def,
                        "new_definition": new_def,
                        "owner": mention.owner or entry.owner,
                        "team": mention.team or entry.team,
                        "speaker": mention.speaker,
                        "old_value": entry.latest_value,
                        "new_value": mention.value,
                    },
                )
            )

        if drifted and value_moved:
            old_v = mention.previous_value or entry.latest_value
            new_v = mention.value
            findings.append(
                Finding(
                    kind="confounded_value",
                    severity="high",
                    metric_name=entry.canonical_name,
                    title=f"Confounded value change: {entry.canonical_name}",
                    summary=(
                        f"**{entry.canonical_name}** appears to move from {old_v} → {new_v}, "
                        f"but the definition also changed in the same window. "
                        f"These two numbers measure different things and are not comparable. "
                        f"Reporting this as growth/progress is a mistake."
                    ),
                    recommendation=(
                        "Do not report the delta as performance. Recompute both periods "
                        "under one frozen definition before sharing with leadership."
                    ),
                    details={
                        "metric_id": entry.metric_id,
                        "old_value": old_v,
                        "new_value": new_v,
                        "old_definition": old_def,
                        "new_definition": new_def,
                        "team": mention.team or entry.team,
                    },
                )
            )

        # Persistent cross-team conflict vs glossary owner/team
        if (
            new_def
            and old_def
            and mention.team
            and entry.team
            and normalize_name(mention.team) != normalize_name(entry.team)
            and not definitions_equivalent(old_def, new_def)
        ):
            findings.append(
                Finding(
                    kind="cross_team_conflict",
                    severity="medium",
                    metric_name=entry.canonical_name,
                    title=f"Cross-team conflict: {entry.canonical_name}",
                    summary=(
                        f"**{entry.team}** defines {entry.canonical_name} as “{old_def}”. "
                        f"**{mention.team}** defines it as “{new_def}”. "
                        f"Reported figures from these teams cannot be compared until reconciled."
                    ),
                    recommendation=(
                        "Name a single metric owner, pick one canonical definition "
                        "(or create team-specific aliased metrics), and update the glossary."
                    ),
                    details={
                        "metric_id": entry.metric_id,
                        "team_a": entry.team,
                        "definition_a": old_def,
                        "team_b": mention.team,
                        "definition_b": new_def,
                        "first_seen_at": entry.first_seen_at,
                    },
                )
            )

    return _dedupe_findings(findings)


def apply_updates(
    store,
    workspace: str,
    mentions: list[MetricMention],
    findings: list[Finding],
    meeting_id: str,
    meeting_title: str,
) -> list[GlossaryEntry]:
    """Persist mentions.

    Definition drift updates the canonical glossary when the same team (or an
    unscoped speaker) redefines a metric. Cross-team disagreements keep the
    prior canonical definition and stay open as conflicts.
    """
    drift_by_metric = {
        f.details.get("metric_id"): f
        for f in findings
        if f.kind == "definition_drift" and f.details.get("metric_id")
    }

    updated: list[GlossaryEntry] = []
    for mention in mentions:
        existing = store.find_entry(workspace, mention)
        should_rewrite = False
        if existing and existing.metric_id in drift_by_metric and mention.definition:
            prior_team = (existing.team or "").strip().lower()
            new_team = (mention.team or "").strip().lower()
            # Same team (or missing team info) → accept redefinition.
            # Different team → conflict only; do not flip the source of truth.
            should_rewrite = (not prior_team or not new_team or prior_team == new_team)

        if should_rewrite:
            entry = store.update_definition(
                workspace=workspace,
                metric_id=existing.metric_id,
                new_definition=mention.definition,
                meeting_id=meeting_id,
                meeting_title=meeting_title,
                mention=mention,
                event="definition_changed",
            )
        else:
            entry = store.upsert_mention(
                workspace=workspace,
                mention=mention,
                meeting_id=meeting_id,
                meeting_title=meeting_title,
            )
        updated.append(entry)

    # Attach open conflicts onto glossary entries (resolve metric_id if missing).
    conflict_by_metric: dict[str, list[dict]] = {}
    for finding in findings:
        if finding.kind != "cross_team_conflict":
            continue
        mid = finding.details.get("metric_id")
        if not mid:
            match = store.find_entry(
                workspace,
                MetricMention(name=finding.metric_name),
            )
            mid = match.metric_id if match else None
            if mid:
                finding.details["metric_id"] = mid
        if not mid:
            continue
        conflict_by_metric.setdefault(mid, []).append(
            {
                "summary": finding.summary,
                "team_a": finding.details.get("team_a"),
                "team_b": finding.details.get("team_b"),
                "definition_a": finding.details.get("definition_a"),
                "definition_b": finding.details.get("definition_b"),
                "status": "open",
            }
        )
    for mid, conflicts in conflict_by_metric.items():
        store.set_open_conflicts(workspace, mid, conflicts)

    return updated


def _index_entries(entries: list[GlossaryEntry]) -> dict[str, GlossaryEntry]:
    """Map normalized keys → entry. Canonical names always win over aliases."""
    alias_index: dict[str, GlossaryEntry] = {}
    canonical_index: dict[str, GlossaryEntry] = {}
    for entry in entries:
        canonical_index[normalize_name(entry.canonical_name)] = entry
        for alias in entry.aliases:
            key = normalize_name(alias)
            if key and key not in canonical_index:
                alias_index.setdefault(key, entry)
    # Canonical keys overwrite alias keys
    return {**alias_index, **canonical_index}


def _match_entry(
    mention: MetricMention, by_key: dict[str, GlossaryEntry]
) -> GlossaryEntry | None:
    for key in lookup_keys(mention.name, mention.aliases):
        if key in by_key:
            return by_key[key]
    return None


def _intra_meeting_conflicts(mentions: list[MetricMention]) -> list[Finding]:
    grouped: dict[str, list[MetricMention]] = {}
    for m in mentions:
        grouped.setdefault(normalize_name(m.name), []).append(m)

    findings: list[Finding] = []
    for _, group in grouped.items():
        if len(group) < 2:
            continue
        # Compare pairwise definitions across teams
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                if not a.definition or not b.definition:
                    continue
                if definitions_equivalent(a.definition, b.definition):
                    continue
                team_a = a.team or a.speaker or "Team A"
                team_b = b.team or b.speaker or "Team B"
                if normalize_name(team_a) == normalize_name(team_b):
                    continue
                findings.append(
                    Finding(
                        kind="cross_team_conflict",
                        severity="high",
                        metric_name=a.name,
                        title=f"Cross-team conflict: {a.name}",
                        summary=(
                            f"**{team_a}** defines {a.name} as “{a.definition}”. "
                            f"**{team_b}** defines it as “{b.definition}”. "
                            f"Their reported numbers are not comparable."
                        ),
                        recommendation=(
                            "Reconcile definitions before the next leadership review. "
                            "Until then, label each figure with its team-specific definition."
                        ),
                        details={
                            "team_a": team_a,
                            "definition_a": a.definition,
                            "team_b": team_b,
                            "definition_b": b.definition,
                            "value_a": a.value,
                            "value_b": b.value,
                        },
                    )
                )
    return findings


def _value_moved(prior_value: str | None, mention: MetricMention) -> bool:
    """Only treat as a value move when the speaker compared numbers, or both values exist."""
    if mention.value and mention.previous_value:
        return str(mention.value).strip() != str(mention.previous_value).strip()
    # Require an explicit previous_value for confound alerts when relying on glossary.
    # (Avoids false "55% → 18.2k" style mismatches across different metrics.)
    if mention.value and mention.previous_value is None and prior_value:
        # Still allow glossary comparison when the mention clearly states a new value
        # AND the definitions drifted — but only if units/shape look comparable.
        return _roughly_same_shape(prior_value, mention.value) and (
            str(mention.value).strip() != str(prior_value).strip()
        )
    return False


def _roughly_same_shape(a: str, b: str) -> bool:
    """Reject obvious unit mismatches like 55% vs 18.2k."""
    a_l, b_l = a.lower(), b.lower()
    a_pct, b_pct = "%" in a_l, "%" in b_l
    if a_pct != b_pct:
        return False
    a_k, b_k = ("k" in a_l and "%" not in a_l), ("k" in b_l and "%" not in b_l)
    if a_k != b_k:
        return False
    return True


def _dedupe_findings(findings: list[Finding]) -> list[Finding]:
    # If a cross-team conflict already explains a disagreement, drop the redundant
    # definition_drift for the same metric (keep confounded_value — that's the insight).
    conflict_metrics = {
        normalize_name(f.metric_name)
        for f in findings
        if f.kind == "cross_team_conflict"
    }
    seen: set[str] = set()
    out: list[Finding] = []
    for f in findings:
        if (
            f.kind == "definition_drift"
            and normalize_name(f.metric_name) in conflict_metrics
        ):
            continue
        key = f"{f.kind}|{normalize_name(f.metric_name)}|{f.title}|{f.summary[:120]}"
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    rank = {"high": 0, "medium": 1, "low": 2}
    out.sort(key=lambda x: (rank.get(x.severity, 9), x.kind, x.metric_name.lower()))
    return out

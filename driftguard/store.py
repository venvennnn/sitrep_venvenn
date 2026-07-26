"""SQLite-backed living glossary. Persists across meetings so memory compounds."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import GlossaryEntry, MetricMention
from .normalize import indexable_alias_keys, lookup_keys, normalize_name


def default_db_path() -> Path:
    configured = os.getenv("DRIFTGUARD_DB_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent / "data" / "glossary.db"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class GlossaryStore:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metrics (
                    metric_id TEXT PRIMARY KEY,
                    workspace TEXT NOT NULL,
                    canonical_name TEXT NOT NULL,
                    definition TEXT NOT NULL DEFAULT '',
                    aliases_json TEXT NOT NULL DEFAULT '[]',
                    owner TEXT,
                    team TEXT,
                    latest_value TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    meeting_count INTEGER NOT NULL DEFAULT 0,
                    history_json TEXT NOT NULL DEFAULT '[]',
                    open_conflicts_json TEXT NOT NULL DEFAULT '[]',
                    name_key TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_metrics_workspace
                    ON metrics(workspace);
                CREATE INDEX IF NOT EXISTS idx_metrics_name_key
                    ON metrics(workspace, name_key);

                CREATE TABLE IF NOT EXISTS alias_index (
                    workspace TEXT NOT NULL,
                    alias_key TEXT NOT NULL,
                    metric_id TEXT NOT NULL,
                    PRIMARY KEY (workspace, alias_key)
                );

                CREATE TABLE IF NOT EXISTS meetings (
                    meeting_id TEXT PRIMARY KEY,
                    workspace TEXT NOT NULL,
                    title TEXT,
                    summary_hash TEXT,
                    created_at TEXT NOT NULL,
                    metrics_json TEXT NOT NULL DEFAULT '[]',
                    findings_json TEXT NOT NULL DEFAULT '[]'
                );
                """
            )

    def list_entries(self, workspace: str) -> list[GlossaryEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM metrics WHERE workspace = ? ORDER BY canonical_name COLLATE NOCASE",
                (workspace,),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def find_entry(
        self, workspace: str, mention: MetricMention
    ) -> GlossaryEntry | None:
        keys = lookup_keys(mention.name, mention.aliases)
        if not keys:
            return None
        with self._connect() as conn:
            # Prefer canonical name_key hits before broader alias_index hits.
            for key in keys:
                row = conn.execute(
                    "SELECT * FROM metrics WHERE workspace = ? AND name_key = ?",
                    (workspace, key),
                ).fetchone()
                if row:
                    return self._row_to_entry(row)
            for key in keys:
                row = conn.execute(
                    """
                    SELECT m.* FROM alias_index a
                    JOIN metrics m ON m.metric_id = a.metric_id
                    WHERE a.workspace = ? AND a.alias_key = ?
                    """,
                    (workspace, key),
                ).fetchone()
                if row:
                    return self._row_to_entry(row)
        return None

    def upsert_mention(
        self,
        workspace: str,
        mention: MetricMention,
        meeting_id: str,
        meeting_title: str,
        seen_at: str | None = None,
    ) -> GlossaryEntry:
        seen_at = seen_at or utc_now()
        existing = self.find_entry(workspace, mention)

        if existing is None:
            entry = GlossaryEntry(
                metric_id=str(uuid.uuid4()),
                canonical_name=mention.name.strip(),
                definition=mention.definition.strip(),
                aliases=list(dict.fromkeys(mention.aliases)),
                owner=mention.owner,
                team=mention.team,
                latest_value=mention.value,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                meeting_count=1,
                history=[
                    self._history_event(
                        meeting_id, meeting_title, seen_at, mention, event="created"
                    )
                ],
                open_conflicts=[],
            )
            self._save_entry(workspace, entry)
            return entry

        # Update existing
        aliases = list(dict.fromkeys([*existing.aliases, *mention.aliases, mention.name]))
        # Keep prior aliases that equal the canonical name out of noise
        aliases = [a for a in aliases if normalize_name(a) != normalize_name(existing.canonical_name)]

        history = list(existing.history)
        history.append(
            self._history_event(
                meeting_id, meeting_title, seen_at, mention, event="observed"
            )
        )

        if mention.definition and not existing.definition:
            existing.definition = mention.definition
        if mention.owner and not existing.owner:
            existing.owner = mention.owner
        if mention.team and not existing.team:
            existing.team = mention.team
        if mention.value:
            existing.latest_value = mention.value

        existing.aliases = aliases
        existing.last_seen_at = seen_at
        existing.meeting_count = int(existing.meeting_count) + 1
        existing.history = history[-50:]  # cap growth
        self._save_entry(workspace, existing)
        return existing

    def update_definition(
        self,
        workspace: str,
        metric_id: str,
        new_definition: str,
        meeting_id: str,
        meeting_title: str,
        mention: MetricMention,
        event: str = "definition_changed",
    ) -> GlossaryEntry:
        entry = self.get_by_id(workspace, metric_id)
        if entry is None:
            raise KeyError(metric_id)
        entry.definition = new_definition
        entry.last_seen_at = utc_now()
        if mention.value:
            entry.latest_value = mention.value
        if mention.owner:
            entry.owner = mention.owner
        if mention.team:
            entry.team = mention.team
        entry.aliases = list(
            dict.fromkeys([*entry.aliases, *mention.aliases, mention.name])
        )
        entry.history.append(
            self._history_event(
                meeting_id, meeting_title, entry.last_seen_at, mention, event=event
            )
        )
        entry.history = entry.history[-50:]
        entry.meeting_count = int(entry.meeting_count) + 1
        self._save_entry(workspace, entry)
        return entry

    def set_open_conflicts(
        self, workspace: str, metric_id: str, conflicts: list[dict[str, Any]]
    ) -> None:
        entry = self.get_by_id(workspace, metric_id)
        if entry is None:
            return
        entry.open_conflicts = conflicts
        self._save_entry(workspace, entry)

    def get_by_id(self, workspace: str, metric_id: str) -> GlossaryEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM metrics WHERE workspace = ? AND metric_id = ?",
                (workspace, metric_id),
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def record_meeting(
        self,
        workspace: str,
        meeting_id: str,
        title: str,
        summary_hash: str,
        metrics: list[MetricMention],
        findings: list[dict[str, Any]],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO meetings
                (meeting_id, workspace, title, summary_hash, created_at, metrics_json, findings_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meeting_id,
                    workspace,
                    title,
                    summary_hash,
                    utc_now(),
                    json.dumps([m.to_dict() for m in metrics]),
                    json.dumps(findings),
                ),
            )

    def meeting_count(self, workspace: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM meetings WHERE workspace = ?",
                (workspace,),
            ).fetchone()
        return int(row["c"]) if row else 0

    def _save_entry(self, workspace: str, entry: GlossaryEntry) -> None:
        name_key = normalize_name(entry.canonical_name)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO metrics (
                    metric_id, workspace, canonical_name, definition, aliases_json,
                    owner, team, latest_value, first_seen_at, last_seen_at,
                    meeting_count, history_json, open_conflicts_json, name_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(metric_id) DO UPDATE SET
                    canonical_name=excluded.canonical_name,
                    definition=excluded.definition,
                    aliases_json=excluded.aliases_json,
                    owner=excluded.owner,
                    team=excluded.team,
                    latest_value=excluded.latest_value,
                    first_seen_at=excluded.first_seen_at,
                    last_seen_at=excluded.last_seen_at,
                    meeting_count=excluded.meeting_count,
                    history_json=excluded.history_json,
                    open_conflicts_json=excluded.open_conflicts_json,
                    name_key=excluded.name_key
                """,
                (
                    entry.metric_id,
                    workspace,
                    entry.canonical_name,
                    entry.definition,
                    json.dumps(entry.aliases),
                    entry.owner,
                    entry.team,
                    entry.latest_value,
                    entry.first_seen_at,
                    entry.last_seen_at,
                    entry.meeting_count,
                    json.dumps(entry.history),
                    json.dumps(entry.open_conflicts),
                    name_key,
                ),
            )
            conn.execute(
                "DELETE FROM alias_index WHERE workspace = ? AND metric_id = ?",
                (workspace, entry.metric_id),
            )
            keys = indexable_alias_keys(entry.canonical_name, entry.aliases)
            for key in keys:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO alias_index (workspace, alias_key, metric_id)
                    VALUES (?, ?, ?)
                    """,
                    (workspace, key, entry.metric_id),
                )

    @staticmethod
    def _history_event(
        meeting_id: str,
        meeting_title: str,
        seen_at: str,
        mention: MetricMention,
        event: str,
    ) -> dict[str, Any]:
        return {
            "event": event,
            "meeting_id": meeting_id,
            "meeting_title": meeting_title,
            "seen_at": seen_at,
            "definition": mention.definition,
            "value": mention.value,
            "team": mention.team,
            "owner": mention.owner,
            "speaker": mention.speaker,
        }

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> GlossaryEntry:
        return GlossaryEntry(
            metric_id=row["metric_id"],
            canonical_name=row["canonical_name"],
            definition=row["definition"] or "",
            aliases=json.loads(row["aliases_json"] or "[]"),
            owner=row["owner"],
            team=row["team"],
            latest_value=row["latest_value"],
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            meeting_count=int(row["meeting_count"] or 0),
            history=json.loads(row["history_json"] or "[]"),
            open_conflicts=json.loads(row["open_conflicts_json"] or "[]"),
        )

#!/usr/bin/env python3
"""Run the 3-meeting DriftGuard demo offline (no LLM required).

Usage:
  python scripts/demo_driftguard.py
  python scripts/demo_driftguard.py --db /tmp/driftguard-demo.db
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from driftguard.pipeline import run_driftguard_offline
from driftguard.store import GlossaryStore


FIXTURES = [
    ROOT / "fixtures" / "meeting1_growth_standup.json",
    ROOT / "fixtures" / "meeting2_product_review.json",
    ROOT / "fixtures" / "meeting3_board_prep.json",
]


async def main() -> int:
    parser = argparse.ArgumentParser(description="DriftGuard offline multi-meeting demo")
    parser.add_argument("--db", default=str(ROOT / "data" / "demo-glossary.db"))
    parser.add_argument("--out", default=str(ROOT / "data" / "demo-output"))
    args = parser.parse_args()

    db_path = Path(args.db)
    if db_path.exists():
        db_path.unlink()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    store = GlossaryStore(db_path)

    for i, path in enumerate(FIXTURES, 1):
        payload = json.loads(path.read_text(encoding="utf-8"))
        print(f"\n=== Meeting {i}: {path.name} ===")
        result = await run_driftguard_offline(
            summary=payload["summary"],
            attendees=payload.get("attendees") or [],
            task=payload.get("task") or {},
            fixture_extraction=payload["extraction"],
            instructions=(payload.get("agent") or {}).get("instructions", ""),
            store=store,
        )
        meta = result["meta"]
        print(f"workspace={meta['workspace']} findings={len(meta['findings'])} "
              f"glossary={meta['glossary_count']} meetings_seen={meta['meetings_seen']}")
        for finding in meta["findings"]:
            print(f"  - [{finding['kind']}] {finding['title']}")

        for art in result["artifacts"]:
            slug = art["title"].lower().replace(" ", "-").replace("—", "-")
            out = out_dir / f"meeting{i}-{slug[:48]}.md"
            out.write_text(art["content"], encoding="utf-8")
            print(f"  wrote {out}")

    print(f"\nDemo complete. Glossary DB: {db_path}")
    print(f"Reports: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

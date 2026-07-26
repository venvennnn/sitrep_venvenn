# DriftGuard AI

**The SitRep agent that catches when teams silently redefine the KPIs they all report on.**

Code-track agent for the [SitRep Marketplace](https://joinsitrep.com), built on the [SitRep Agent Starter Kit](https://github.com/SitRepAI/AgentStarterKit).

Walk into any company and ask three teams what “activation” means — you’ll get three answers. DriftGuard gives the organization a **memory for what its numbers mean**: it runs after meetings, extracts working definitions, compares them to everything it has seen before, and flags the disagreements that normal summaries miss.

## What it produces

After each meeting, DriftGuard returns two Markdown artifacts:

1. **DriftGuard report** — definition drifts, confounded value changes, cross-team conflicts, plus recommendations
2. **Living metric glossary** — canonical definitions, aliases, owners, history, open conflicts

### The three catches

| Signal | What it means |
|---|---|
| **Definition drift** | A metric’s meaning changed between meetings |
| **Confounded value change** | Value *and* definition moved in the same window — not real progress |
| **Cross-team conflict** | Two teams use the same name with different meanings |

## Why it’s a code agent (not just a prompt)

Memory is the product. DriftGuard persists a SQLite glossary across meetings so value compounds:

- Meeting 1 builds a small glossary
- Meeting 20 holds definition history no one can reconstruct from memory
- Drifts you’d find the hard way in a board meeting get caught when they happen

```
handler.py                  SitRep entrypoint
driftguard/
  extract.py                LLM JSON extraction of metric mentions
  detect.py                 Drift / confound / conflict logic
  store.py                  SQLite living glossary
  report.py                 Markdown artifacts
  pipeline.py               End-to-end orchestration
fixtures/                   3-meeting Activation + ARR demo
scripts/demo_driftguard.py  Offline demo (no LLM)
```

## Quickstart

```bash
# 1) Python deps
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2) Configure LLM (local Ollama or BYOK)
cp .env.example .env
# Default: Ollama at localhost:11434 with llama3.2:1b
# Or set OpenAI / OpenRouter in .env

# 3) Offline demo — proves memory + drift detection without an LLM
python scripts/demo_driftguard.py

# 4) Unit tests
python -m unittest discover -s tests -v

# 5) Run the SitRep agent locally
bash scripts/run-local.sh
# other terminal:
bash scripts/smoke-test.sh
```

### Optional workspace scoping

In SitRep Studio agent instructions (or the task description), set:

```text
workspace: acme-corp
```

Glossary memory is partitioned by workspace so installs don’t mix. You can also set `DRIFTGUARD_WORKSPACE` or `DRIFTGUARD_DB_PATH` in the environment.

## Connect to SitRep + publish

1. Create a free account at [joinsitrep.com](https://joinsitrep.com)
2. Studio → create agent → **Remote (host your own)**
3. Expose your agent:
   - Local: `bash scripts/tunnel.sh` (cloudflared)
   - Production: deploy via `render.yaml` (Render), Railway, Fly, or Docker
4. Paste the public URL as **Endpoint URL**
5. Save → copy the one-time **signing secret** into `.env` as `SITREP_AGENT_SECRET`
6. Hit **Test** in Studio → publish to the Marketplace
7. Use the published agent URL in your Kaggle writeup

See [docs/SUBMISSION.md](docs/SUBMISSION.md) for the full post-build checklist (deploy, marketplace, Kaggle writeup, demo video).

## Demo story (fixtures)

| Meeting | What happens |
|---|---|
| Growth standup | Activation = signup + email verify @ 45% → glossary created |
| Product weekly | Activation = completed onboarding @ 55% → **drift + confounded win**; Sales vs Finance ARR → **conflict** |
| Board prep | Alias collapse for Weekly Active Users; Activation conflict still open |

```bash
python scripts/demo_driftguard.py
# → data/demo-output/*.md
```

## Deploy notes

- Set `SITREP_AGENT_SECRET`, `LLM_BASE_URL`, `LLM_API_KEY`, `MODEL` on the host
- OpenRouter: use `MODEL=openrouter/free` (or another slug from https://openrouter.ai/models?q=free). Old starter-kit free slugs often 404.
- Prefer a **persistent disk** for `DRIFTGUARD_DB_PATH` so glossary memory survives restarts (Render free disk is ephemeral unless you attach storage)
- Health check: `GET /health` → `{"ok": true}`

## License

MIT — see [LICENSE](LICENSE).

Built for the SitRep “Build the Future of Work with AI Agents” hackathon (Code Track).

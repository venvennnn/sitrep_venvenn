# DriftGuard — what to do after the code is ready

The repo is the Code Track agent. These are the human steps left for SitRep + Kaggle.

## 1. Star the starter kit

Star https://github.com/SitRepAI/AgentStarterKit (submission requirement).

## 2. Make this GitHub repo public + MIT

- Confirm `LICENSE` (MIT) is in the repo root
- Settings → change visibility to **Public**
- Copy the public repo URL for the Kaggle writeup

## 3. Deploy the agent (judges need a live endpoint)

Tunnels die when your laptop sleeps — deploy somewhere always-on:

### Option A — Render (blueprint included)

1. Push this branch / merge to `main`
2. [Render](https://render.com) → New → Blueprint → select this repo (`render.yaml`)
3. Set env vars:
   - `SITREP_AGENT_SECRET` (from SitRep Studio after you create the remote agent)
   - `LLM_API_KEY` (OpenRouter / OpenAI)
   - `LLM_BASE_URL=https://openrouter.ai/api/v1`
   - `MODEL=openrouter/free`  
     *(OpenRouter free-model slugs change often. `meta-llama/llama-3.1-8b-instruct:free` is gone and returns **404**. Check https://openrouter.ai/models?q=free)*
   - `DRIFTGUARD_DB_PATH=/var/data/glossary.db` if you attach a disk
4. Note the public URL, e.g. `https://driftguard-xxxx.onrender.com`

### If Studio Test crashes with OpenRouter 404

On Render → Environment, set:

```
MODEL=openrouter/free
```

(or `openai/gpt-oss-20b:free`), save, redeploy, retry Test.

### Option B — Railway / Fly / any Docker host

`Dockerfile` + `Procfile` are included. Same env vars as above.

## 4. Publish on SitRep Marketplace

1. Sign up at https://joinsitrep.com
2. Open **Studio** → Create agent → **Remote (host your own)**
3. Fill marketplace metadata (matches `agent.json`):
   - **Name:** DriftGuard AI
   - **Tagline:** Catches when teams silently redefine the KPIs they all report on.
   - **Description:** use the longer blurb from `agent.json` / README
4. Endpoint URL = your deployed base URL (SitRep POSTs to `/run` and `/test`)
5. Save → copy signing secret once → put in host env as `SITREP_AGENT_SECRET` → restart
6. Studio instructions (recommended):
   ```text
   workspace: your-company-id
   ```
7. **Test** with a sample meeting summary (paste meeting 1 then meeting 2 from `fixtures/`)
8. **Publish** → copy the Marketplace agent URL

## 5. Record a short demo (for Media Gallery)

Keep it under ~3 minutes:

1. Show the problem (Activation / ARR mismatch) in one slide or the README
2. Run meeting 1 through SitRep Test (or `python scripts/demo_driftguard.py`)
3. Run meeting 2 — highlight definition drift + confounded 45%→55% + ARR conflict
4. Show the living glossary artifact
5. Show the published Marketplace page

## 6. Kaggle writeup (≤ 1000 words)

Use [docs/KAGGLE_WRITEUP.md](KAGGLE_WRITEUP.md). Attach:

- a. SitRep Agent URL (published)
- b. Public GitHub repo
- c. Confirmation you starred the starter kit
- d. Screenshots / demo video

**Submit** the writeup before the deadline — drafts don’t count.

## 7. Suggested Studio test summaries

**Test 1 — seed glossary**

> Growth standup. Priya reported activation at 45%, defined as signup + email verification within 24 hours.

**Test 2 — catch drift** (same `workspace:`)

> Product weekly. Alex said activation is 55%, up from 45%. Product defines activation as completing onboarding (profile + first project). Finance reports ARR RM12.4M excluding trials; Sales reports ARR RM13.1M including committed trials.

You should see definition drift, a confounded value change, and a cross-team ARR conflict.

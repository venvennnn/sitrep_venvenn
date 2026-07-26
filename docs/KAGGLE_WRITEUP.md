# DriftGuard AI — Kaggle Writeup draft (keep ≤ 1000 words)

**SitRep Agent URL:** _paste published Marketplace URL_  
**Public GitHub repo:** _paste public repo URL_  
**Starter kit starred:** yes — https://github.com/SitRepAI/AgentStarterKit

## Inspiration

Ask three teams what “activation” means and you’ll get three answers. Marketing counts signup + email verification. Product counts completed onboarding. Growth counts week-one return. Each team reports a number to leadership; each number measures something different.

That gap is why dashboards disagree in board meetings, why a metric can “improve” from 45% to 55% while nothing real changed except the definition, and why Finance’s ARR and Sales’s ARR can be millions apart with no written record of the disagreement. Semantic layers govern warehouse dashboards — they do nothing about definitions invented and mutated in meetings. DriftGuard lives in that gap.

## What it does

DriftGuard is a SitRep code-track agent that gives an organization a memory for what its numbers mean. After every meeting it:

1. Extracts every metric/KPI mentioned — name, working definition, value, speaker, team, aliases
2. Compares against a persistent living glossary built from prior meetings
3. Flags three things a normal summary never will:
   - **Definition drift** — meaning changed between meetings
   - **Confounded value changes** — value and definition moved together (not real progress)
   - **Cross-team conflicts** — same name, different meanings; kept open until reconciled
4. Updates the living glossary — canonical definition, aliases, owner, history, open conflicts

Outputs are two Markdown artifacts: an alert report with recommendations, and the glossary itself.

## How we built it

Built on the SitRep Agent Starter Kit as a Remote agent (`handler.py` + FastAPI `/run` `/test`).

- **Extraction:** structured LLM JSON pass over the meeting summary (temperature 0)
- **Memory:** SQLite glossary partitioned by `workspace` (Studio instruction, env, or attendees hash)
- **Detection:** deterministic comparison — definition similarity, value deltas, team mismatches — so catches stay reliable across models
- **Reporting:** plain-language Markdown with evidence and fix recommendations
- **Demo:** three fixtures (Growth standup → Product weekly → Board prep) runnable offline via `scripts/demo_driftguard.py` without an LLM

Stack: Python, FastAPI, httpx, SQLite, OpenAI-compatible LLM (Ollama / OpenRouter / OpenAI).

## Challenges we ran into

- SitRep payloads have no org id — we scoped memory with an explicit `workspace:` instruction plus safe fallbacks
- Free hosts often have ephemeral disks — glossary persistence needs an explicit `DRIFTGUARD_DB_PATH` on durable storage
- LLMs love to wrap JSON in fences — extraction has robust parse fallbacks; detection stays rule-based so a messy model can’t invent false calm
- “Same metric” matching needed alias normalization (AU / weekly actives / actives → one entry)

## Accomplishments we’re proud of

- The confounded-value insight: catching “Activation rose 45% → 55%” as noise when the definition loosened
- A glossary that compounds — the rare agent that gets more valuable every meeting
- An offline demo that proves drift + ARR conflict without any API keys
- Marketplace-ready packaging: `agent.json`, MIT license, deploy configs, submission checklist

## What we learned

Institutional metric definitions don’t live in the warehouse first — they live in conversation. Automating post-meeting work isn’t only emails and tickets; it’s preserving meaning. Separating LLM extraction from deterministic detection made the agent both flexible and trustworthy.

## What’s next

- Metric owners + Slack/Linear escalation when a high-severity drift opens
- Optional write-back of the glossary to Notion/Confluence
- Confidence-weighted merges and explicit “resolved” conflict workflow
- Multi-language meeting support and tighter attendee→team mapping from the company directory

1. create venv: 
python3 -m venv venv
source venv/bin/activate
2. downlaod requirements.txt:
pip install -r requirements.txt
3. create a .env and populate it with .env.example keys 



# ORII AI Calendar Assistant

AI-powered calendar assistant for Google Calendar, built as a Chrome extension with a chat-based interface.

**Status: rebuilding from v1.** The original (Flask + React + Redis, deployed on Railway, live for [N] users) is preserved on `archive/full-original`. I'm rewriting it by hand — no AI-assisted codegen — to deepen my understanding of the harder pieces: the GPT-4 → calendar-action translation layer, OAuth token handling, and context/session management.

**Progress: ~25–30% of a working pipeline. Nothing on `main` runs end-to-end yet.**

- Done: Google OAuth (credential loading, refresh, setup flow), LLM client (OpenAI integration, intent classification, date parsing), repo scaffolding
- In progress: cache layer (`is_stale` logic buggy), prompt engine (~1,800 lines ported, broken imports), date/logging utils (ported, broken imports), demo script (partially updated)
- Not started: pipeline glue (`calendar.py`, `retrieval.py`, `query.py`), intent processing, calendar service layer, eval framework, Chrome extension, web API

## Architecture

New design: a modular pipeline (`auth → cache → calendar → retrieval → llm`, orchestrated by `query.py`), replacing the old Flask monolith.

```
core/
├── auth.py        Google OAuth
├── llm.py         OpenAI client — intent classification, date parsing
├── cache.py       scaffolded, is_stale buggy
├── prompts.py     ported, broken imports
├── calendar.py    stub — Google Calendar API fetch
├── retrieval.py   stub — filters events against query
└── query.py       stub — orchestrator

utils/             ported, imports point at old paths
v2/                # v1 utilities kept for reference, not yet integrated
eval/              placeholder only
orii_demo.py       partially updated
```

Old monolith (Flask API, Chrome extension, DB, monitoring) removed from `main`, lives on `archive/full-original`.

**Stack (wired):** Python · OpenAI API · Google OAuth
**Stack (planned):** calendar retrieval/query layer, caching, Chrome extension, web API

## Running this

Not runnable end-to-end yet. For the working version:

```bash
git checkout archive/full-original
```

```bash
# env vars for the new pipeline
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
OPENAI_API_KEY=
```

## Roadmap

1. Wire up `calendar.py`, `retrieval.py`, `query.py` so `orii_demo.py` runs end-to-end
2. Fix broken imports in `cache.py`, `prompts.py`, `utils/`
3. Re-port intent detection and calendar service layer
4. Build eval framework
5. Rebuild Chrome extension and web API once the core pipeline is solid

## Why rebuild?

v1 worked and had real users, but the hardest logic (auth, action translation, session state) was scaffolded quickly. This rebuild is about understanding those pieces well enough to explain and extend them confidently.

## Reference: what v1 supports

Describes the archived `archive/full-original` branch, not current `main`.

- Natural language queries — *"What do I have tomorrow?"*
- Semantic search — *"When was my last dentist appointment?"*
- Event creation — *"Schedule lunch with John tomorrow at noon"*
- Context-aware, multi-turn conversations
- Multi-calendar support, attendees/reminders/Google Meet, recurrence, time zones

```
User: "What do I have tomorrow?"
ORII: "You have 3 meetings: 9am Standup, 2pm Client Call, 4:30pm Dentist."

User: "Reschedule the dentist to Friday"
ORII: "Done — moved to Friday at 4:30 PM."
```

Stack: React + TypeScript + Tailwind (frontend) · Flask + OpenAI GPT-4 + Redis (backend) · Google Calendar API · Chrome Manifest V3

## License

MIT — see [LICENSE](LICENSE).
# Orii — Engineering Log

**Decisions** — one-time write-ups for choices that shaped the architecture, in build order.
**Running Log** — dated bullets, added as work happens.

---

## Decisions

### Project scope: read-only, stateless, single-session (v1)
No event creation, editing, deletion, reminders, multi-calendar, or cross-session memory. Each query is independent — no "what about the day after?" follow-ups yet.
**Alternative considered:** building write operations alongside fetch, since it's the same API.
**Why:** proving fetch → understand → answer end-to-end mattered more than breadth. Write operations carry real risk (irreversible changes to a real calendar) not worth taking on before the read path works.

### Pipeline architecture: thin orchestrator, single-responsibility modules
```
query.py (orchestrator, no business logic)
  → auth.py       Google OAuth
  → cache.py      in-memory TTL cache
  → gcal_client.py  fetch events from Google Calendar API
  → date_parser.py  NL → date range
  → retrieval.py  filter events against parsed query
  → llm.py        generate grounded natural-language answer
```
Each module has one job and one contract. Built bottom-up (pure, dependency-free modules first) so each is testable alone before the orchestrator — which needs every module's contract finalized — is written last.

### Data format: Google Calendar JSON API, not `icalendar`/ICS
**Alternative considered:** standardizing on `icalendar` (vendor-neutral spec).
**Why:** live Google API access already exists; ICS adds a translation layer with no payoff until non-Google calendars are supported (v3+).
**Audit before shelving:** reviewed the unused `icalendar_utils.py` anyway and found four bugs worth having on record:
- timezone handling asymmetric — naive `start_time` gets localized, naive `end_time` doesn't
- attendee parsing breaks on exactly one attendee (iCalendar returns a scalar, not a list, for single values)
- `RRULE` input unvalidated — malformed strings can produce non-compliant output
- all-day `dtend` always adds one day — only correct under inclusive-end semantics

### Query parsing: structured schema, not intent classification
Every query parses into one JSON schema with optional fields (time range, attendees, keywords, status, ordinals, exclusions) instead of routing to separate handlers by intent type.
**Why:** bucket routing breaks on hybrid queries (e.g. "next 1-on-1 with Alex that isn't the recurring one"). A single schema handles hybrids without rearchitecting for new categories.
**Related:** date/time resolution goes through a deterministic library (`dateparser`), not the LLM — the LLM only identifies which expression was used, escalating to itself on parse failure.

### 1. `auth.py` — Google OAuth
Loads credentials from env vars (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`). One-time `setup_oauth_flow()` runs the browser consent flow and writes the refresh token to `.env`; `get_credentials()` builds a `Credentials` object from the stored refresh token and refreshes it via `Request()` if expired.
**Why env vars over `credentials.json`:** keeps secrets out of the repo, standard practice for anything checked into git.

### 2. `cache.py` — in-memory TTL cache
`Cached` class wraps a dict keyed by date-range string, each value storing `{"events": [...], "retrieved_at": datetime}`. `is_stale()` compares `retrieved_at + ttl` against `now()` on every `get()`.
**Why a class here specifically:** state (the cached dict, the TTL) needs to persist across calls — contrast with `gcal_client.py` below, which needs no state and is a plain function.
**Interface decision:** since `cache.py` and its caller are both mine to write, I define the contract rather than discover it — key is a date-range string, value is a list of event dicts, enforced with type hints (`-> None`, etc.) so it's explicit instead of implicit.

### 3. `gcal_client.py` — Google Calendar API fetch
Single function `retrieve_cal_data(creds, start_date, end_date)`, no class. Calls `events().list()` on the primary calendar, returns `items` or `[]` if empty, `None` on `HttpError`.
**Why a function, not a class:** no state to carry between calls — each call is independent (input in, output out). Class is reserved for `cache.py`, where TTL and cached data must persist.
**Deferred to v2:** currently hardcoded to `calendarId="primary"`. Multi-calendar support means calling `calendarList().list()` first and looping — out of scope for v1.

### Version roadmap: capability tiers, not difficulty tiers
v1/v2 = Read (basic/advanced), v3 = Memory, v4 = Write, v5+ = Beyond (unspecified for now).
**Why Write is its own tier, not folded into Read-advanced:** different risk category — irreversible side effects on a real calendar, not just queries. Worth isolating so it gets deliberate scoping later instead of sliding in as "just another feature."
**Why v5+ stays undefined:** planning it now would be guessing. Ideas that surface before their version is ready get parked, not designed prematurely.

### 4. `date_parser.py` — NL → date range (in progress)
Returns `{"start": ..., "end": ..., "is_past": ...}` — a dict, not a tuple, for extensibility.
**Boundary:** the 6-month retry-loop and `is_past` decision live in `query.py`, not here. `date_parser.py` stays pure — NL parsing (`dateparser`, escalating to the LLM only on failure) plus pure datetime arithmetic (`shift_range`).
**Corrected assumption:** initially thought `retrieval.py` should own "keep expanding the window until something matches," since it's the piece that knows whether anything matched. Tracing the actual call sequence showed only `query.py` holds both facts needed — that the last attempt was empty, and the ability to re-invoke `date_parser` — so the loop belongs there.
**Three query cases:** explicit single date, explicit range, and implicit/unspecified (e.g. "when was my last therapy session?"). The implicit case searches in monthly steps, stopping at first match, capped at 6 months before prompting the user to keep going.
**Bug caught pre-implementation:** initial `shift_range` pseudocode had swapped branches, a missing assignment, and arithmetic on strings instead of datetime objects — found by tracing retry-loop cases before writing real code.

---

## Running Log

`YYYY-MM-DD — what happened, one to three sentences.`

<!-- Add entries below -->

- 2026-07-23 — `gcal_client.py` (file 3) done: single function, no class — no state to carry between calls, unlike `cache.py`.
- 2026-07-22 — `date_parser.py` (file 4) in progress — see decision entry above for the retry-loop ownership correction. started branch/PR discipline going forward (one issue → one branch → one PR) starting with `date_parser`.
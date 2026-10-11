# MeetingAgent

Turns a team's meeting transcripts into owned, de-duplicated tasks in the issue tracker,
and follows up on them at the next meeting.

Meeting tools already write summaries. The useful part is what comes after: deciding who
owns each task, not filing a ticket that already exists, and checking next week whether
anything actually happened.

## How it works

```
Transcript (.vtt / .srt / .txt from Teams, Zoom or Meet)
  -> clean up              strip timestamps, keep speaker names
  -> extract               summary, decisions, action items (owner, due date, priority, quote)
  -> review                a teammate edits and approves
  -> duplicate check       compare against existing tickets
  -> file                  create tickets in the local tracker
  -> follow up             open items from the last meeting            [planned]
```

## Status

| Phase | What it does | State |
| --- | --- | --- |
| 1. Minutes | Transcript in, summary + decisions + action items out, with a review page | Done |
| 2. Tickets | Approve items and create them in the local tracker (mock Jira) | Done |
| 3. Duplicates | Flag action items that match existing tickets (word overlap) | Done |
| 4. Follow-up | Open items from last time, search past decisions | Planned |
| 5. Polish | Live Jira/Qdrant embeddings, Docker, CI, deployment | Planned |

Audio upload with Whisper is wired up in `services/transcriber.py` but is not connected to
the API yet; transcripts are the primary input.

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r backend/requirements.txt
copy .env.example .env
```

Put a Gemini API key from https://aistudio.google.com into `.env`. To keep everything on
your own machine instead, install [Ollama](https://ollama.com), then set `LLM_PROVIDER=ollama`
and `EMBED_PROVIDER=ollama`.

## Run

```bash
cd backend
uvicorn main:app --reload
```

Open **http://localhost:8000** for the review page: drop in a transcript, then edit,
approve or reject what comes back. Items that already look like tickets in
`data/mock_tickets.json` are flagged. Approved items can be filed into a local
tracker (`data/local_tickets.json`, not committed). Copy the minutes as Markdown.
Your edits survive a refresh. http://localhost:8000/docs has the interactive API.

### Extract notes from a transcript file

```bash
curl -X POST http://localhost:8000/extract/file \
  -F "file=@../data/sample_meeting.vtt" \
  -F "meeting_date=2026-09-15" \
  -F "attendees=Alice Fernandes, Bob Mehta, Carol D'Souza"
```

### Or send text directly

```bash
curl -X POST http://localhost:8000/extract \
  -H "Content-Type: application/json" \
  -d '{"transcript": "Bob: I will add rate limiting by Wednesday.", "meeting_date": "2026-09-15"}'
```

Both return the same shape:

```json
{
  "meeting_id": "0f1c...",
  "summary": "The team discussed login problems and the release schedule.",
  "decisions": ["Release every Thursday afternoon"],
  "action_items": [
    {
      "id": "8a2e...",
      "task": "Add rate limiting to the login endpoint",
      "owner": "Bob Mehta",
      "due_date": "2026-09-16",
      "priority": "high",
      "status": "possible_duplicate",
      "similar_tickets": [
        {"id": "MEET-110", "title": "Add rate limiting to API", "status": "open", "score": 0.6}
      ],
      "source_segment": "Sure, I will do it by Wednesday."
    }
  ],
  "transcript_length": 1784,
  "extracted_at": "2026-09-19T09:12:44.113Z"
}
```

Passing `attendees` is worth it: owners are matched against that list, so "Bob" in the
transcript becomes "Bob Mehta". Passing `meeting_date` lets "by Wednesday" become a real date.

### File approved items as tickets

```bash
curl -X POST http://localhost:8000/dispatch \
  -H "Content-Type: application/json" \
  -d '{"meeting_id": "0f1c...", "approved_items": [{"id": "8a2e...", "task": "Write the on-call rota", "owner": "Carol", "priority": "medium", "status": "approved"}]}'
```

`GET /tickets` lists the sample corpus plus anything you filed. Live Jira is not
connected yet; keep `MOCK_INTEGRATIONS=true`.

## Tests

```bash
cd backend
pytest
```

The tests replace the model with canned responses, so they need no API key and cost nothing.

## Privacy

Meeting transcripts are usually confidential. On the Gemini free tier, Google may use
prompts to improve its products, so use it only with sample or anonymised transcripts. For
real meetings, use a paid key or run everything locally with Ollama, and check your
company's policy first.

## Layout

```
backend/
  main.py                    API endpoints
  static/index.html          review page
  config.py                  settings, read from .env
  agents/extraction.py       transcript -> summary, decisions, action items
  agents/dedup.py            action items vs existing tickets
  agents/dispatch.py         approved items -> local tracker tickets
  services/transcript_parser.py  .vtt / .srt / .txt -> clean text
  services/ticket_store.py   sample tickets + locally filed tickets
  services/transcriber.py    Whisper audio transcription (not wired up yet)
  services/job_store.py      job tracking for long running uploads
  providers/                 Gemini and Ollama clients
  models/schemas.py          request and response shapes
  tests/
data/
  sample_meeting.vtt         sample transcript
  mock_tickets.json          sample tickets for duplicate detection
```

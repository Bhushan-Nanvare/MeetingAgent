import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agents.dedup import annotate_action_items
from agents.dispatch import dispatch_items
from agents.extraction import ExtractionError, extract_meeting
from config import settings
from models.schemas import (
    CorpusIngestResponse,
    DispatchBatchResponse,
    DispatchRequest,
    ExtractionResult,
    ExtractRequest,
    FollowUpItem,
    ItemUpdate,
    MeetingDetail,
    MeetingSummary,
    SearchResponse,
    StoredActionItem,
)
from services import meeting_store
from services.db import init_db
from services.ticket_store import all_tickets, get_ticket
from services.transcript_parser import parse_transcript
from tools import get_tracker

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_SUFFIXES = {".txt", ".vtt", ".srt", ".md"}
STATIC_DIR = Path(__file__).resolve().parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="MeetingAgent",
    version="1.0.0",
    description="Turns meeting transcripts into summaries, decisions, owned action items and tracker tickets.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """The review page: upload a transcript, edit and approve what comes back."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "gemini_key_set": bool(settings.GEMINI_API_KEY),
        "mock_integrations": settings.MOCK_INTEGRATIONS,
        "tracker": _tracker_name(),
        "dedup": _dedup_mode(),
        "ticket_count": len(all_tickets()),
    }


def _dedup_mode() -> str:
    if not settings.SEMANTIC_DEDUP:
        return "words"
    from rag.client import collection_ready

    return "semantic" if collection_ready() else "words (corpus not indexed)"


def _tracker_name() -> str:
    try:
        return get_tracker().name
    except Exception as e:
        logger.warning(f"Tracker unavailable: {e}")
        return "unconfigured"


@app.post("/extract", response_model=ExtractionResult)
async def extract(request: ExtractRequest) -> ExtractionResult:
    return await _extract(
        request.transcript,
        meeting_id=request.meeting_id,
        meeting_date=request.meeting_date,
        attendees=request.attendees,
        title=request.title,
    )


@app.post("/extract/file", response_model=ExtractionResult)
async def extract_file(
    file: UploadFile = File(...),
    meeting_id: str | None = Form(None),
    meeting_date: str | None = Form(None),
    attendees: str = Form(""),
    title: str = Form(""),
) -> ExtractionResult:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{suffix or file.filename}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_SUFFIXES))}",
        )

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    return await _extract(
        raw.decode("utf-8-sig", errors="replace"),
        meeting_id=meeting_id,
        meeting_date=meeting_date,
        attendees=[name.strip() for name in attendees.split(",") if name.strip()],
        title=title or Path(file.filename or "").stem,
    )


async def _extract(
    raw_transcript: str,
    meeting_id: str | None,
    meeting_date: str | None,
    attendees: list[str],
    title: str = "",
) -> ExtractionResult:
    transcript = parse_transcript(raw_transcript)
    if not transcript:
        raise HTTPException(status_code=422, detail="Transcript is empty")

    try:
        result = await extract_meeting(
            transcript,
            meeting_id=meeting_id,
            meeting_date=meeting_date,
            attendees=attendees,
        )
    except ExtractionError as e:
        logger.error(f"Extraction failed: {e}")
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        logger.exception("Language model call failed")
        raise HTTPException(status_code=502, detail=f"Language model call failed: {e}") from e

    await annotate_action_items(result.action_items)
    meeting_store.save_meeting(result, meeting_date, attendees, title)
    return result


@app.get("/meetings", response_model=list[MeetingSummary])
async def list_meetings(limit: int = 50) -> list[MeetingSummary]:
    return [MeetingSummary(**meeting) for meeting in meeting_store.list_meetings(limit)]


@app.get("/meetings/{meeting_id}", response_model=MeetingDetail)
async def meeting_detail(meeting_id: str) -> MeetingDetail:
    meeting = meeting_store.get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail=f"Meeting {meeting_id} not found")
    return MeetingDetail(**meeting)


@app.get("/followup", response_model=list[FollowUpItem])
async def followup(exclude_meeting: str | None = None, limit: int = 50) -> list[FollowUpItem]:
    """Action items from earlier meetings that nobody has closed yet."""
    return [
        FollowUpItem(**item) for item in meeting_store.open_items(exclude_meeting, limit)
    ]


@app.patch("/items/{item_id}", response_model=StoredActionItem)
async def update_item(item_id: str, changes: ItemUpdate) -> StoredActionItem:
    updated = meeting_store.update_item(
        item_id, changes.model_dump(exclude_unset=True, exclude_none=True)
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Action item {item_id} not found")
    return StoredActionItem(**updated)


@app.get("/search", response_model=SearchResponse)
async def search(q: str, limit: int = 20) -> SearchResponse:
    if not q.strip():
        raise HTTPException(status_code=422, detail="Search for something")
    return SearchResponse(query=q, **meeting_store.search(q, limit))


@app.get("/tickets")
async def list_tickets():
    return {"tickets": all_tickets()}


@app.get("/tickets/{ticket_id}")
async def ticket_detail(ticket_id: str):
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return ticket


@app.post("/corpus/index", response_model=CorpusIngestResponse)
async def index_corpus() -> CorpusIngestResponse:
    """Embed every known ticket so duplicate detection can match on meaning."""
    from rag.ingest import ingest_tickets

    try:
        indexed = await ingest_tickets(all_tickets())
    except Exception as e:
        logger.exception("Indexing the ticket corpus failed")
        raise HTTPException(status_code=502, detail=f"Indexing failed: {e}") from e

    return CorpusIngestResponse(
        indexed=indexed, collection=settings.QDRANT_COLLECTION, source="tickets"
    )


@app.post("/dispatch", response_model=DispatchBatchResponse)
async def dispatch(request: DispatchRequest) -> DispatchBatchResponse:
    if not request.approved_items:
        raise HTTPException(status_code=422, detail="Approve at least one action item first")
    results = await dispatch_items(request.approved_items, request.meeting_id)
    meeting_store.save_items(request.approved_items, request.meeting_id)
    created = sum(1 for item in results if item.status == "success")
    return DispatchBatchResponse(results=results, tickets_created=created)

import logging
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
    DispatchBatchResponse,
    DispatchRequest,
    ExtractionResult,
    ExtractRequest,
)
from services.ticket_store import all_tickets, get_ticket
from services.transcript_parser import parse_transcript

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_SUFFIXES = {".txt", ".vtt", ".srt", ".md"}
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="MeetingAgent",
    version="0.1.0",
    description="Turns meeting transcripts into summaries, decisions, owned action items and tracker tickets.",
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
        "ticket_count": len(all_tickets()),
    }


@app.post("/extract", response_model=ExtractionResult)
async def extract(request: ExtractRequest) -> ExtractionResult:
    return await _extract(
        request.transcript,
        meeting_id=request.meeting_id,
        meeting_date=request.meeting_date,
        attendees=request.attendees,
    )


@app.post("/extract/file", response_model=ExtractionResult)
async def extract_file(
    file: UploadFile = File(...),
    meeting_id: str | None = Form(None),
    meeting_date: str | None = Form(None),
    attendees: str = Form(""),
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
    )


async def _extract(
    raw_transcript: str,
    meeting_id: str | None,
    meeting_date: str | None,
    attendees: list[str],
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

    annotate_action_items(result.action_items)
    return result


@app.get("/tickets")
async def list_tickets():
    return {"tickets": all_tickets()}


@app.get("/tickets/{ticket_id}")
async def ticket_detail(ticket_id: str):
    ticket = get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return ticket


@app.post("/dispatch", response_model=DispatchBatchResponse)
async def dispatch(request: DispatchRequest) -> DispatchBatchResponse:
    if not request.approved_items:
        raise HTTPException(status_code=422, detail="Approve at least one action item first")
    results = await dispatch_items(request.approved_items, request.meeting_id)
    created = sum(1 for item in results if item.status == "success")
    return DispatchBatchResponse(results=results, tickets_created=created)

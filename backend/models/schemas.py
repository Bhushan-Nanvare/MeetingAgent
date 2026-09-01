from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class ActionItem(BaseModel):
    id: str
    task: str
    owner: str
    due_date: Optional[str] = None
    priority: Literal["high", "medium", "low"]
    status: Literal["new", "possible_duplicate", "approved", "rejected", "failed"] = "new"
    similar_tickets: List[dict] = Field(default_factory=list)
    source_segment: Optional[str] = None


class ExtractionResult(BaseModel):
    meeting_id: str
    summary: str
    decisions: List[str]
    action_items: List[ActionItem]
    transcript_length: int = 0
    extracted_at: str


class DispatchResult(BaseModel):
    item_id: str
    task: str
    jira_url: Optional[str] = None
    jira_ticket_id: Optional[str] = None
    email_draft_id: Optional[str] = None
    calendar_event_id: Optional[str] = None
    notion_row_id: Optional[str] = None
    status: Literal["success", "partial", "failed"]
    errors: List[str] = Field(default_factory=list)
    dispatched_at: str


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "transcribing", "extracting", "deduplicating", "complete", "error"]
    result: Optional[ExtractionResult] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class UploadResponse(BaseModel):
    job_id: str
    status: str


class DispatchRequest(BaseModel):
    approved_items: List[ActionItem]
    meeting_id: str
    summary: str = ""


class CorpusIngestRequest(BaseModel):
    source: Literal["jira", "notion"]
    data: List[dict]


class CorpusIngestResponse(BaseModel):
    indexed: int
    collection: str
    source: str

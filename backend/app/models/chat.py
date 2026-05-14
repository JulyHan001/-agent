from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


MemoryScope = Literal["session", "user"]
MemorySourceType = Literal["user", "tool", "inference", "manual"]
UserMemoryCandidateStatus = Literal["pending_confirmation", "approved", "rejected"]
AuthCodePurpose = Literal["register", "login"]


class ChatInputMessage(BaseModel):
    role: Literal["user"]
    content: str = Field(..., min_length=1)


class UserProfile(BaseModel):
    id: str
    phone: str | None = None
    display_name: str
    status: str = "active"
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def normalize_items(self) -> "UserProfile":
        self.phone = self.phone.strip() if self.phone else None
        self.display_name = self.display_name.strip()
        self.status = self.status.strip() or "active"
        return self


class AuthCodeSendRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11)
    purpose: AuthCodePurpose

    @model_validator(mode="after")
    def normalize_items(self) -> "AuthCodeSendRequest":
        self.phone = self.phone.strip()
        return self


class AuthCodeSendResponse(BaseModel):
    success: bool = True
    cooldown_seconds: int = 60
    expires_in_seconds: int = 300
    dev_code: str | None = None


class AuthVerificationCode(BaseModel):
    id: str
    phone: str
    purpose: AuthCodePurpose
    attempts: int = 0
    status: str = "pending"
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    last_sent_at: datetime


class AuthRegisterRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11)
    code: str = Field(..., min_length=4, max_length=8)
    display_name: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def normalize_items(self) -> "AuthRegisterRequest":
        self.phone = self.phone.strip()
        self.code = self.code.strip()
        self.display_name = self.display_name.strip()
        return self


class AuthLoginRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=11)
    code: str = Field(..., min_length=4, max_length=8)

    @model_validator(mode="after")
    def normalize_items(self) -> "AuthLoginRequest":
        self.phone = self.phone.strip()
        self.code = self.code.strip()
        return self


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserProfile


class ChatStructuredReply(BaseModel):
    summary: str = Field(..., min_length=1)
    analysis: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    follow_up_question: str | None = None

    @model_validator(mode="after")
    def normalize_items(self) -> "ChatStructuredReply":
        self.summary = self.summary.strip()
        self.analysis = [item.strip() for item in self.analysis if item.strip()]
        self.actions = [item.strip() for item in self.actions if item.strip()]
        self.follow_up_question = (
            self.follow_up_question.strip() if self.follow_up_question else None
        )
        return self


class JdAnalysisResult(BaseModel):
    summary: str = Field(..., min_length=1)
    responsibilities: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    match_focus: list[str] = Field(default_factory=list)
    resume_keywords: list[str] = Field(default_factory=list)
    interview_focus: list[str] = Field(default_factory=list)
    gap_analysis: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_items(self) -> "JdAnalysisResult":
        self.summary = self.summary.strip()
        self.responsibilities = [
            item.strip() for item in self.responsibilities if item.strip()
        ]
        self.required_skills = [
            item.strip() for item in self.required_skills if item.strip()
        ]
        self.preferred_skills = [
            item.strip() for item in self.preferred_skills if item.strip()
        ]
        self.keywords = [item.strip() for item in self.keywords if item.strip()]
        self.match_focus = [item.strip() for item in self.match_focus if item.strip()]
        self.resume_keywords = [
            item.strip() for item in self.resume_keywords if item.strip()
        ]
        self.interview_focus = [
            item.strip() for item in self.interview_focus if item.strip()
        ]
        self.gap_analysis = [
            item.strip() for item in self.gap_analysis if item.strip()
        ]
        return self


class ResumeTailorResult(BaseModel):
    summary: str = Field(..., min_length=1)
    tailored_summary: str = ""
    experience_bullets: list[str] = Field(default_factory=list)
    keyword_additions: list[str] = Field(default_factory=list)
    risk_alerts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_items(self) -> "ResumeTailorResult":
        self.summary = self.summary.strip()
        self.tailored_summary = self.tailored_summary.strip()
        self.experience_bullets = [
            item.strip() for item in self.experience_bullets if item.strip()
        ]
        self.keyword_additions = [
            item.strip() for item in self.keyword_additions if item.strip()
        ]
        self.risk_alerts = [item.strip() for item in self.risk_alerts if item.strip()]
        return self


class ToolCallRecord(BaseModel):
    tool_name: str = Field(..., min_length=1)
    trigger: Literal["auto", "manual", "suggested"]
    status: Literal["planned", "success", "failed", "skipped"] = "success"
    input_excerpt: str = ""
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""

    @model_validator(mode="after")
    def normalize_items(self) -> "ToolCallRecord":
        self.tool_name = self.tool_name.strip()
        self.input_excerpt = self.input_excerpt.strip()
        self.error_message = self.error_message.strip()
        if not isinstance(self.result, dict):
            self.result = {}
        return self


class SessionMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., min_length=1)
    structured: ChatStructuredReply | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)


def _normalize_memory_key(value: str) -> str:
    raw = value.strip().lower().replace("-", "_").replace(" ", "_")
    alias_map = {
        "job_target": "target_role",
        "target_job": "target_role",
        "goal_role": "target_role",
        "target_position": "target_role",
        "role_target": "target_role",
        "stack": "primary_stack",
        "tech_stack": "primary_stack",
        "technology_stack": "primary_stack",
        "primary_tech_stack": "primary_stack",
        "project_exp": "project_experience",
        "project": "project_experience",
        "projects": "project_experience",
        "experience_project": "project_experience",
        "job_stage": "job_search_stage",
        "search_stage": "job_search_stage",
        "focus": "current_focus",
        "study_focus": "current_focus",
        "prep_focus": "current_focus",
        "active_focus": "current_focus",
        "constraint": "constraint",
        "constraints": "constraint",
        "preference": "preference",
        "preferences": "preference",
    }
    return alias_map.get(raw, raw)


class MemoryFact(BaseModel):
    key: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)
    scope: MemoryScope = "session"
    source_type: MemorySourceType = "user"
    confidence: float = 0.0
    source_turn_start: int = 0
    source_turn_end: int = 0
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def normalize_items(self) -> "MemoryFact":
        self.key = _normalize_memory_key(self.key)
        self.label = self.label.strip()
        self.value = self.value.strip()
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.source_turn_start = max(0, self.source_turn_start)
        self.source_turn_end = max(self.source_turn_start, self.source_turn_end)
        return self


class MemoryConflict(BaseModel):
    key: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    previous_value: str = Field(..., min_length=1)
    incoming_value: str = Field(..., min_length=1)
    scope: MemoryScope = "session"
    source_type: MemorySourceType = "user"
    status: Literal["pending", "resolved", "ignored"] = "pending"
    resolution: str = ""
    confidence: float = 0.0
    source_turn_start: int = 0
    source_turn_end: int = 0
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def normalize_items(self) -> "MemoryConflict":
        self.key = _normalize_memory_key(self.key)
        self.label = self.label.strip()
        self.previous_value = self.previous_value.strip()
        self.incoming_value = self.incoming_value.strip()
        self.resolution = self.resolution.strip()
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.source_turn_start = max(0, self.source_turn_start)
        self.source_turn_end = max(self.source_turn_start, self.source_turn_end)
        return self


class SessionMemory(BaseModel):
    session_id: str
    summary: str = ""
    user_profile: list[str] = Field(default_factory=list)
    stable_profile: list[MemoryFact] = Field(default_factory=list)
    temporary_state: list[MemoryFact] = Field(default_factory=list)
    conflicts: list[MemoryConflict] = Field(default_factory=list)
    confidence: float = 0.0
    source_turn_start: int = 0
    source_turn_end: int = 0
    updated_at: datetime

    @model_validator(mode="after")
    def normalize_items(self) -> "SessionMemory":
        self.summary = self.summary.strip()
        self.user_profile = [item.strip() for item in self.user_profile if item.strip()]
        self.stable_profile = [
            item for item in self.stable_profile if item.label and item.value
        ]
        self.temporary_state = [
            item for item in self.temporary_state if item.label and item.value
        ]
        self.conflicts = [
            item
            for item in self.conflicts
            if item.label and item.previous_value and item.incoming_value
        ]
        if not self.user_profile:
            self.user_profile = [
                f"{item.label}: {item.value}" for item in self.stable_profile[:5]
            ]
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.source_turn_start = max(0, self.source_turn_start)
        self.source_turn_end = max(self.source_turn_start, self.source_turn_end)
        return self


class UserMemory(BaseModel):
    user_id: str
    summary: str = ""
    user_profile: list[str] = Field(default_factory=list)
    stable_profile: list[MemoryFact] = Field(default_factory=list)
    conflicts: list[MemoryConflict] = Field(default_factory=list)
    confidence: float = 0.0
    updated_at: datetime

    @model_validator(mode="after")
    def normalize_items(self) -> "UserMemory":
        self.summary = self.summary.strip()
        self.user_profile = [item.strip() for item in self.user_profile if item.strip()]
        self.stable_profile = [
            item for item in self.stable_profile if item.label and item.value
        ]
        self.conflicts = [
            item
            for item in self.conflicts
            if item.label and item.previous_value and item.incoming_value
        ]
        if not self.user_profile:
            self.user_profile = [
                f"{item.label}: {item.value}" for item in self.stable_profile[:5]
            ]
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        return self


class UserMemoryUpdate(BaseModel):
    summary: str = ""
    user_profile: list[str] = Field(default_factory=list)
    stable_profile: list[MemoryFact] = Field(default_factory=list)
    conflicts: list[MemoryConflict] = Field(default_factory=list)
    confidence: float = 0.0

    @model_validator(mode="after")
    def normalize_items(self) -> "UserMemoryUpdate":
        self.summary = self.summary.strip()
        self.user_profile = [item.strip() for item in self.user_profile if item.strip()]
        self.stable_profile = [
            item for item in self.stable_profile if item.label and item.value
        ]
        self.conflicts = [
            item
            for item in self.conflicts
            if item.label and item.previous_value and item.incoming_value
        ]
        if not self.user_profile:
            self.user_profile = [
                f"{item.label}: {item.value}" for item in self.stable_profile[:5]
            ]
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        return self


class UserMemoryCandidate(BaseModel):
    id: str
    user_id: str
    session_id: str | None = None
    key: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)
    previous_value: str = ""
    scope: MemoryScope = "user"
    source_type: MemorySourceType = "user"
    status: UserMemoryCandidateStatus = "pending_confirmation"
    reason: str = ""
    confidence: float = 0.0
    source_turn_start: int = 0
    source_turn_end: int = 0
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def normalize_items(self) -> "UserMemoryCandidate":
        self.key = _normalize_memory_key(self.key)
        self.label = self.label.strip()
        self.value = self.value.strip()
        self.previous_value = self.previous_value.strip()
        self.reason = self.reason.strip()
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.source_turn_start = max(0, self.source_turn_start)
        self.source_turn_end = max(self.source_turn_start, self.source_turn_end)
        return self


class UserMemoryCandidateCreate(BaseModel):
    user_id: str
    session_id: str | None = None
    key: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)
    previous_value: str = ""
    scope: MemoryScope = "user"
    source_type: MemorySourceType = "user"
    status: UserMemoryCandidateStatus = "pending_confirmation"
    reason: str = ""
    confidence: float = 0.0
    source_turn_start: int = 0
    source_turn_end: int = 0

    @model_validator(mode="after")
    def normalize_items(self) -> "UserMemoryCandidateCreate":
        self.key = _normalize_memory_key(self.key)
        self.label = self.label.strip()
        self.value = self.value.strip()
        self.previous_value = self.previous_value.strip()
        self.reason = self.reason.strip()
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.source_turn_start = max(0, self.source_turn_start)
        self.source_turn_end = max(self.source_turn_start, self.source_turn_end)
        return self


class UserMemorySyncPlan(BaseModel):
    memory: UserMemoryUpdate | None = None
    candidates: list[UserMemoryCandidateCreate] = Field(default_factory=list)


class SessionMemoryUpdate(BaseModel):
    summary: str = ""
    user_profile: list[str] = Field(default_factory=list)
    stable_profile: list[MemoryFact] = Field(default_factory=list)
    temporary_state: list[MemoryFact] = Field(default_factory=list)
    conflicts: list[MemoryConflict] = Field(default_factory=list)
    confidence: float = 0.0
    source_turn_start: int = 0
    source_turn_end: int = 0

    @model_validator(mode="after")
    def normalize_items(self) -> "SessionMemoryUpdate":
        self.summary = self.summary.strip()
        self.user_profile = [item.strip() for item in self.user_profile if item.strip()]
        self.stable_profile = [
            item for item in self.stable_profile if item.label and item.value
        ]
        self.temporary_state = [
            item for item in self.temporary_state if item.label and item.value
        ]
        self.conflicts = [
            item
            for item in self.conflicts
            if item.label and item.previous_value and item.incoming_value
        ]
        if not self.user_profile:
            self.user_profile = [
                f"{item.label}: {item.value}" for item in self.stable_profile[:5]
            ]
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.source_turn_start = max(0, self.source_turn_start)
        self.source_turn_end = max(self.source_turn_start, self.source_turn_end)
        return self


class JdAnalysisRequest(BaseModel):
    jd_text: str = Field(..., min_length=1)


class ResumeTailorRequest(BaseModel):
    resume_text: str = Field(..., min_length=1)
    jd_text: str = Field(..., min_length=1)


class UserMemoryFactRequest(BaseModel):
    key: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    value: str = Field(..., min_length=1)
    confidence: float = 1.0

    @model_validator(mode="after")
    def normalize_items(self) -> "UserMemoryFactRequest":
        self.key = _normalize_memory_key(self.key)
        self.label = self.label.strip()
        self.value = self.value.strip()
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        return self


class ChatRequest(BaseModel):
    session_id: str | None = None
    messages: list[ChatInputMessage] = Field(..., min_length=1)

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        session_id = payload.get("session_id") or payload.get("sessionId")
        if session_id is not None:
            payload["session_id"] = session_id

        if payload.get("messages"):
            return payload

        message = str(payload.get("message") or "").strip()
        if message:
            payload["messages"] = [{"role": "user", "content": message}]

        return payload

    def latest_user_message(self) -> str:
        return self.messages[-1].content


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    session_id: str
    message: SessionMessage
    usage: UsageInfo


class JdAnalysisResponse(BaseModel):
    result: JdAnalysisResult
    usage: UsageInfo


class ResumeTailorResponse(BaseModel):
    result: ResumeTailorResult
    usage: UsageInfo


class UserMemoryResponse(BaseModel):
    memory: UserMemory | None = None


class UserMemoryCandidatesResponse(BaseModel):
    candidates: list[UserMemoryCandidate] = Field(default_factory=list)


class UserMemoryCandidateActionResponse(BaseModel):
    candidate: UserMemoryCandidate
    memory: UserMemory | None = None


class LogoutResponse(BaseModel):
    success: bool = True


class ToolDefinition(BaseModel):
    name: str
    title: str
    description: str
    trigger_modes: list[Literal["auto", "manual", "suggested"]] = Field(
        default_factory=list
    )
    selection_mode: Literal["rule", "model", "hybrid"] = "rule"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class ToolChoice(BaseModel):
    tool_name: str = Field(..., min_length=1)
    trigger: Literal["auto", "manual", "suggested"] = "auto"
    reason: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_items(self) -> "ToolChoice":
        self.tool_name = self.tool_name.strip()
        self.reason = self.reason.strip()
        if not isinstance(self.arguments, dict):
            self.arguments = {}
        return self


class ToolSelectionResult(BaseModel):
    mode: Literal["rule", "model", "hybrid", "fallback"] = "rule"
    choices: list[ToolChoice] = Field(default_factory=list)
    fallback_reason: str = ""

    @model_validator(mode="after")
    def normalize_items(self) -> "ToolSelectionResult":
        self.fallback_reason = self.fallback_reason.strip()
        return self


class ToolExecutionLog(BaseModel):
    id: str
    user_id: str
    session_id: str
    tool_name: str
    trigger: Literal["auto", "manual", "suggested"]
    status: Literal["success", "failed", "skipped"]
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_json: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""
    created_at: datetime

    @model_validator(mode="after")
    def normalize_items(self) -> "ToolExecutionLog":
        self.tool_name = self.tool_name.strip()
        self.error_message = self.error_message.strip()
        if not isinstance(self.input_json, dict):
            self.input_json = {}
        if not isinstance(self.output_json, dict):
            self.output_json = {}
        return self


class ToolExecutionLogCreate(BaseModel):
    tool_name: str = Field(..., min_length=1)
    trigger: Literal["auto", "manual", "suggested"]
    status: Literal["success", "failed", "skipped"]
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_json: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ""

    @model_validator(mode="after")
    def normalize_items(self) -> "ToolExecutionLogCreate":
        self.tool_name = self.tool_name.strip()
        self.error_message = self.error_message.strip()
        if not isinstance(self.input_json, dict):
            self.input_json = {}
        if not isinstance(self.output_json, dict):
            self.output_json = {}
        return self


class SessionSummary(BaseModel):
    id: str
    user_id: str | None = None
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_preview: str = ""


class SessionDetail(BaseModel):
    id: str
    user_id: str | None = None
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[SessionMessage]
    memory: SessionMemory | None = None

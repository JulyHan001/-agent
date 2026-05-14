from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user
from app.models.chat import (
    ChatRequest,
    ChatResponse,
    JdAnalysisRequest,
    JdAnalysisResponse,
    ResumeTailorRequest,
    ResumeTailorResponse,
    SessionDetail,
    SessionSummary,
    ToolDefinition,
    ToolExecutionLog,
    UserProfile,
    UserMemoryCandidateActionResponse,
    UserMemoryCandidatesResponse,
    UserMemoryFactRequest,
    UserMemoryResponse,
)
from app.services.llm_service import llm_service
from app.services.session_service import session_service
from app.services.tool_service import tool_service

router = APIRouter()


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(user: UserProfile = Depends(get_current_user)) -> list[SessionSummary]:
    return session_service.list_session_summaries(user.id)


@router.get("/tools", response_model=list[ToolDefinition])
def list_tools() -> list[ToolDefinition]:
    return tool_service.list_definitions()


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: str,
    user: UserProfile = Depends(get_current_user),
) -> SessionDetail:
    return session_service.get_session(session_id, user.id)


@router.get("/sessions/{session_id}/tool-logs", response_model=list[ToolExecutionLog])
def list_session_tool_logs(
    session_id: str,
    user: UserProfile = Depends(get_current_user),
) -> list[ToolExecutionLog]:
    return session_service.list_tool_execution_logs(session_id, user.id)


@router.get("/memory/user", response_model=UserMemoryResponse)
def get_user_memory(user: UserProfile = Depends(get_current_user)) -> UserMemoryResponse:
    return UserMemoryResponse(memory=session_service.get_user_memory(user.id))


@router.put("/memory/user", response_model=UserMemoryResponse)
def upsert_user_memory_fact(
    request: UserMemoryFactRequest,
    user: UserProfile = Depends(get_current_user),
) -> UserMemoryResponse:
    memory = session_service.upsert_user_memory_fact(request, user.id)
    return UserMemoryResponse(memory=memory)


@router.delete("/memory/user/{key}", response_model=UserMemoryResponse)
def delete_user_memory_fact(
    key: str,
    user: UserProfile = Depends(get_current_user),
) -> UserMemoryResponse:
    memory = session_service.delete_user_memory_fact(key, user.id)
    return UserMemoryResponse(memory=memory)


@router.get("/memory/user/candidates", response_model=UserMemoryCandidatesResponse)
def list_user_memory_candidates(
    user: UserProfile = Depends(get_current_user),
) -> UserMemoryCandidatesResponse:
    return UserMemoryCandidatesResponse(
        candidates=session_service.list_user_memory_candidates(user.id)
    )


@router.post(
    "/memory/user/candidates/{candidate_id}/approve",
    response_model=UserMemoryCandidateActionResponse,
)
def approve_user_memory_candidate(
    candidate_id: str,
    user: UserProfile = Depends(get_current_user),
) -> UserMemoryCandidateActionResponse:
    candidate, memory = session_service.approve_user_memory_candidate(candidate_id, user.id)
    return UserMemoryCandidateActionResponse(candidate=candidate, memory=memory)


@router.post(
    "/memory/user/candidates/{candidate_id}/reject",
    response_model=UserMemoryCandidateActionResponse,
)
def reject_user_memory_candidate(
    candidate_id: str,
    user: UserProfile = Depends(get_current_user),
) -> UserMemoryCandidateActionResponse:
    candidate, memory = session_service.reject_user_memory_candidate(candidate_id, user.id)
    return UserMemoryCandidateActionResponse(candidate=candidate, memory=memory)


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    user: UserProfile = Depends(get_current_user),
) -> ChatResponse:
    try:
        session = session_service.ensure_session(
            session_id=request.session_id,
            first_user_message=request.latest_user_message(),
            user_id=user.id,
        )

        for message in request.messages:
            session_service.append_user_message(session.id, message.content, user.id)

        context_messages = session_service.build_context_messages(session.id, user.id)
        memory = session_service.get_memory(session.id, user.id)
        user_memory = session_service.get_user_memory_by_session(session.id, user.id)
        latest_user_message = request.latest_user_message()
        tool_calls = []
        try:
            selection = tool_service.select_tools(
                latest_user_message,
                context_messages=context_messages,
                user_memory=user_memory,
            )
            tool_calls, tool_logs, _ = tool_service.execute_choices(selection.choices)
            session_service.record_tool_execution_logs(session.id, tool_logs, user.id)
        except Exception:
            tool_calls = []

        reply_message, usage = llm_service.generate_reply(
            context_messages,
            memory=memory,
            user_memory=user_memory,
            tool_calls=tool_calls,
        )
        session_service.append_assistant_message(
            session.id,
            reply_message.content,
            user_id=user.id,
            structured=reply_message.structured,
            tool_calls=reply_message.tool_calls,
        )
        session_service.refresh_memory(session.id, user.id)

        return ChatResponse(session_id=session.id, message=reply_message, usage=usage)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Model request failed: {exc}") from exc


@router.post("/analyze/jd", response_model=JdAnalysisResponse)
def analyze_jd(request: JdAnalysisRequest) -> JdAnalysisResponse:
    try:
        result, usage = llm_service.analyze_jd(request.jd_text)
        return JdAnalysisResponse(result=result, usage=usage)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"JD analysis failed: {exc}") from exc


@router.post("/tailor/resume", response_model=ResumeTailorResponse)
def tailor_resume(request: ResumeTailorRequest) -> ResumeTailorResponse:
    try:
        tool_call, usage = tool_service.run_tool(
            "resume_tailor",
            {
                "resume_text": request.resume_text,
                "jd_text": request.jd_text,
            },
        )
        return ResumeTailorResponse(
            result=tool_call.result,
            usage=usage,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Resume tailor failed: {exc}") from exc

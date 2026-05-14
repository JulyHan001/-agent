from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from app.models.chat import (
    JdAnalysisResult,
    ResumeTailorResult,
    SessionMessage,
    ToolCallRecord,
    ToolChoice,
    ToolDefinition,
    ToolExecutionLogCreate,
    ToolSelectionResult,
    UsageInfo,
    UserMemory,
)
from app.services.llm_service import llm_service


ToolTrigger = Literal["auto", "manual", "suggested"]
ToolHandler = Callable[[dict], tuple[dict, UsageInfo]]
ToolMatcher = Callable[[str], bool]


@dataclass(frozen=True)
class RegisteredTool:
    definition: ToolDefinition
    auto_trigger: ToolTrigger | None
    should_run: ToolMatcher | None
    run: ToolHandler


class ToolService:
    def __init__(self) -> None:
        self._tool_map: dict[str, RegisteredTool] = {}
        self._register_defaults()

    def select_tools(
        self,
        user_message: str,
        context_messages: list[SessionMessage] | None = None,
        user_memory: UserMemory | None = None,
    ) -> ToolSelectionResult:
        try:
            model_result = llm_service.select_tools(
                user_message=user_message,
                tool_definitions=self.list_definitions(),
                context_messages=context_messages or [],
                user_memory=user_memory,
            )
        except Exception as exc:
            return self._rule_selection_with_fallback(user_message, str(exc))

        rule_choices = self._rule_choices(user_message)
        merged_choices = self._merge_choices(model_result.choices, rule_choices)

        if merged_choices:
            return ToolSelectionResult(
                mode="hybrid" if model_result.choices and rule_choices else model_result.mode,
                choices=merged_choices,
                fallback_reason=model_result.fallback_reason,
            )

        if model_result.choices:
            return model_result

        if rule_choices:
            return ToolSelectionResult(
                mode="fallback",
                choices=rule_choices,
                fallback_reason=model_result.fallback_reason or "rule fallback applied",
            )

        return model_result

    def execute_choices(
        self,
        choices: list[ToolChoice],
    ) -> tuple[list[ToolCallRecord], list[ToolExecutionLogCreate], UsageInfo]:
        records: list[ToolCallRecord] = []
        logs: list[ToolExecutionLogCreate] = []
        total_usage = UsageInfo()

        for choice in choices:
            record, usage, log = self._execute_choice(choice)
            records.append(record)
            logs.append(log)
            total_usage = UsageInfo(
                prompt_tokens=total_usage.prompt_tokens + usage.prompt_tokens,
                completion_tokens=total_usage.completion_tokens + usage.completion_tokens,
                total_tokens=total_usage.total_tokens + usage.total_tokens,
            )

        return records, logs, total_usage

    def run_tool(
        self,
        name: str,
        payload: dict,
        trigger: ToolTrigger = "manual",
    ) -> tuple[ToolCallRecord, UsageInfo]:
        tool = self._tool_map.get(name)
        if tool is None:
            raise ValueError(f"Tool not found: {name}")

        result, usage = tool.run(payload)
        return (
            ToolCallRecord(
                tool_name=tool.definition.name,
                trigger=trigger,
                status="success",
                input_excerpt=self._build_excerpt(payload),
                result=result,
            ),
            usage,
        )

    def list_definitions(self) -> list[ToolDefinition]:
        return [tool.definition for tool in self._tool_map.values()]

    def get_definition(self, name: str) -> ToolDefinition | None:
        tool = self._tool_map.get(name)
        return tool.definition if tool else None

    def _execute_choice(
        self,
        choice: ToolChoice,
    ) -> tuple[ToolCallRecord, UsageInfo, ToolExecutionLogCreate]:
        tool = self._tool_map.get(choice.tool_name)
        if tool is None:
            record = ToolCallRecord(
                tool_name=choice.tool_name,
                trigger=choice.trigger,
                status="skipped",
                input_excerpt=self._build_excerpt(choice.arguments),
                result={},
                error_message="Tool not registered.",
            )
            return (
                record,
                UsageInfo(),
                ToolExecutionLogCreate(
                    tool_name=choice.tool_name,
                    trigger=choice.trigger,
                    status="skipped",
                    input_json=choice.arguments,
                    output_json={},
                    error_message=record.error_message,
                ),
            )

        try:
            result, usage = tool.run(choice.arguments)
            record = ToolCallRecord(
                tool_name=tool.definition.name,
                trigger=choice.trigger,
                status="success",
                input_excerpt=self._build_excerpt(choice.arguments),
                result=result,
            )
            log = ToolExecutionLogCreate(
                tool_name=tool.definition.name,
                trigger=choice.trigger,
                status="success",
                input_json=choice.arguments,
                output_json=result,
            )
            return record, usage, log
        except Exception as exc:
            record = ToolCallRecord(
                tool_name=tool.definition.name,
                trigger=choice.trigger,
                status="failed",
                input_excerpt=self._build_excerpt(choice.arguments),
                result={},
                error_message=str(exc),
            )
            log = ToolExecutionLogCreate(
                tool_name=tool.definition.name,
                trigger=choice.trigger,
                status="failed",
                input_json=choice.arguments,
                output_json={},
                error_message=str(exc),
            )
            return record, UsageInfo(), log

    def _rule_selection_with_fallback(
        self,
        user_message: str,
        reason: str,
    ) -> ToolSelectionResult:
        return ToolSelectionResult(
            mode="fallback",
            choices=self._rule_choices(user_message),
            fallback_reason=reason,
        )

    def _rule_choices(self, user_message: str) -> list[ToolChoice]:
        choices: list[ToolChoice] = []
        for tool in self._tool_map.values():
            if tool.auto_trigger is None or tool.should_run is None:
                continue
            if not tool.should_run(user_message):
                continue

            payload = self._build_auto_payload(tool.definition.name, user_message)
            choices.append(
                ToolChoice(
                    tool_name=tool.definition.name,
                    trigger=tool.auto_trigger,
                    reason="matched built-in auto trigger rules",
                    arguments=payload,
                )
            )
        return choices

    def _register_defaults(self) -> None:
        self._register(
            RegisteredTool(
                definition=ToolDefinition(
                    name="analyze_jd",
                    title="JD 分析",
                    description="提取岗位职责、要求、简历关键词、面试重点和能力缺口。",
                    trigger_modes=["auto", "manual"],
                    selection_mode="hybrid",
                    input_schema={
                        "type": "object",
                        "required": ["jd_text"],
                        "properties": {
                            "jd_text": {"type": "string", "description": "岗位 JD 原文"}
                        },
                    },
                    output_schema=self._schema_for_jd(),
                ),
                auto_trigger="auto",
                should_run=llm_service.should_auto_analyze_jd,
                run=self._run_analyze_jd,
            )
        )
        self._register(
            RegisteredTool(
                definition=ToolDefinition(
                    name="resume_tailor",
                    title="简历定制",
                    description="基于简历内容和目标 JD，输出定制化改写建议、关键词补齐和投递风险提示。",
                    trigger_modes=["manual", "suggested"],
                    selection_mode="model",
                    input_schema={
                        "type": "object",
                        "required": ["resume_text", "jd_text"],
                        "properties": {
                            "resume_text": {"type": "string", "description": "当前简历原文"},
                            "jd_text": {"type": "string", "description": "目标岗位 JD 原文"},
                        },
                    },
                    output_schema=self._schema_for_resume_tailor(),
                ),
                auto_trigger=None,
                should_run=None,
                run=self._run_resume_tailor,
            )
        )

    def _register(self, tool: RegisteredTool) -> None:
        self._tool_map[tool.definition.name] = tool

    @staticmethod
    def _run_analyze_jd(payload: dict) -> tuple[dict, UsageInfo]:
        jd_text = str(payload.get("jd_text") or payload.get("content") or "").strip()
        result, usage = llm_service.analyze_jd(jd_text)
        return ToolService._dump_jd_result(result), usage

    @staticmethod
    def _run_resume_tailor(payload: dict) -> tuple[dict, UsageInfo]:
        resume_text = str(payload.get("resume_text") or "").strip()
        jd_text = str(payload.get("jd_text") or "").strip()
        result, usage = llm_service.tailor_resume(resume_text, jd_text)
        return ToolService._dump_resume_tailor_result(result), usage

    @staticmethod
    def _dump_jd_result(result: JdAnalysisResult) -> dict:
        return result.model_dump(mode="json")

    @staticmethod
    def _dump_resume_tailor_result(result: ResumeTailorResult) -> dict:
        return result.model_dump(mode="json")

    @staticmethod
    def _build_auto_payload(tool_name: str, user_message: str) -> dict:
        if tool_name == "analyze_jd":
            return {"jd_text": user_message}
        return {"content": user_message}

    @staticmethod
    def _merge_choices(
        primary: list[ToolChoice],
        secondary: list[ToolChoice],
    ) -> list[ToolChoice]:
        merged: dict[tuple[str, str], ToolChoice] = {}
        for choice in [*primary, *secondary]:
            key = (choice.tool_name, choice.trigger)
            if key not in merged:
                merged[key] = choice
        return list(merged.values())

    @staticmethod
    def _build_excerpt(payload: dict) -> str:
        raw_parts = [
            str(payload.get("content") or ""),
            str(payload.get("jd_text") or ""),
            str(payload.get("resume_text") or ""),
        ]
        raw = " ".join(part.strip() for part in raw_parts if part.strip())
        return " ".join(raw.split())[:160]

    @staticmethod
    def _schema_for_jd() -> dict:
        return {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "responsibilities": {"type": "array", "items": {"type": "string"}},
                "required_skills": {"type": "array", "items": {"type": "string"}},
                "preferred_skills": {"type": "array", "items": {"type": "string"}},
                "keywords": {"type": "array", "items": {"type": "string"}},
                "match_focus": {"type": "array", "items": {"type": "string"}},
                "resume_keywords": {"type": "array", "items": {"type": "string"}},
                "interview_focus": {"type": "array", "items": {"type": "string"}},
                "gap_analysis": {"type": "array", "items": {"type": "string"}},
            },
        }

    @staticmethod
    def _schema_for_resume_tailor() -> dict:
        return {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "tailored_summary": {"type": "string"},
                "experience_bullets": {"type": "array", "items": {"type": "string"}},
                "keyword_additions": {"type": "array", "items": {"type": "string"}},
                "risk_alerts": {"type": "array", "items": {"type": "string"}},
            },
        }


tool_service = ToolService()

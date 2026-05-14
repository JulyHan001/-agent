import json
import re

from openai import OpenAI

from app.core.config import settings
from app.core.prompts import (
    build_chat_system_prompt,
    build_jd_analysis_prompt,
    build_resume_tailor_prompt,
    fallback_jd_analysis,
    fallback_resume_tailor,
    render_structured_reply,
)
from app.models.chat import (
    ChatStructuredReply,
    JdAnalysisResult,
    ResumeTailorResult,
    SessionMemory,
    SessionMessage,
    ToolCallRecord,
    ToolChoice,
    ToolDefinition,
    ToolSelectionResult,
    UsageInfo,
    UserMemory,
)


JD_AUTO_TRIGGER_MARKERS = [
    "jd",
    "岗位：",
    "职责：",
    "要求：",
    "岗位职责",
    "岗位要求",
    "任职要求",
    "职位描述",
    "职位要求",
    "工作职责",
    "job description",
    "responsibilities",
    "requirements",
    "qualifications",
]


class LLMService:
    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
        )

    def generate_reply(
        self,
        messages: list[SessionMessage],
        memory: SessionMemory | None = None,
        user_memory: UserMemory | None = None,
        tool_calls: list[ToolCallRecord] | None = None,
    ) -> tuple[SessionMessage, UsageInfo]:
        if settings.mock_llm:
            structured_reply = self._mock_structured_reply(messages, user_memory, tool_calls)
            return SessionMessage(
                role="assistant",
                content=render_structured_reply(structured_reply),
                structured=structured_reply,
                tool_calls=tool_calls or [],
            ), UsageInfo()

        response = self.client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": build_chat_system_prompt(
                        memory,
                        user_memory=user_memory,
                        tool_calls=tool_calls,
                    ),
                },
                *[
                    {"role": message.role, "content": message.content}
                    for message in messages
                ],
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )

        raw_reply = response.choices[0].message.content or ""
        structured_reply = self._parse_structured_reply(raw_reply)
        usage = response.usage

        return SessionMessage(
            role="assistant",
            content=render_structured_reply(structured_reply),
            structured=structured_reply,
            tool_calls=tool_calls or [],
        ), UsageInfo(
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
        )

    def analyze_jd(self, jd_text: str) -> tuple[JdAnalysisResult, UsageInfo]:
        if settings.mock_llm:
            return self._mock_jd_analysis(jd_text), UsageInfo()

        response = self.client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": build_jd_analysis_prompt()},
                {"role": "user", "content": jd_text},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        raw_reply = response.choices[0].message.content or ""
        usage = response.usage

        try:
            parsed = json.loads(raw_reply.strip())
            result = JdAnalysisResult.model_validate(parsed)
        except Exception:
            result = fallback_jd_analysis()

        if not result.resume_keywords:
            result.resume_keywords = list(result.keywords[:6] or result.required_skills[:6])
        if not result.interview_focus:
            result.interview_focus = list(result.match_focus[:6] or result.required_skills[:6])
        if not result.gap_analysis:
            result.gap_analysis = self._build_gap_analysis_fallback(result)

        return result, UsageInfo(
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
        )

    def tailor_resume(
        self,
        resume_text: str,
        jd_text: str,
    ) -> tuple[ResumeTailorResult, UsageInfo]:
        if settings.mock_llm:
            return self._mock_resume_tailor(resume_text, jd_text), UsageInfo()

        response = self.client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": build_resume_tailor_prompt()},
                {
                    "role": "user",
                    "content": f"简历内容：\n{resume_text.strip()}\n\n目标 JD：\n{jd_text.strip()}",
                },
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        raw_reply = response.choices[0].message.content or ""
        usage = response.usage

        try:
            parsed = json.loads(raw_reply.strip())
            result = ResumeTailorResult.model_validate(parsed)
        except Exception:
            result = fallback_resume_tailor()

        if not result.keyword_additions:
            result.keyword_additions = self._extract_keyword_additions(
                resume_text,
                jd_text,
            )
        if not result.risk_alerts:
            result.risk_alerts = self._extract_resume_risks(resume_text, jd_text)

        return result, UsageInfo(
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
        )

    def select_tools(
        self,
        user_message: str,
        tool_definitions: list[ToolDefinition],
        context_messages: list[SessionMessage] | None = None,
        user_memory: UserMemory | None = None,
    ) -> ToolSelectionResult:
        if settings.mock_llm:
            return self._mock_tool_selection(user_message, tool_definitions)

        choices: list[ToolChoice] = []
        if self.should_auto_analyze_jd(user_message):
            choices.append(
                ToolChoice(
                    tool_name="analyze_jd",
                    trigger="auto",
                    reason="message matches JD-like content",
                    arguments={"jd_text": user_message},
                )
            )

        return ToolSelectionResult(
            mode="model" if choices else "fallback",
            choices=choices,
            fallback_reason="" if choices else "model selection returned no tool",
        )

    @staticmethod
    def should_auto_analyze_jd(message: str) -> bool:
        normalized = message.strip()
        if len(normalized) < 60:
            return False

        lowered = normalized.lower()
        matched_markers = sum(1 for marker in JD_AUTO_TRIGGER_MARKERS if marker in lowered)
        bullet_like_count = len(re.findall(r"(\n[-*•]|\n\d+[.)、])", normalized))
        line_count = len([line for line in normalized.splitlines() if line.strip()])

        return (
            matched_markers >= 2
            or (matched_markers >= 1 and bullet_like_count >= 2)
            or ("岗位：" in normalized and "要求：" in normalized and line_count >= 3)
        )

    def _parse_structured_reply(self, raw_reply: str) -> ChatStructuredReply:
        content = raw_reply.strip()

        try:
            parsed = json.loads(content)
            return ChatStructuredReply.model_validate(parsed)
        except Exception:
            fallback = content or "我先给你一个简短建议。"
            return ChatStructuredReply(
                summary=fallback,
                analysis=[],
                actions=[],
                follow_up_question=None,
            )

    @staticmethod
    def _build_gap_analysis_fallback(result: JdAnalysisResult) -> list[str]:
        fallbacks: list[str] = []

        for item in result.required_skills:
            text = item.strip()
            if not text:
                continue
            fallbacks.append(f"如果这项要求缺少实际项目经验，需要尽快补齐：{text}")
            if len(fallbacks) >= 4:
                break

        if not fallbacks and result.match_focus:
            for item in result.match_focus[:4]:
                fallbacks.append(f"需要重点准备并验证掌握程度：{item}")

        return fallbacks

    @staticmethod
    def _extract_keyword_additions(resume_text: str, jd_text: str) -> list[str]:
        lowered_resume = resume_text.lower()
        candidates = [
            "Spring Boot",
            "MySQL",
            "Redis",
            "消息队列",
            "Linux",
            "微服务",
            "SQL 优化",
        ]
        return [
            item
            for item in candidates
            if item.lower() in jd_text.lower() and item.lower() not in lowered_resume
        ][:6]

    @staticmethod
    def _extract_resume_risks(resume_text: str, jd_text: str) -> list[str]:
        risks: list[str] = []
        lowered_resume = resume_text.lower()
        checks = [
            ("消息队列", "简历里如果没有消息队列实践，投递该 JD 时会显得分布式中间件准备不足。"),
            ("linux", "简历里如果缺少 Linux 开发或排障经历，容易在面试中被追问实际操作能力。"),
            ("mysql", "如果简历没有索引优化或 SQL 调优案例，数据库能力的说服力会偏弱。"),
            ("spring boot", "如果 Spring Boot 只停留在技能栏，没有项目要点支撑，匹配度会被拉低。"),
        ]
        lowered_jd = jd_text.lower()
        for marker, message in checks:
            if marker in lowered_jd and marker not in lowered_resume:
                risks.append(message)
        return risks[:6]

    @staticmethod
    def _mock_structured_reply(
        messages: list[SessionMessage],
        user_memory: UserMemory | None,
        tool_calls: list[ToolCallRecord] | None,
    ) -> ChatStructuredReply:
        latest_user = next(
            (message.content for message in reversed(messages) if message.role == "user"),
            "",
        )
        has_jd_tool = any(
            tool_call.tool_name == "analyze_jd" for tool_call in (tool_calls or [])
        )

        if user_memory and "不重复介绍背景" in latest_user:
            profile = ", ".join(
                f"{item.label}{item.value}" for item in user_memory.stable_profile[:2]
            ) or "之前的长期背景"
            return ChatStructuredReply(
                summary=f"我记得你的长期背景，当前可以直接沿着 {profile} 继续准备。",
                analysis=["这是跨会话读取到的用户长期记忆。"],
                actions=["继续基于既有背景推进面试准备，不需要重复自我介绍。"],
                follow_up_question=None,
            )

        if has_jd_tool:
            return ChatStructuredReply(
                summary="已识别为 JD 输入，并自动完成岗位分析。",
                analysis=[
                    "工具链路已自动触发 analyze_jd。",
                    "当前响应包含结构化分析和工具结果。",
                ],
                actions=[
                    "查看 JD 分析模块。",
                    "继续验证会话记忆和长期记忆是否按预期刷新。",
                ],
                follow_up_question=None,
            )

        if "纠正一下" in latest_user:
            return ChatStructuredReply(
                summary="已记录你的最新纠正信息，并会优先采用更新后的短期重点。",
                analysis=["这类输入会帮助系统更新短期状态并触发冲突处理。"],
                actions=["后续建议会优先围绕消息队列和 Linux 展开。"],
                follow_up_question=None,
            )

        return ChatStructuredReply(
            summary="已记录你的求职背景，并继续推进当前对话。",
            analysis=["当前输入已进入会话上下文，可用于后续记忆提炼。"],
            actions=["继续提供更具体的问题，我会基于当前背景给出建议。"],
            follow_up_question=None,
        )

    def _mock_jd_analysis(self, jd_text: str) -> JdAnalysisResult:
        required_skills = []
        if "Java" in jd_text:
            required_skills.append("熟悉 Java")
        if "Spring Boot" in jd_text:
            required_skills.append("了解 Spring Boot")
        if "MySQL" in jd_text:
            required_skills.append("掌握 MySQL 与 SQL 优化")
        if "Redis" in jd_text:
            required_skills.append("了解 Redis")
        if "Linux" in jd_text:
            required_skills.append("具备 Linux 使用经验")
        if "消息队列" in jd_text:
            required_skills.append("了解消息队列")

        if not required_skills:
            required_skills = ["理解岗位核心技术要求"]

        return JdAnalysisResult(
            summary="这是一个以后端开发实习为目标的岗位，强调接口开发、数据库优化和基础中间件能力。",
            responsibilities=[
                "参与业务后台接口开发与维护",
                "配合完成数据库设计、性能优化与问题排查",
                "参与模块开发与单元测试",
            ],
            required_skills=required_skills,
            preferred_skills=["有实习经历优先", "具备良好沟通与责任心"],
            keywords=["Java", "Spring Boot", "MySQL", "Redis", "消息队列", "Linux"],
            match_focus=[
                "突出后端项目经历",
                "补齐消息队列和 Linux 相关表达",
                "准备数据库优化案例",
            ],
            resume_keywords=[
                "Spring Boot 接口开发",
                "MySQL 索引与 SQL 优化",
                "Redis 缓存设计",
                "Linux 环境排查",
            ],
            interview_focus=[
                "Java 基础与集合并发",
                "Spring Boot 核心机制",
                "MySQL 索引与慢查询优化",
                "消息队列使用场景",
            ],
            gap_analysis=[
                "如果缺少消息队列实践，需要补一个可讲的异步场景。",
                "如果 Linux 经验偏弱，建议补充排障或部署案例。",
            ],
        )

    def _mock_resume_tailor(
        self,
        resume_text: str,
        jd_text: str,
    ) -> ResumeTailorResult:
        return ResumeTailorResult(
            summary="已生成一版最小可执行的简历定制建议。",
            tailored_summary="聚焦后端开发实习目标，强调 Spring Boot、MySQL、Redis 和项目落地能力。",
            experience_bullets=[
                "将项目描述改写为接口开发、缓存设计、性能优化三个维度。",
                "补充 Linux 部署或排障相关经历表达。",
            ],
            keyword_additions=self._extract_keyword_additions(resume_text, jd_text)
            or ["消息队列", "Linux", "SQL 优化"],
            risk_alerts=self._extract_resume_risks(resume_text, jd_text)
            or ["如果没有消息队列实践，建议至少准备一个模拟异步处理案例。"],
        )

    def _mock_tool_selection(
        self,
        user_message: str,
        tool_definitions: list[ToolDefinition],
    ) -> ToolSelectionResult:
        available = {item.name for item in tool_definitions}
        choices: list[ToolChoice] = []

        if "analyze_jd" in available and self.should_auto_analyze_jd(user_message):
            choices.append(
                ToolChoice(
                    tool_name="analyze_jd",
                    trigger="auto",
                    reason="mock model recognized JD-like content",
                    arguments={"jd_text": user_message},
                )
            )

        return ToolSelectionResult(
            mode="model" if choices else "fallback",
            choices=choices,
            fallback_reason="" if choices else "mock model selected no tool",
        )


llm_service = LLMService()

from app.core.prompts.base import BASE_ROLE_PROMPT, RESPONSE_RULES_PROMPT
from app.models.chat import (
    ChatStructuredReply,
    JdAnalysisResult,
    ResumeTailorResult,
    SessionMemory,
    SessionMemoryUpdate,
    ToolCallRecord,
    UserMemory,
)

CHAT_OUTPUT_PROMPT = """
你必须只返回一个合法 JSON 对象，不要返回 Markdown，不要加代码块，不要补充解释文字。JSON 结构要求：
{
  "summary": "一句话总结当前回答",
  "analysis": ["2 到 4 条分析要点"],
  "actions": ["1 到 4 条下一步建议"],
  "follow_up_question": "如果缺少关键信息，需要追问的问题；否则为 null"
}

字段约束：
1. summary 必须是字符串，不能为空。
2. analysis 必须是字符串数组，没有内容时返回空数组。
3. actions 必须是字符串数组，没有内容时返回空数组。
4. follow_up_question 必须是字符串或 null。
5. 如果用户只是简单追问，也仍然返回上面 JSON 结构。
6. 用户使用中文时，所有字段内容使用中文。
""".strip()

MEMORY_UPDATE_PROMPT = """
你需要根据会话历史，输出该会话的分层记忆。目标是避免临时状态覆盖稳定画像，并识别冲突信息。
你必须只返回一个合法 JSON 对象，不要返回 Markdown，不要加代码块，不要补充解释文字。JSON 结构要求：
{
  "summary": "3 句话以内的会话摘要，聚焦当前目标、进展和待解决问题",
  "user_profile": ["兼容旧前端的扁平画像标签"],
  "stable_profile": [
    {
      "key": "target_role",
      "label": "目标岗位",
      "value": "后端开发实习",
      "confidence": 0.88,
      "source_turn_start": 1,
      "source_turn_end": 3
    }
  ],
  "temporary_state": [
    {
      "key": "current_focus",
      "label": "当前重点",
      "value": "补消息队列和 Linux",
      "confidence": 0.78,
      "source_turn_start": 3,
      "source_turn_end": 4
    }
  ],
  "conflicts": [
    {
      "key": "target_role",
      "label": "目标岗位",
      "previous_value": "后端开发实习",
      "incoming_value": "转前端开发",
      "status": "pending",
      "resolution": "用户最近表达了新的转向，但需要后续确认是否长期切换",
      "confidence": 0.66,
      "source_turn_start": 5,
      "source_turn_end": 5
    }
  ],
  "confidence": 0.0,
  "source_turn_start": 1,
  "source_turn_end": 4
}

约束：
1. stable_profile 只写相对稳定、后续多轮仍然有用的信息，例如目标岗位、主技术栈、项目经历、长期偏好。
2. temporary_state 只写短期状态，例如当前投递阶段、最近准备重点、这周的计划、正在补的知识点。
3. conflicts 只在新旧信息明显冲突时填写；若用户明确表示“现在改成”“不再是”“纠正一下”，可以直接将 status 设为 resolved，并在 resolution 里说明。
4. 不确定的信息不要写入；不确定越多，confidence 越低。
5. stable_profile、temporary_state、conflicts 各自最多 5 条，允许为空数组。
6. summary、user_profile、label、value、resolution 都必须使用中文。
7. confidence 取值 0 到 1；信息明确、重复出现、可直接引用时更高。
8. source_turn_start/source_turn_end 表示本次记忆主要依据的用户轮次区间，至少为 1。
""".strip()

JD_ANALYSIS_PROMPT = """
你是求职助手中的岗位分析模块。你需要从用户提供的 JD 中提炼最关键信息，并进一步生成可直接用于简历和面试准备的结果。
你必须只返回一个合法 JSON 对象，不要返回 Markdown，不要加代码块，不要补充解释文字。JSON 结构要求：
{
  "summary": "对这个岗位的简短概括",
  "responsibilities": ["岗位职责要点"],
  "required_skills": ["明确要求的技能或经验"],
  "preferred_skills": ["加分项或优先项"],
  "keywords": ["适合简历和面试准备的关键词"],
  "match_focus": ["候选人准备时最该优先补齐或强调的点"],
  "resume_keywords": ["建议直接写进简历项目描述或技能栏的关键词"],
  "interview_focus": ["建议重点准备的面试主题或问题方向"],
  "gap_analysis": ["从 JD 出发，候选人可能存在的能力缺口或待补齐项"]
}

约束：
1. 所有字段都必须返回，缺失时返回空数组。
2. 提炼信息时优先依据 JD 原文，不要脑补具体项目经历。
3. 输出使用中文，措辞简洁，适合前端直接展示。
4. responsibilities、required_skills、preferred_skills、keywords、match_focus、resume_keywords、interview_focus、gap_analysis 各返回 2 到 6 条为宜。
5. resume_keywords 更偏向简历措辞；interview_focus 更偏向面试准备；gap_analysis 更偏向待补能力。
""".strip()

RESUME_TAILOR_PROMPT = """
你是求职助手中的简历定制模块。你需要结合用户提供的简历内容和目标 JD，输出最小可执行的简历定制建议。
你必须只返回一个合法 JSON 对象，不要返回 Markdown，不要加代码块，不要补充解释文字。JSON 结构要求：
{
  "summary": "一句话概括当前简历与 JD 的匹配调整方向",
  "tailored_summary": "建议放在简历开头的 2 到 3 句中文总结",
  "experience_bullets": ["建议改写进项目/经历描述的要点"],
  "keyword_additions": ["建议补进简历的关键词"],
  "risk_alerts": ["当前简历投递这个 JD 的主要风险或缺口"]
}

约束：
1. 所有字段都必须返回，没有内容时返回空数组或空字符串。
2. 不要虚构用户没有提供的经历，只能做重写、强调和排序建议。
3. 输出使用中文，适合前端直接展示。
4. experience_bullets、keyword_additions、risk_alerts 各返回 2 到 6 条为宜。
5. experience_bullets 更偏项目改写；keyword_additions 更偏关键词补齐；risk_alerts 更偏投递风险提示。
""".strip()


def build_chat_system_prompt(
    memory: SessionMemory | None = None,
    user_memory: UserMemory | None = None,
    tool_calls: list[ToolCallRecord] | None = None,
) -> str:
    sections = [BASE_ROLE_PROMPT, RESPONSE_RULES_PROMPT]

    if user_memory and (
        user_memory.summary
        or user_memory.user_profile
        or user_memory.stable_profile
        or user_memory.conflicts
        or user_memory.confidence > 0
    ):
        user_memory_lines = ["当前已知用户长期记忆："]
        if user_memory.summary:
            user_memory_lines.append(f"- 长期画像摘要：{user_memory.summary}")
        if user_memory.stable_profile:
            user_memory_lines.append("- 长期稳定画像：")
            user_memory_lines.extend(
                f"  - {item.label}: {item.value} (可信度 {item.confidence:.2f})"
                for item in user_memory.stable_profile
            )
        elif user_memory.user_profile:
            user_memory_lines.append("- 长期用户画像：")
            user_memory_lines.extend(f"  - {item}" for item in user_memory.user_profile)
        if user_memory.conflicts:
            user_memory_lines.append("- 长期记忆冲突：")
            user_memory_lines.extend(
                f"  - {item.label}: 旧信息“{item.previous_value}”，新信息“{item.incoming_value}”，状态 {item.status}"
                for item in user_memory.conflicts
            )
        user_memory_lines.append(f"- 长期记忆可信度：{user_memory.confidence:.2f}")
        sections.append("\n".join(user_memory_lines))

    if memory and (
        memory.summary
        or memory.user_profile
        or memory.stable_profile
        or memory.temporary_state
        or memory.conflicts
        or memory.confidence > 0
        or memory.source_turn_end > 0
    ):
        memory_lines = ["当前已知会话记忆："]
        if memory.summary:
            memory_lines.append(f"- 会话摘要：{memory.summary}")
        if memory.stable_profile:
            memory_lines.append("- 稳定画像：")
            memory_lines.extend(
                f"  - {item.label}：{item.value}（可信度 {item.confidence:.2f}）"
                for item in memory.stable_profile
            )
        elif memory.user_profile:
            memory_lines.append("- 用户画像：")
            memory_lines.extend(f"  - {item}" for item in memory.user_profile)
        if memory.temporary_state:
            memory_lines.append("- 临时状态：")
            memory_lines.extend(
                f"  - {item.label}：{item.value}（可信度 {item.confidence:.2f}）"
                for item in memory.temporary_state
            )
        if memory.conflicts:
            memory_lines.append("- 需要注意的记忆冲突：")
            memory_lines.extend(
                f"  - {item.label}：旧信息“{item.previous_value}”，新信息“{item.incoming_value}”，状态 {item.status}"
                for item in memory.conflicts
            )
        memory_lines.append(f"- 记忆可信度：{memory.confidence:.2f}")
        if memory.source_turn_end > 0:
            memory_lines.append(
                f"- 记忆来源轮次：第 {memory.source_turn_start} 到第 {memory.source_turn_end} 轮用户发言"
            )
        sections.append("\n".join(memory_lines))

    if tool_calls:
        tool_lines = ["本轮已完成的工具结果："]
        for tool_call in tool_calls:
            tool_lines.append(f"- 工具：{tool_call.tool_name}")
            tool_lines.append(f"  - 触发方式：{tool_call.trigger}")
            summary = str(tool_call.result.get("summary") or "").strip()
            if summary:
                tool_lines.append(f"  - 结果概括：{summary}")

            required_skills = tool_call.result.get("required_skills")
            if isinstance(required_skills, list) and required_skills:
                tool_lines.append("  - 明确要求：" + "；".join(str(item) for item in required_skills))

            resume_keywords = tool_call.result.get("resume_keywords")
            if isinstance(resume_keywords, list) and resume_keywords:
                tool_lines.append("  - 简历关键词：" + "；".join(str(item) for item in resume_keywords))

            interview_focus = tool_call.result.get("interview_focus")
            if isinstance(interview_focus, list) and interview_focus:
                tool_lines.append("  - 面试重点：" + "；".join(str(item) for item in interview_focus))

            gap_analysis = tool_call.result.get("gap_analysis")
            if isinstance(gap_analysis, list) and gap_analysis:
                tool_lines.append("  - 能力缺口：" + "；".join(str(item) for item in gap_analysis))
        sections.append("\n".join(tool_lines))

    sections.append(CHAT_OUTPUT_PROMPT)
    return "\n\n".join(sections)


def build_memory_update_prompt() -> str:
    return "\n\n".join(
        [
            BASE_ROLE_PROMPT,
            RESPONSE_RULES_PROMPT,
            MEMORY_UPDATE_PROMPT,
        ]
    )


def build_jd_analysis_prompt() -> str:
    return "\n\n".join(
        [
            BASE_ROLE_PROMPT,
            RESPONSE_RULES_PROMPT,
            JD_ANALYSIS_PROMPT,
        ]
    )


def build_resume_tailor_prompt() -> str:
    return "\n\n".join(
        [
            BASE_ROLE_PROMPT,
            RESPONSE_RULES_PROMPT,
            RESUME_TAILOR_PROMPT,
        ]
    )


def render_structured_reply(reply: ChatStructuredReply) -> str:
    lines: list[str] = [reply.summary.strip()]

    if reply.analysis:
        lines.extend(["", "分析："])
        lines.extend(f"- {item}" for item in reply.analysis)

    if reply.actions:
        lines.extend(["", "建议下一步："])
        lines.extend(f"- {item}" for item in reply.actions)

    if reply.follow_up_question:
        lines.extend(["", f"如果你愿意，可以补充：{reply.follow_up_question}"])

    return "\n".join(lines).strip()


def fallback_memory_update() -> SessionMemoryUpdate:
    return SessionMemoryUpdate(
        summary="",
        user_profile=[],
        stable_profile=[],
        temporary_state=[],
        conflicts=[],
        confidence=0.0,
        source_turn_start=0,
        source_turn_end=0,
    )


def fallback_jd_analysis() -> JdAnalysisResult:
    return JdAnalysisResult(
        summary="暂时无法稳定提取 JD 结构信息，请稍后重试。",
        responsibilities=[],
        required_skills=[],
        preferred_skills=[],
        keywords=[],
        match_focus=[],
        resume_keywords=[],
        interview_focus=[],
        gap_analysis=[],
    )


def fallback_resume_tailor() -> ResumeTailorResult:
    return ResumeTailorResult(
        summary="暂时无法稳定生成简历定制建议，请稍后重试。",
        tailored_summary="",
        experience_bullets=[],
        keyword_additions=[],
        risk_alerts=[],
    )

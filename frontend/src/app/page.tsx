"use client";

import { useEffect, useState } from "react";

import { ChatInput } from "@/components/chat-input";
import { ChatWindow } from "@/components/chat-window";
import {
  analyzeJd,
  getCurrentUser,
  getSession,
  getSessions,
  login,
  logout,
  register,
  sendAuthCode,
  setAccessToken,
  type MemoryConflict,
  type MemoryFact,
  sendChat,
  type JdAnalysisResult,
  type SessionMemory,
  type SessionMessage,
  type SessionSummary,
  type UserProfile,
} from "@/lib/api";

const AUTH_STORAGE_KEY = "job-agent-auth-token";

const UI = {
  introContent:
    "我是你的求职助手，可以帮你做求职规划、简历优化、岗位理解和面试准备。你可以先告诉我目标岗位，或者直接贴出你现在最想解决的问题。",
  introSummary:
    "我是你的求职助手，可以先从目标岗位或当前卡点开始。",
  introActionJob: "告诉我目标岗位",
  introActionBlock: "说明你当前卡住的问题",
  loadError: "会话加载失败。",
  requestError: "请求失败。",
  restoreError: "会话恢复失败。",
  jdError: "JD 分析失败。",
  heroTitle: "求职面试 Agent",
  heroDescription:
    "当前版本已经支持长期记忆、多用户隔离准备链路和更完整的 JD 分析结果，后续会继续往标准工具调用与 LangGraph 编排推进。",
  sessionsTitle: "历史会话",
  newSession: "新建会话",
  loadingSessions: "正在加载会话...",
  emptySessions: "还没有历史会话。",
  emptyPreview: "暂无内容",
  memoryTitle: "记忆提炼",
  memoryDescription:
    "这里会拆开展示稳定画像、临时状态和记忆冲突，避免后续摘要被短期噪音覆盖。",
  emptySummary: "当前还没有稳定的会话摘要。",
  stableProfile: "稳定画像",
  temporaryState: "临时状态",
  memoryConflicts: "记忆冲突",
  confidence: "可信度",
  sourceTurns: "来源轮次",
  sourceTurnsValuePrefix: "第 ",
  sourceTurnsValueJoin: " - ",
  sourceTurnsValueSuffix: " 轮",
  updatedAt: "最近更新时间：",
  conflictPending: "待确认",
  conflictResolved: "已解决",
  conflictIgnored: "已忽略",
  emptyMemory:
    "当前会话还没有抽取出稳定记忆。继续对话 2 到 3 轮后，这里会开始出现摘要、用户画像和可信度信息。",
  toolTitle: "JD 深度分析",
  toolDescription:
    "现在的 JD 工具不仅会分析岗位，还会输出可直接用于简历优化、面试准备和能力补齐的结构化信息。",
  jdPlaceholder: "粘贴岗位描述（JD）...",
  analyzing: "分析中...",
  analyzeJd: "分析 JD",
  responsibilities: "岗位职责",
  requiredSkills: "明确要求",
  preferredSkills: "加分项",
  matchFocus: "准备重点",
  resumeKeywords: "简历关键词",
  interviewFocus: "面试重点",
  gapAnalysis: "能力缺口",
  noResult: "暂无提炼结果",
  authTitle: "注册后开始使用",
  authDescription:
    "当前 M4 阶段已接入多用户会话隔离。登录后，你的历史会话和长期记忆会按用户独立保存。",
  authLoginTab: "登录",
  authRegisterTab: "注册",
  authPhone: "手机号",
  authCode: "验证码",
  authDisplayName: "昵称",
  authLoginButton: "登录进入工作台",
  authRegisterButton: "注册并进入工作台",
  authSendCode: "发送验证码",
  authCodeSending: "发送中...",
  authLoading: "提交中...",
  authWelcome: "欢迎回来，",
  authLogout: "退出登录",
  authRequiredName: "昵称至少填写 1 个字符。",
  authRequiredPhone: "请输入有效 11 位手机号。",
  authRequiredCode: "请输入 6 位验证码。",
  authCodeHint: "开发模式验证码：",
} as const;

const INITIAL_MESSAGES: SessionMessage[] = [
  {
    role: "assistant",
    content: UI.introContent,
    structured: {
      summary: UI.introSummary,
      analysis: [],
      actions: [UI.introActionJob, UI.introActionBlock],
      follow_up_question: null,
    },
    tool_calls: [],
  },
];

type AuthMode = "login" | "register";

export default function Home() {
  const [messages, setMessages] = useState<SessionMessage[]>(INITIAL_MESSAGES);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [memory, setMemory] = useState<SessionMemory | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSessionLoading, setIsSessionLoading] = useState(true);
  const [jdText, setJdText] = useState("");
  const [jdResult, setJdResult] = useState<JdAnalysisResult | null>(null);
  const [jdError, setJdError] = useState("");
  const [isJdLoading, setIsJdLoading] = useState(false);
  const [currentUser, setCurrentUser] = useState<UserProfile | null>(null);
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [authPhone, setAuthPhone] = useState("");
  const [authCode, setAuthCode] = useState("");
  const [authDisplayName, setAuthDisplayName] = useState("");
  const [authError, setAuthError] = useState("");
  const [authCodeHint, setAuthCodeHint] = useState("");
  const [authCooldown, setAuthCooldown] = useState(0);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [isAuthSubmitting, setIsAuthSubmitting] = useState(false);
  const [isSendingCode, setIsSendingCode] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      const storedToken =
        typeof window !== "undefined"
          ? window.localStorage.getItem(AUTH_STORAGE_KEY)
          : null;

      if (!storedToken) {
        setAccessToken("");
        if (!cancelled) {
          setCurrentUser(null);
          setIsAuthLoading(false);
          setIsSessionLoading(false);
        }
        return;
      }

      try {
        setAccessToken(storedToken);
        const user = await getCurrentUser();
        if (cancelled) {
          return;
        }

        setCurrentUser(user);
        await initializeSessions();
      } catch {
        if (typeof window !== "undefined") {
          window.localStorage.removeItem(AUTH_STORAGE_KEY);
        }
        setAccessToken("");
        if (!cancelled) {
          setCurrentUser(null);
        }
      } finally {
        if (!cancelled) {
          setIsAuthLoading(false);
          setIsSessionLoading(false);
        }
      }
    }

    async function initializeSessions() {
      try {
        const sessionList = (await getSessions()).map(normalizeSessionSummary);

        if (cancelled) {
          return;
        }

        setSessions(sessionList);

        const latestSessionId = sessionList[0]?.id ?? null;
        if (!latestSessionId) {
          setActiveSessionId(null);
          setMessages(INITIAL_MESSAGES);
          setMemory(null);
          return;
        }

        const session = normalizeSessionDetail(await getSession(latestSessionId));
        if (cancelled) {
          return;
        }

        setActiveSessionId(session.id);
        setMessages(toUiMessages(session.messages));
        setMemory(session.memory);
      } catch (loadError) {
        if (cancelled) {
          return;
        }

        const message =
          loadError instanceof Error ? loadError.message : UI.loadError;
        setError(message);
      }
    }

    void bootstrap();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (authCooldown <= 0) {
      return;
    }

    const timer = window.setTimeout(() => {
      setAuthCooldown((value) => Math.max(0, value - 1));
    }, 1000);

    return () => window.clearTimeout(timer);
  }, [authCooldown]);

  async function refreshSessions(preferredSessionId?: string | null) {
    setIsSessionLoading(true);

    try {
      const sessionList = (await getSessions()).map(normalizeSessionSummary);
      setSessions(sessionList);

      if (!preferredSessionId) {
        return;
      }

      const selectedSession = normalizeSessionDetail(
        await getSession(preferredSessionId),
      );
      setActiveSessionId(selectedSession.id);
      setMessages(toUiMessages(selectedSession.messages));
      setMemory(selectedSession.memory);
    } finally {
      setIsSessionLoading(false);
    }
  }

  async function loadSession(sessionId: string) {
    const session = normalizeSessionDetail(await getSession(sessionId));
    setActiveSessionId(session.id);
    setMessages(toUiMessages(session.messages));
    setMemory(session.memory);
  }

  async function initializeAuthenticatedWorkspace(user: UserProfile) {
    setCurrentUser(user);
    setError("");
    setMessages(INITIAL_MESSAGES);
    setMemory(null);
    setActiveSessionId(null);
    await refreshSessions();
  }

  async function handleAuthSubmit() {
    if (!isValidPhone(authPhone)) {
      setAuthError(UI.authRequiredPhone);
      return;
    }

    if (authCode.trim().length !== 6) {
      setAuthError(UI.authRequiredCode);
      return;
    }

    if (authMode === "register" && authDisplayName.trim().length < 1) {
      setAuthError(UI.authRequiredName);
      return;
    }

    setAuthError("");
    setIsAuthSubmitting(true);

    try {
      const response =
        authMode === "login"
          ? await login({
              phone: authPhone.trim(),
              code: authCode.trim(),
            })
          : await register({
              phone: authPhone.trim(),
              code: authCode.trim(),
              displayName: authDisplayName.trim(),
            });

      setAccessToken(response.access_token);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(AUTH_STORAGE_KEY, response.access_token);
      }
      await initializeAuthenticatedWorkspace(response.user);
    } catch (submitError) {
      const message =
        submitError instanceof Error ? submitError.message : UI.requestError;
      setAuthError(message);
    } finally {
      setIsAuthSubmitting(false);
    }
  }

  async function handleLogout() {
    try {
      await logout();
    } catch {
      // Ignore logout request failures; local cleanup still wins.
    }

    setAccessToken("");
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(AUTH_STORAGE_KEY);
    }

    setCurrentUser(null);
    setSessions([]);
    setActiveSessionId(null);
    setMessages(INITIAL_MESSAGES);
    setMemory(null);
    setError("");
    setJdText("");
    setJdResult(null);
    setJdError("");
    setAuthPhone("");
    setAuthCode("");
    setAuthDisplayName("");
    setAuthCodeHint("");
    setAuthCooldown(0);
  }

  async function handleSendCode() {
    if (!isValidPhone(authPhone) || isSendingCode || authCooldown > 0) {
      if (!isValidPhone(authPhone)) {
        setAuthError(UI.authRequiredPhone);
      }
      return;
    }

    setAuthError("");
    setIsSendingCode(true);

    try {
      const response = await sendAuthCode({
        phone: authPhone.trim(),
        purpose: authMode,
      });
      setAuthCooldown(response.cooldown_seconds);
      setAuthCodeHint(response.dev_code ?? "");
    } catch (sendError) {
      const message =
        sendError instanceof Error ? sendError.message : UI.requestError;
      setAuthError(message);
    } finally {
      setIsSendingCode(false);
    }
  }

  async function handleSubmit(content: string) {
    const previousMessages = messages;
    const optimisticMessages: SessionMessage[] = [
      ...previousMessages,
      { role: "user", content, tool_calls: [] },
    ];

    setMessages(optimisticMessages);
    setError("");
    setIsLoading(true);

    try {
      const response = await sendChat({
        message: content,
        sessionId: activeSessionId,
      });

      const nextSessionId = response.session_id;
      setActiveSessionId(nextSessionId);
      setMessages([...optimisticMessages, normalizeMessage(response.message)]);
      await refreshSessions(nextSessionId);
    } catch (submitError) {
      const message =
        submitError instanceof Error ? submitError.message : UI.requestError;
      setError(message);
      setMessages(previousMessages);
    } finally {
      setIsLoading(false);
    }
  }

  function handleNewSession() {
    setActiveSessionId(null);
    setMessages(INITIAL_MESSAGES);
    setMemory(null);
    setError("");
  }

  async function handleSelectSession(sessionId: string) {
    setError("");
    setIsLoading(true);

    try {
      await loadSession(sessionId);
    } catch (sessionError) {
      const message =
        sessionError instanceof Error ? sessionError.message : UI.restoreError;
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleAnalyzeJd() {
    const content = jdText.trim();
    if (!content || isJdLoading) {
      return;
    }

    setIsJdLoading(true);
    setJdError("");

    try {
      const response = await analyzeJd(content);
      setJdResult(normalizeJdResult(response.result));
    } catch (analyzeError) {
      const message =
        analyzeError instanceof Error ? analyzeError.message : UI.jdError;
      setJdError(message);
      setJdResult(null);
    } finally {
      setIsJdLoading(false);
    }
  }

  if (isAuthLoading) {
    return <main className="page-shell"><section className="hero-card">正在初始化...</section></main>;
  }

  if (!currentUser) {
    return (
      <main className="page-shell page-shell-auth">
        <section className="hero-card">
          <div className="hero-text">
            <p className="eyebrow">M4 Multi-user Access</p>
            <h1>{UI.heroTitle}</h1>
            <p className="hero-description">{UI.heroDescription}</p>
          </div>
        </section>

        <section className="auth-card" data-testid="auth-panel">
          <div className="auth-header">
            <div>
              <p className="session-eyebrow">Authentication</p>
              <h2>{UI.authTitle}</h2>
              <p className="section-description">{UI.authDescription}</p>
            </div>
            <div className="auth-tabs">
              <button
                className={`auth-tab ${authMode === "login" ? "auth-tab-active" : ""}`}
                type="button"
                onClick={() => setAuthMode("login")}
              >
                {UI.authLoginTab}
              </button>
              <button
                className={`auth-tab ${authMode === "register" ? "auth-tab-active" : ""}`}
                type="button"
                onClick={() => setAuthMode("register")}
              >
                {UI.authRegisterTab}
              </button>
            </div>
          </div>

          <div className="auth-form">
            {authMode === "register" ? (
              <label className="auth-field">
              <span>{UI.authDisplayName}</span>
              <input
                className="auth-input"
                  value={authDisplayName}
                  onChange={(event) => setAuthDisplayName(event.target.value)}
                  placeholder="例如：张三"
                />
              </label>
            ) : null}

            <label className="auth-field">
              <span>{UI.authPhone}</span>
              <input
                className="auth-input"
                type="text"
                value={authPhone}
                onChange={(event) => setAuthPhone(event.target.value)}
                placeholder="例如：13800138000"
              />
            </label>

            <div className="auth-code-row">
              <label className="auth-field auth-field-grow">
                <span>{UI.authCode}</span>
                <input
                  className="auth-input"
                  type="text"
                  value={authCode}
                  onChange={(event) => setAuthCode(event.target.value)}
                  placeholder="请输入 6 位验证码"
                />
              </label>
              <button
                className="secondary-button auth-code-button"
                type="button"
                onClick={() => void handleSendCode()}
                disabled={isSendingCode || authCooldown > 0}
              >
                {isSendingCode
                  ? UI.authCodeSending
                  : authCooldown > 0
                    ? `${authCooldown}s`
                    : UI.authSendCode}
              </button>
            </div>

            {authCodeHint ? (
              <p className="auth-code-hint">
                {UI.authCodeHint}
                <strong>{authCodeHint}</strong>
              </p>
            ) : null}

            {authError ? <p className="error-banner">{authError}</p> : null}

            <button
              className="send-button auth-submit"
              type="button"
              onClick={() => void handleAuthSubmit()}
              disabled={isAuthSubmitting}
            >
              {isAuthSubmitting
                ? UI.authLoading
                : authMode === "login"
                  ? UI.authLoginButton
                  : UI.authRegisterButton}
            </button>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="page-shell">
      <section className="hero-card hero-card-compact">
        <div className="hero-text">
          <p className="eyebrow">M4 Multi-user Workspace</p>
          <h1>{UI.heroTitle}</h1>
          <p className="hero-description">{UI.heroDescription}</p>
        </div>
        <div className="user-badge-card">
          <p className="session-eyebrow">Workspace Owner</p>
          <strong>
            {UI.authWelcome}
            {currentUser.display_name}
          </strong>
          <span>{currentUser.phone || "未绑定手机号"}</span>
          <button
            className="secondary-button"
            type="button"
            onClick={() => void handleLogout()}
          >
            {UI.authLogout}
          </button>
        </div>
      </section>

      <section className="workspace-grid">
        <aside className="session-card" data-testid="session-panel">
          <div className="session-card-header">
            <div>
              <p className="session-eyebrow">Sessions</p>
              <h2>{UI.sessionsTitle}</h2>
            </div>
            <button
              className="secondary-button"
              onClick={handleNewSession}
              type="button"
            >
              {UI.newSession}
            </button>
          </div>

          <div className="session-list">
            {isSessionLoading ? (
              <p className="session-empty">{UI.loadingSessions}</p>
            ) : sessions.length === 0 ? (
              <p className="session-empty">{UI.emptySessions}</p>
            ) : (
              sessions.map((session) => (
                <button
                  key={session.id}
                  type="button"
                  className={`session-item ${
                    session.id === activeSessionId ? "session-item-active" : ""
                  }`}
                  onClick={() => void handleSelectSession(session.id)}
                >
                  <span className="session-title">{session.title}</span>
                  <span className="session-preview">
                    {session.last_message_preview || UI.emptyPreview}
                  </span>
                </button>
              ))
            )}
          </div>
        </aside>

        <section className="main-panel">
          <section className="memory-card" data-testid="memory-panel">
            <div className="section-header">
              <div>
                <p className="session-eyebrow">Session Memory</p>
                <h2>{UI.memoryTitle}</h2>
                <p className="section-description">{UI.memoryDescription}</p>
              </div>
            </div>

            {memory &&
            (memory.summary ||
              memory.user_profile.length > 0 ||
              memory.stable_profile.length > 0 ||
              memory.temporary_state.length > 0 ||
              memory.conflicts.length > 0) ? (
              <>
                <p className="memory-summary">
                  {memory.summary || UI.emptySummary}
                </p>
                <div className="memory-sections">
                  <MemoryFactSection
                    title={UI.stableProfile}
                    items={memory.stable_profile}
                  />
                  {memory.stable_profile.length === 0 &&
                  memory.user_profile.length > 0 ? (
                    <ul className="memory-list">
                      {memory.user_profile.map((item) => (
                        <li className="memory-pill" key={item}>
                          {item}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <MemoryFactSection
                    title={UI.temporaryState}
                    items={memory.temporary_state}
                  />
                  <MemoryConflictSection items={memory.conflicts} />
                </div>
                <div className="memory-metrics">
                  <div className="metric-card">
                    <span className="metric-label">{UI.confidence}</span>
                    <strong>{Math.round(memory.confidence * 100)}%</strong>
                  </div>
                  <div className="metric-card">
                    <span className="metric-label">{UI.sourceTurns}</span>
                    <strong>
                      {UI.sourceTurnsValuePrefix}
                      {memory.source_turn_start || 0}
                      {UI.sourceTurnsValueJoin}
                      {memory.source_turn_end || 0}
                      {UI.sourceTurnsValueSuffix}
                    </strong>
                  </div>
                </div>
                <p className="memory-meta">
                  {UI.updatedAt}
                  {formatDateTime(memory.updated_at)}
                </p>
              </>
            ) : (
              <p className="empty-card">{UI.emptyMemory}</p>
            )}
          </section>

          <section className="chat-card" data-testid="chat-panel">
            <ChatWindow messages={messages} isLoading={isLoading} />
            {error ? <p className="error-banner">{error}</p> : null}
            <ChatInput onSubmit={handleSubmit} disabled={isLoading} />
          </section>

          <section className="tool-card" data-testid="jd-tool-panel">
            <div className="section-header">
              <div>
                <p className="session-eyebrow">Tool</p>
                <h2>{UI.toolTitle}</h2>
                <p className="section-description">{UI.toolDescription}</p>
              </div>
            </div>

            <div className="tool-form">
              <textarea
                data-testid="jd-input"
                className="tool-textarea"
                placeholder={UI.jdPlaceholder}
                value={jdText}
                onChange={(event) => setJdText(event.target.value)}
                disabled={isJdLoading}
              />
              <div className="tool-actions">
                <button
                  data-testid="jd-analyze"
                  className="send-button"
                  type="button"
                  onClick={() => void handleAnalyzeJd()}
                  disabled={isJdLoading || !jdText.trim()}
                >
                  {isJdLoading ? UI.analyzing : UI.analyzeJd}
                </button>
              </div>
            </div>

            {jdError ? <p className="error-banner">{jdError}</p> : null}

            {jdResult ? (
              <div className="tool-result">
                <p className="tool-summary">{jdResult.summary}</p>

                <div className="tool-grid">
                  <ToolResultCard
                    title={UI.responsibilities}
                    items={jdResult.responsibilities}
                  />
                  <ToolResultCard
                    title={UI.requiredSkills}
                    items={jdResult.required_skills}
                  />
                  <ToolResultCard
                    title={UI.preferredSkills}
                    items={jdResult.preferred_skills}
                  />
                  <ToolResultCard
                    title={UI.matchFocus}
                    items={jdResult.match_focus}
                  />
                  <ToolResultCard
                    title={UI.resumeKeywords}
                    items={jdResult.resume_keywords}
                  />
                  <ToolResultCard
                    title={UI.interviewFocus}
                    items={jdResult.interview_focus}
                  />
                  <ToolResultCard
                    title={UI.gapAnalysis}
                    items={jdResult.gap_analysis}
                  />
                </div>

                {jdResult.keywords.length > 0 ? (
                  <ul className="tag-list">
                    {jdResult.keywords.map((item) => (
                      <li className="tag-pill" key={item}>
                        {item}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </section>
        </section>
      </section>
    </main>
  );
}

function ToolResultCard({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  return (
    <section className="tool-result-card">
      <h3>{title}</h3>
      {items.length > 0 ? (
        <ul className="tool-result-list">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="session-empty">{UI.noResult}</p>
      )}
    </section>
  );
}

function MemoryFactSection({
  title,
  items,
}: {
  title: string;
  items: MemoryFact[];
}) {
  if (items.length === 0) {
    return null;
  }

  return (
    <section className="memory-subsection">
      <h3>{title}</h3>
      <div className="memory-fact-list">
        {items.map((item) => (
          <article className="memory-fact-card" key={`${item.key}-${item.value}`}>
            <div className="memory-fact-topline">
              <strong>{item.label}</strong>
              <span>{Math.round(item.confidence * 100)}%</span>
            </div>
            <p>{item.value}</p>
            <p className="memory-fact-meta">
              {UI.sourceTurns}
              {UI.sourceTurnsValuePrefix}
              {item.source_turn_start}
              {UI.sourceTurnsValueJoin}
              {item.source_turn_end}
              {UI.sourceTurnsValueSuffix}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

function MemoryConflictSection({
  items,
}: {
  items: MemoryConflict[];
}) {
  if (items.length === 0) {
    return null;
  }

  return (
    <section className="memory-subsection">
      <h3>{UI.memoryConflicts}</h3>
      <div className="memory-fact-list">
        {items.map((item) => (
          <article className="memory-conflict-card" key={`${item.key}-${item.incoming_value}`}>
            <div className="memory-fact-topline">
              <strong>{item.label}</strong>
              <span>{formatConflictStatus(item.status)}</span>
            </div>
            <p>
              {item.previous_value} {"->"} {item.incoming_value}
            </p>
            <p className="memory-fact-meta">{item.resolution}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function toUiMessages(messages: SessionMessage[]): SessionMessage[] {
  const nextMessages = messages
    .map(normalizeMessage)
    .filter(
      (message): message is SessionMessage & { role: "user" | "assistant" } =>
        message.role === "user" || message.role === "assistant",
    );

  return nextMessages.length > 0 ? nextMessages : INITIAL_MESSAGES;
}

function normalizeSessionSummary(session: SessionSummary): SessionSummary {
  return {
    id: session.id,
    title: readString(session.title) || "新会话",
    created_at: readString(session.created_at),
    updated_at: readString(session.updated_at),
    last_message_preview: readString(session.last_message_preview),
  };
}

function normalizeSessionDetail(session: Awaited<ReturnType<typeof getSession>>) {
  return {
    ...session,
    title: readString(session.title) || "新会话",
    created_at: readString(session.created_at),
    updated_at: readString(session.updated_at),
    messages: Array.isArray(session.messages)
      ? session.messages.map(normalizeMessage)
      : [],
    memory: normalizeMemory(session.memory),
  };
}

function normalizeMessage(message: SessionMessage): SessionMessage {
  return {
    role: message.role,
    content: readString(message.content),
    structured: normalizeStructured(message.structured),
    tool_calls: Array.isArray(message.tool_calls) ? message.tool_calls : [],
  };
}

function normalizeStructured(structured: SessionMessage["structured"]) {
  if (!structured) {
    return null;
  }

  return {
    summary: readString(structured.summary),
    analysis: readStringList(structured.analysis),
    actions: readStringList(structured.actions),
    follow_up_question: readNullableString(structured.follow_up_question),
  };
}

function normalizeMemory(memory: SessionMemory | null | undefined): SessionMemory | null {
  if (!memory) {
    return null;
  }

  return {
    session_id: readString(memory.session_id),
    summary: readString(memory.summary),
    user_profile: readStringList(memory.user_profile),
    stable_profile: readMemoryFacts(memory.stable_profile),
    temporary_state: readMemoryFacts(memory.temporary_state),
    conflicts: readMemoryConflicts(memory.conflicts),
    confidence: readNumber(memory.confidence),
    source_turn_start: readNumber(memory.source_turn_start),
    source_turn_end: readNumber(memory.source_turn_end),
    updated_at: readString(memory.updated_at),
  };
}

function normalizeJdResult(result: JdAnalysisResult): JdAnalysisResult {
  return {
    summary: readString(result.summary),
    responsibilities: readStringList(result.responsibilities),
    required_skills: readStringList(result.required_skills),
    preferred_skills: readStringList(result.preferred_skills),
    keywords: readStringList(result.keywords),
    match_focus: readStringList(result.match_focus),
    resume_keywords: readStringList(result.resume_keywords),
    interview_focus: readStringList(result.interview_focus),
    gap_analysis: readStringList(result.gap_analysis),
  };
}

function readMemoryFacts(value: unknown): MemoryFact[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item): MemoryFact | null => {
      if (!item || typeof item !== "object") {
        return null;
      }

      const record = item as Partial<MemoryFact>;
      const label = readString(record.label);
      const factValue = readString(record.value);
      if (!label || !factValue) {
        return null;
      }

      return {
        key: readString(record.key),
        label,
        value: factValue,
        confidence: readNumber(record.confidence),
        source_turn_start: readNumber(record.source_turn_start),
        source_turn_end: readNumber(record.source_turn_end),
        updated_at: readNullableString(record.updated_at),
      };
    })
    .filter((item): item is MemoryFact => item !== null);
}

function readMemoryConflicts(value: unknown): MemoryConflict[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item): MemoryConflict | null => {
      if (!item || typeof item !== "object") {
        return null;
      }

      const record = item as Partial<MemoryConflict>;
      const label = readString(record.label);
      const previousValue = readString(record.previous_value);
      const incomingValue = readString(record.incoming_value);
      if (!label || !previousValue || !incomingValue) {
        return null;
      }

      const status =
        record.status === "resolved" || record.status === "ignored"
          ? record.status
          : "pending";

      return {
        key: readString(record.key),
        label,
        previous_value: previousValue,
        incoming_value: incomingValue,
        status,
        resolution: readString(record.resolution),
        confidence: readNumber(record.confidence),
        source_turn_start: readNumber(record.source_turn_start),
        source_turn_end: readNumber(record.source_turn_end),
        updated_at: readNullableString(record.updated_at),
      };
    })
    .filter((item): item is MemoryConflict => item !== null);
}

function readString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function readNullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function readStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((item): item is string => typeof item === "string");
}

function readNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatConflictStatus(status: MemoryConflict["status"]): string {
  if (status === "resolved") {
    return UI.conflictResolved;
  }

  if (status === "ignored") {
    return UI.conflictIgnored;
  }

  return UI.conflictPending;
}

function isValidPhone(value: string): boolean {
  return /^1\d{10}$/.test(value.trim());
}

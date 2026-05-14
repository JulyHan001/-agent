import type { SessionMessage, ToolCallRecord } from "@/lib/api";

const UI = {
  user: "\u4f60",
  assistant: "\u6c42\u804c\u52a9\u624b",
  loading: "\u6b63\u5728\u6574\u7406\u56de\u7b54...",
  analysis: "\u5206\u6790",
  nextAction: "\u5efa\u8bae\u4e0b\u4e00\u6b65",
  needMore: "\u8fd8\u9700\u8981\u4f60\u8865\u5145",
  toolUsed: "\u5df2\u8c03\u7528\u5de5\u5177\uff1a",
  auto: "\u81ea\u52a8\u89e6\u53d1",
  manual: "\u624b\u52a8\u89e6\u53d1",
  suggested: "\u5efa\u8bae\u89e6\u53d1",
  requiredSkills: "\u660e\u786e\u8981\u6c42",
  matchFocus: "\u51c6\u5907\u91cd\u70b9",
  noToolSummary: "\u5df2\u8fd4\u56de\u7ed3\u6784\u5316\u5de5\u5177\u7ed3\u679c\u3002",
} as const;

type ChatWindowProps = {
  messages: SessionMessage[];
  isLoading: boolean;
};

export function ChatWindow({ messages, isLoading }: ChatWindowProps) {
  return (
    <div className="chat-window">
      {messages.map((message, index) => (
        <article
          key={`${message.role}-${index}`}
          className={`message message-${message.role}`}
        >
          <div className="message-label">
            {message.role === "user" ? UI.user : UI.assistant}
          </div>
          {message.role === "assistant" && message.structured ? (
            <StructuredAssistantMessage message={message} />
          ) : (
            <div className="message-content">{message.content}</div>
          )}
          {message.tool_calls && message.tool_calls.length > 0 ? (
            <ToolCallList toolCalls={message.tool_calls} />
          ) : null}
        </article>
      ))}
      {isLoading ? (
        <article className="message message-assistant">
          <div className="message-label">{UI.assistant}</div>
          <div className="message-content">{UI.loading}</div>
        </article>
      ) : null}
    </div>
  );
}

function StructuredAssistantMessage({ message }: { message: SessionMessage }) {
  const structured = message.structured;

  if (!structured) {
    return <div className="message-content">{message.content}</div>;
  }

  return (
    <div className="structured-message">
      <div className="message-content">{structured.summary}</div>

      {structured.analysis.length > 0 ? (
        <section className="structured-section">
          <div className="structured-title">{UI.analysis}</div>
          <ul className="structured-list">
            {structured.analysis.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {structured.actions.length > 0 ? (
        <section className="structured-section">
          <div className="structured-title">{UI.nextAction}</div>
          <ul className="structured-list">
            {structured.actions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {structured.follow_up_question ? (
        <section className="structured-section">
          <div className="structured-title">{UI.needMore}</div>
          <div className="message-content">{structured.follow_up_question}</div>
        </section>
      ) : null}
    </div>
  );
}

function ToolCallList({ toolCalls }: { toolCalls: ToolCallRecord[] }) {
  return (
    <div className="tool-call-stack">
      {toolCalls.map((toolCall, index) => (
        <section
          key={`${toolCall.tool_name}-${toolCall.trigger}-${index}`}
          className="tool-call-card"
        >
          <div className="tool-call-header">
            <span>
              {UI.toolUsed}
              {toolCall.tool_name}
            </span>
            <span>{formatTrigger(toolCall.trigger)}</span>
          </div>
          <p className="tool-call-summary">
            {readString(toolCall.result.summary) || UI.noToolSummary}
          </p>
          {readStringList(toolCall.result.required_skills).length > 0 ? (
            <div className="tool-call-section">
              <div className="structured-title">{UI.requiredSkills}</div>
              <ul className="structured-list">
                {readStringList(toolCall.result.required_skills).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {readStringList(toolCall.result.match_focus).length > 0 ? (
            <div className="tool-call-section">
              <div className="structured-title">{UI.matchFocus}</div>
              <ul className="structured-list">
                {readStringList(toolCall.result.match_focus).map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ))}
    </div>
  );
}

function readString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function readStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((item): item is string => typeof item === "string");
}

function formatTrigger(trigger: ToolCallRecord["trigger"]): string {
  if (trigger === "auto") {
    return UI.auto;
  }

  if (trigger === "suggested") {
    return UI.suggested;
  }

  return UI.manual;
}

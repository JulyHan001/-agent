"use client";

import { FormEvent, useState } from "react";

const UI = {
  placeholder:
    "\u8f93\u5165\u6c42\u804c\u3001\u7b80\u5386\u3001\u9762\u8bd5\u76f8\u5173\u95ee\u9898\uff0c\u6216\u76f4\u63a5\u7c98\u8d34\u5c97\u4f4d JD...",
  send: "\u53d1\u9001",
} as const;

type ChatInputProps = {
  onSubmit: (value: string) => Promise<void>;
  disabled: boolean;
};

export function ChatInput({ onSubmit, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = value.trim();

    if (!content || disabled) {
      return;
    }

    setValue("");
    await onSubmit(content);
  }

  return (
    <form className="chat-input-form" onSubmit={handleSubmit}>
      <textarea
        data-testid="chat-input"
        className="chat-textarea"
        rows={4}
        placeholder={UI.placeholder}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        disabled={disabled}
      />
      <button
        data-testid="chat-send"
        className="send-button"
        type="submit"
        disabled={disabled}
      >
        {UI.send}
      </button>
    </form>
  );
}

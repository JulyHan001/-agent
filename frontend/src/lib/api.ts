export type StructuredReply = {
  summary: string;
  analysis: string[];
  actions: string[];
  follow_up_question: string | null;
};

export type JdAnalysisResult = {
  summary: string;
  responsibilities: string[];
  required_skills: string[];
  preferred_skills: string[];
  keywords: string[];
  match_focus: string[];
  resume_keywords: string[];
  interview_focus: string[];
  gap_analysis: string[];
};

export type UserProfile = {
  id: string;
  phone?: string | null;
  display_name: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  user: UserProfile;
};

export type AuthCodeSendResponse = {
  success: boolean;
  cooldown_seconds: number;
  expires_in_seconds: number;
  dev_code?: string | null;
};

export type ToolCallRecord = {
  tool_name: string;
  trigger: "auto" | "manual" | "suggested";
  input_excerpt: string;
  result: Record<string, unknown>;
};

export type SessionMessage = {
  role: "user" | "assistant" | "system";
  content: string;
  structured?: StructuredReply | null;
  tool_calls?: ToolCallRecord[];
};

export type SessionMemory = {
  session_id: string;
  summary: string;
  user_profile: string[];
  stable_profile: MemoryFact[];
  temporary_state: MemoryFact[];
  conflicts: MemoryConflict[];
  confidence: number;
  source_turn_start: number;
  source_turn_end: number;
  updated_at: string;
};

export type MemoryFact = {
  key: string;
  label: string;
  value: string;
  confidence: number;
  source_turn_start: number;
  source_turn_end: number;
  updated_at?: string | null;
};

export type MemoryConflict = {
  key: string;
  label: string;
  previous_value: string;
  incoming_value: string;
  status: "pending" | "resolved" | "ignored";
  resolution: string;
  confidence: number;
  source_turn_start: number;
  source_turn_end: number;
  updated_at?: string | null;
};

export type ChatResponse = {
  session_id: string;
  message: SessionMessage;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
};

export type SessionSummary = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_preview: string;
};

export type SessionDetail = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: SessionMessage[];
  memory: SessionMemory | null;
};

export type JdAnalysisResponse = {
  result: JdAnalysisResult;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";

let accessToken = "";

export function setAccessToken(token: string | null | undefined) {
  accessToken = token?.trim() ?? "";
}

function buildHeaders(headers?: HeadersInit): HeadersInit {
  const nextHeaders = new Headers(headers);
  if (accessToken) {
    nextHeaders.set("Authorization", `Bearer ${accessToken}`);
  }
  return nextHeaders;
}

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";

    if (contentType.includes("application/json")) {
      const errorPayload = (await response.json()) as { detail?: string };
      throw new Error(errorPayload.detail || "Request failed.");
    }

    const errorText = await response.text();
    throw new Error(errorText || "Request failed.");
  }

  return response.json() as Promise<T>;
}

export async function sendChat(payload: {
  message: string;
  sessionId?: string | null;
}): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: buildHeaders({
      "Content-Type": "application/json",
    }),
    body: JSON.stringify({
      session_id: payload.sessionId ?? null,
      messages: [
        {
          role: "user",
          content: payload.message,
        },
      ],
    }),
  });

  return parseJsonResponse<ChatResponse>(response);
}

export async function getSessions(): Promise<SessionSummary[]> {
  const response = await fetch(`${API_BASE_URL}/api/sessions`, {
    cache: "no-store",
    headers: buildHeaders(),
  });

  return parseJsonResponse<SessionSummary[]>(response);
}

export async function getSession(sessionId: string): Promise<SessionDetail> {
  const response = await fetch(`${API_BASE_URL}/api/sessions/${sessionId}`, {
    cache: "no-store",
    headers: buildHeaders(),
  });

  return parseJsonResponse<SessionDetail>(response);
}

export async function analyzeJd(jdText: string): Promise<JdAnalysisResponse> {
  const response = await fetch(`${API_BASE_URL}/api/analyze/jd`, {
    method: "POST",
    headers: buildHeaders({
      "Content-Type": "application/json",
    }),
    body: JSON.stringify({
      jd_text: jdText,
    }),
  });

  return parseJsonResponse<JdAnalysisResponse>(response);
}

export async function sendAuthCode(payload: {
  phone: string;
  purpose: "register" | "login";
}): Promise<AuthCodeSendResponse> {
  const response = await fetch(`${API_BASE_URL}/api/auth/code/send`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return parseJsonResponse<AuthCodeSendResponse>(response);
}

export async function register(payload: {
  phone: string;
  code: string;
  displayName: string;
}): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      phone: payload.phone,
      code: payload.code,
      display_name: payload.displayName,
    }),
  });

  return parseJsonResponse<AuthResponse>(response);
}

export async function login(payload: {
  phone: string;
  code: string;
}): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      phone: payload.phone,
      code: payload.code,
    }),
  });

  return parseJsonResponse<AuthResponse>(response);
}

export async function getCurrentUser(): Promise<UserProfile> {
  const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
    cache: "no-store",
    headers: buildHeaders(),
  });

  return parseJsonResponse<UserProfile>(response);
}

export async function logout(): Promise<{ success: boolean }> {
  const response = await fetch(`${API_BASE_URL}/api/auth/logout`, {
    method: "POST",
    headers: buildHeaders(),
  });

  return parseJsonResponse<{ success: boolean }>(response);
}

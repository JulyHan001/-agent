from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Job Interview Agent API"
    app_env: str = "development"
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    sqlite_path: str = "data/job_interview_agent.db"
    default_user_id: str = "default-local-user"
    default_user_name: str = "Default Local User"
    auth_secret_key: str = "job-agent-dev-secret"
    auth_code_ttl_seconds: int = 300
    auth_code_cooldown_seconds: int = 60
    auth_code_max_attempts: int = 5
    mock_sms_code: bool = True
    mock_llm: bool = False
    chat_context_message_limit: int = 20
    chat_summary_trigger_message_count: int = 6

    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def cors_origin_list(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        expanded: list[str] = []

        for origin in origins:
            if origin not in expanded:
                expanded.append(origin)

            parsed = urlparse(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                continue

            alternate_host = None
            if parsed.hostname == "localhost":
                alternate_host = "127.0.0.1"
            elif parsed.hostname == "127.0.0.1":
                alternate_host = "localhost"

            if alternate_host is None:
                continue

            alternate_origin = f"{parsed.scheme}://{alternate_host}"
            if parsed.port:
                alternate_origin = f"{alternate_origin}:{parsed.port}"

            if alternate_origin not in expanded:
                expanded.append(alternate_origin)

        return expanded


settings = Settings()

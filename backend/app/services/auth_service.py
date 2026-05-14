from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status

from app.core.config import settings
from app.models.chat import (
    AuthCodeSendRequest,
    AuthCodeSendResponse,
    AuthLoginRequest,
    AuthRegisterRequest,
    UserProfile,
)
from app.repositories.session_repository import session_repository


class AuthService:
    def normalize_phone(self, phone: str) -> str:
        normalized = phone.strip()
        if not self.is_valid_phone(normalized):
            raise HTTPException(
                status_code=422,
                detail="Phone must be a valid mainland China 11-digit mobile number.",
            )
        return normalized

    @staticmethod
    def is_valid_phone(value: str) -> bool:
        return bool(re.fullmatch(r"1\d{10}", value))

    def generate_code(self) -> str:
        return f"{secrets.randbelow(1_000_000):06d}"

    def hash_code(self, code: str) -> str:
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    def send_code(self, request: AuthCodeSendRequest) -> AuthCodeSendResponse:
        phone = self.normalize_phone(request.phone)
        existing_user = session_repository.get_user_by_phone(phone)
        if request.purpose == "register" and existing_user is not None:
            raise HTTPException(status_code=409, detail="Phone already registered.")
        if request.purpose == "login" and existing_user is None:
            raise HTTPException(status_code=404, detail="Phone not registered.")

        latest = session_repository.get_latest_auth_verification_code(
            phone=phone,
            purpose=request.purpose,
        )
        now = datetime.now(UTC)

        if latest is not None:
            cooldown_deadline = latest.last_sent_at + timedelta(
                seconds=settings.auth_code_cooldown_seconds
            )
            if cooldown_deadline > now:
                remaining = int((cooldown_deadline - now).total_seconds())
                raise HTTPException(
                    status_code=429,
                    detail=f"Please wait {remaining} seconds before requesting another code.",
                )

        code = self.generate_code()
        expires_at = now + timedelta(seconds=settings.auth_code_ttl_seconds)
        session_repository.create_auth_verification_code(
            phone=phone,
            purpose=request.purpose,
            code_hash=self.hash_code(code),
            created_at=now,
            expires_at=expires_at,
        )

        return AuthCodeSendResponse(
            success=True,
            cooldown_seconds=settings.auth_code_cooldown_seconds,
            expires_in_seconds=settings.auth_code_ttl_seconds,
            dev_code=code if settings.mock_sms_code else None,
        )

    def register(self, request: AuthRegisterRequest) -> UserProfile:
        phone = self.normalize_phone(request.phone)
        existing = session_repository.get_user_by_phone(phone)
        if existing is not None:
            raise HTTPException(status_code=409, detail="Phone already registered.")

        self.verify_code(phone=phone, purpose="register", code=request.code)
        return session_repository.create_user(
            phone=phone,
            display_name=request.display_name,
        )

    def login(self, request: AuthLoginRequest) -> UserProfile:
        phone = self.normalize_phone(request.phone)
        user = session_repository.get_user_by_phone(phone)
        if user is None:
            raise HTTPException(status_code=404, detail="Phone not registered.")
        if user.status != "active":
            raise HTTPException(status_code=403, detail="User is not active.")

        self.verify_code(phone=phone, purpose="login", code=request.code)
        return user

    def verify_code(self, *, phone: str, purpose: str, code: str) -> None:
        latest = session_repository.get_latest_auth_verification_code(
            phone=phone,
            purpose=purpose,
        )
        if latest is None:
            raise HTTPException(status_code=404, detail="Verification code not found.")
        if latest.status != "pending":
            raise HTTPException(status_code=400, detail="Verification code already used.")
        if latest.expires_at <= datetime.now(UTC):
            session_repository.mark_auth_code_consumed(
                latest.id,
                status="expired",
                consumed_at=datetime.now(UTC),
            )
            raise HTTPException(status_code=400, detail="Verification code expired.")
        if latest.attempts >= settings.auth_code_max_attempts:
            raise HTTPException(status_code=429, detail="Too many failed verification attempts.")

        incoming_hash = self.hash_code(code.strip())
        latest_hash = session_repository.get_auth_code_hash(latest.id)
        if latest_hash is None:
            raise HTTPException(status_code=404, detail="Verification code not found.")
        if not hmac.compare_digest(incoming_hash, latest_hash):
            session_repository.increment_auth_code_attempts(latest.id, latest.attempts + 1)
            raise HTTPException(status_code=400, detail="Verification code is invalid.")

        session_repository.mark_auth_code_consumed(
            latest.id,
            status="used",
            consumed_at=datetime.now(UTC),
        )

    def create_access_token(self, user: UserProfile) -> str:
        expires_at = int((datetime.now(UTC) + timedelta(days=7)).timestamp())
        payload = {
            "sub": user.id,
            "exp": expires_at,
            "type": "access",
        }
        payload_raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
        payload_b64 = base64.urlsafe_b64encode(payload_raw).decode("utf-8").rstrip("=")
        signature = hmac.new(
            settings.auth_secret_key.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
        return f"{payload_b64}.{signature_b64}"

    def resolve_user_from_token(self, token: str) -> UserProfile:
        payload = self._decode_token(token)
        user_id = str(payload.get("sub") or "").strip()
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token.")

        user = session_repository.get_user_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="User not found.")
        if user.status != "active":
            raise HTTPException(status_code=403, detail="User is not active.")
        return user

    def get_default_user(self) -> UserProfile:
        user = session_repository.get_user_by_id(settings.default_user_id)
        if user is None:
            raise HTTPException(status_code=500, detail="Default user not initialized.")
        return user

    def _decode_token(self, token: str) -> dict[str, object]:
        try:
            payload_b64, signature_b64 = token.split(".", 1)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail="Invalid token.") from exc

        expected_signature = hmac.new(
            settings.auth_secret_key.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        provided_signature = self._urlsafe_b64decode(signature_b64)
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise HTTPException(status_code=401, detail="Invalid token signature.")

        payload_raw = self._urlsafe_b64decode(payload_b64)
        try:
            payload = json.loads(payload_raw.decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid token payload.") from exc

        exp = int(payload.get("exp") or 0)
        if exp <= int(datetime.now(UTC).timestamp()):
            raise HTTPException(status_code=401, detail="Token expired.")
        return payload

    @staticmethod
    def _urlsafe_b64decode(value: str) -> bytes:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(f"{value}{padding}".encode("utf-8"))


auth_service = AuthService()

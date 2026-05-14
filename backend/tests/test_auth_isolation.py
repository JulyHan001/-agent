import asyncio
import os
import sys
import time
from pathlib import Path

import httpx


async def _request_and_expect_ok(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response:
    response = await client.request(method, url, **kwargs)
    response.raise_for_status()
    return response


def test_multi_user_session_isolation() -> None:
    output_dir = Path(__file__).resolve().parents[1] / "tmp"
    output_dir.mkdir(parents=True, exist_ok=True)
    backend_dir = Path(__file__).resolve().parents[1]
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    test_db_path = output_dir / "auth-isolation-test.db"
    if test_db_path.exists():
        for _ in range(5):
            try:
                test_db_path.unlink()
                break
            except PermissionError:
                time.sleep(0.2)

    os.environ["SQLITE_PATH"] = str(test_db_path)
    os.environ["MOCK_LLM"] = "true"

    from app.main import app

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
            timeout=90.0,
            trust_env=False,
        ) as client:
            send_code_user1 = (
                await _request_and_expect_ok(
                    client,
                    "POST",
                    "/api/auth/code/send",
                    json={
                        "phone": "13800138000",
                        "purpose": "register",
                    },
                )
            ).json()
            user1 = (
                await _request_and_expect_ok(
                    client,
                    "POST",
                    "/api/auth/register",
                    json={
                        "phone": "13800138000",
                        "code": send_code_user1["dev_code"],
                        "display_name": "User One",
                    },
                )
            ).json()
            send_code_user2 = (
                await _request_and_expect_ok(
                    client,
                    "POST",
                    "/api/auth/code/send",
                    json={
                        "phone": "13900139000",
                        "purpose": "register",
                    },
                )
            ).json()
            user2 = (
                await _request_and_expect_ok(
                    client,
                    "POST",
                    "/api/auth/register",
                    json={
                        "phone": "13900139000",
                        "code": send_code_user2["dev_code"],
                        "display_name": "User Two",
                    },
                )
            ).json()

            headers1 = {"Authorization": f"Bearer {user1['access_token']}"}
            headers2 = {"Authorization": f"Bearer {user2['access_token']}"}

            user1_chat = (
                await _request_and_expect_ok(
                    client,
                    "POST",
                    "/api/chat",
                    headers=headers1,
                    json={
                        "messages": [
                            {
                                "role": "user",
                                "content": "我在准备 Java 后端实习，请记住我的方向。",
                            }
                        ]
                    },
                )
            ).json()

            user1_session_id = user1_chat["session_id"]

            sessions_user1 = (
                await _request_and_expect_ok(
                    client,
                    "GET",
                    "/api/sessions",
                    headers=headers1,
                )
            ).json()
            sessions_user2 = (
                await _request_and_expect_ok(
                    client,
                    "GET",
                    "/api/sessions",
                    headers=headers2,
                )
            ).json()

            assert len(sessions_user1) == 1
            assert sessions_user1[0]["id"] == user1_session_id
            assert sessions_user2 == []

            forbidden = await client.get(
                f"/api/sessions/{user1_session_id}",
                headers=headers2,
            )
            assert forbidden.status_code == 404

    asyncio.run(run())

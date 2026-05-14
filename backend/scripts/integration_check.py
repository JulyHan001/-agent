import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx


def print_section(title: str, payload: object) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


async def request_and_expect_ok(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response:
    response = await client.request(method, url, **kwargs)
    if response.status_code >= 400:
        print_section(
            "HTTP_ERROR",
            {
                "method": method,
                "url": url,
                "status_code": response.status_code,
                "body": response.text,
            },
        )
        response.raise_for_status()
    return response


async def run_check() -> None:
    output_dir = Path(__file__).resolve().parents[1] / "tmp"
    output_dir.mkdir(parents=True, exist_ok=True)
    backend_dir = Path(__file__).resolve().parents[1]
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    test_db_path = output_dir / "integration-check.db"
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

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        timeout=90.0,
        trust_env=False,
    ) as client:
        auth_payload = None
        register_code_response = await client.post(
            "/api/auth/code/send",
            json={
                "phone": "13800138000",
                "purpose": "register",
            },
        )
        if register_code_response.status_code < 400:
            register_code_payload = register_code_response.json()
            register_response = await client.post(
                "/api/auth/register",
                json={
                    "phone": "13800138000",
                    "code": register_code_payload.get("dev_code"),
                    "display_name": "M4 Tester",
                },
            )
            if register_response.status_code < 400:
                auth_payload = register_response.json()
            elif register_response.status_code != 409:
                print_section(
                    "HTTP_ERROR",
                    {
                        "method": "POST",
                        "url": "/api/auth/register",
                        "status_code": register_response.status_code,
                        "body": register_response.text,
                    },
                )
                register_response.raise_for_status()
        elif register_code_response.status_code == 409:
            login_code_response = await request_and_expect_ok(
                client,
                "POST",
                "/api/auth/code/send",
                json={
                    "phone": "13800138000",
                    "purpose": "login",
                },
            )
            login_code_payload = login_code_response.json()
            login_response = await request_and_expect_ok(
                client,
                "POST",
                "/api/auth/login",
                json={
                    "phone": "13800138000",
                    "code": login_code_payload.get("dev_code"),
                },
            )
            auth_payload = login_response.json()
        else:
            print_section(
                "HTTP_ERROR",
                {
                    "method": "POST",
                    "url": "/api/auth/code/send",
                    "status_code": register_code_response.status_code,
                    "body": register_code_response.text,
                },
            )
            register_code_response.raise_for_status()

        access_token = auth_payload["access_token"]
        auth_headers = {"Authorization": f"Bearer {access_token}"}

        resume_text = """
张三
目标：后端开发实习
技术栈：Java、Spring Boot、MySQL
项目经历：秒杀系统项目，负责接口开发、库存扣减、Redis 缓存设计。
        """.strip()

        jd_text = """
岗位：后端开发实习生
职责：1. 参与业务后台接口开发与维护。2. 配合完成数据库设计、性能优化与问题排查。3. 参与微服务架构下的模块开发和单元测试。
要求：1. 熟悉 Java，了解 Spring Boot。2. 熟悉 MySQL，了解索引和 SQL 优化。3. 了解 Redis、消息队列，有 Linux 使用经验。4. 责任心强，沟通良好，有实习经历优先。
        """.strip()

        session_id = None
        turns = [
            "我在准备后端开发实习，技术栈主要是 Java、Spring Boot、MySQL。",
            "我最近在复习 Redis、操作系统和计网，简历里还有一个秒杀系统项目。",
            jd_text,
            "纠正一下，我最近的短期重点不是操作系统，而是补消息队列和 Linux。",
            "基于上面的背景和这个 JD，帮我整理一周面试准备重点。",
        ]

        chat_results = []
        for turn in turns:
            response = await request_and_expect_ok(
                client,
                "POST",
                "/api/chat",
                headers=auth_headers,
                json={
                    "session_id": session_id,
                    "messages": [{"role": "user", "content": turn}],
                },
            )
            payload = response.json()
            session_id = payload["session_id"]
            chat_results.append(
                {
                    "user": turn[:100],
                    "assistant_summary": payload["message"]["structured"]["summary"],
                    "tool_calls": payload["message"].get("tool_calls", []),
                }
            )

        session_response = await request_and_expect_ok(
            client,
            "GET",
            f"/api/sessions/{session_id}",
            headers=auth_headers,
        )
        session_payload = session_response.json()
        user_id = session_payload.get("user_id")

        tool_logs_response = await request_and_expect_ok(
            client,
            "GET",
            f"/api/sessions/{session_id}/tool-logs",
            headers=auth_headers,
        )
        tool_logs_payload = tool_logs_response.json()

        second_session_response = await request_and_expect_ok(
            client,
            "POST",
            "/api/chat",
            headers=auth_headers,
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "不重复介绍背景的话，你还记得我的目标岗位和技术栈吗？",
                    }
                ],
            },
        )
        second_session_payload = second_session_response.json()

        user_memory_response = await request_and_expect_ok(
            client,
            "GET",
            "/api/memory/user",
            headers=auth_headers,
        )
        user_memory_payload = user_memory_response.json()

        manual_memory_response = await request_and_expect_ok(
            client,
            "PUT",
            "/api/memory/user",
            headers=auth_headers,
            json={
                "key": "job_search_stage",
                "label": "求职阶段",
                "value": "后端实习冲刺期",
                "confidence": 0.98,
            },
        )
        manual_memory_payload = manual_memory_response.json()

        deleted_memory_response = await request_and_expect_ok(
            client,
            "DELETE",
            "/api/memory/user/job_search_stage",
            headers=auth_headers,
        )
        deleted_memory_payload = deleted_memory_response.json()

        candidate_memory_response = await request_and_expect_ok(
            client,
            "PUT",
            "/api/memory/user",
            headers=auth_headers,
            json={
                "key": "target_role",
                "label": "目标岗位",
                "value": "数据分析实习",
                "confidence": 0.99,
            },
        )
        candidate_memory_payload = candidate_memory_response.json()

        candidate_list_response = await request_and_expect_ok(
            client,
            "GET",
            "/api/memory/user/candidates",
            headers=auth_headers,
        )
        candidate_list_payload = candidate_list_response.json()

        approved_candidate_payload = None
        after_approve_memory_payload = None
        pending_candidates = candidate_list_payload.get("candidates", [])
        if pending_candidates:
            approve_response = await request_and_expect_ok(
                client,
                "POST",
                f"/api/memory/user/candidates/{pending_candidates[0]['id']}/approve",
                headers=auth_headers,
            )
            approved_candidate_payload = approve_response.json()
            after_approve_memory_payload = approved_candidate_payload.get("memory")

        reject_seed_response = await request_and_expect_ok(
            client,
            "PUT",
            "/api/memory/user",
            headers=auth_headers,
            json={
                "key": "project_experience",
                "label": "项目经历标签",
                "value": "数据看板项目",
                "confidence": 0.99,
            },
        )

        reject_candidate_list_response = await request_and_expect_ok(
            client,
            "GET",
            "/api/memory/user/candidates",
            headers=auth_headers,
        )
        reject_candidate_list_payload = reject_candidate_list_response.json()

        rejected_candidate_payload = None
        pending_candidates_for_reject = reject_candidate_list_payload.get("candidates", [])
        if pending_candidates_for_reject:
            reject_response = await request_and_expect_ok(
                client,
                "POST",
                f"/api/memory/user/candidates/{pending_candidates_for_reject[0]['id']}/reject",
                headers=auth_headers,
            )
            rejected_candidate_payload = reject_response.json()

        tools_response = await request_and_expect_ok(
            client,
            "GET",
            "/api/tools",
            headers=auth_headers,
        )
        tools_payload = tools_response.json()

        jd_response = await request_and_expect_ok(
            client,
            "POST",
            "/api/analyze/jd",
            headers=auth_headers,
            json={"jd_text": jd_text},
        )
        jd_payload = jd_response.json()

        resume_tailor_response = await request_and_expect_ok(
            client,
            "POST",
            "/api/tailor/resume",
            headers=auth_headers,
            json={
                "resume_text": resume_text,
                "jd_text": jd_text,
            },
        )
        resume_tailor_payload = resume_tailor_response.json()

    messages = session_payload.get("messages", [])
    latest_assistant_tool_calls = []
    for message in reversed(messages):
        if message.get("role") == "assistant":
            latest_assistant_tool_calls = message.get("tool_calls", [])
            break

    report = {
        "chat_results": chat_results,
        "session_id": session_id,
        "user_id": user_id,
        "auth_user": auth_payload.get("user"),
        "session_memory": session_payload.get("memory"),
        "user_memory": {
            "initial_memory": user_memory_payload.get("memory"),
            "manual_upsert_memory": manual_memory_payload.get("memory"),
            "after_delete_memory": deleted_memory_payload.get("memory"),
            "candidate_seed_memory": candidate_memory_payload.get("memory"),
            "pending_candidates_before_approve": candidate_list_payload.get("candidates", []),
            "approved_candidate": approved_candidate_payload,
            "after_candidate_approve_memory": after_approve_memory_payload,
            "pending_candidates_before_reject": reject_candidate_list_payload.get("candidates", []),
            "rejected_candidate": rejected_candidate_payload,
            "session_memory_stable_profile_count": len(
                (session_payload.get("memory") or {}).get("stable_profile", [])
            ),
            "second_session_summary": (
                (second_session_payload.get("message") or {}).get("structured") or {}
            ).get("summary"),
        },
        "message_count": len(messages),
        "latest_assistant_tool_calls": latest_assistant_tool_calls,
        "tool_execution_logs": tool_logs_payload,
        "tool_definitions": tools_payload,
        "jd_result": jd_payload.get("result"),
        "resume_tailor_result": resume_tailor_payload.get("result"),
    }

    output_path = output_dir / "integration-check-report.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print_section("CHAT_RESULTS", chat_results)
    print_section("SESSION_MEMORY", session_payload.get("memory"))
    print_section("USER_MEMORY", report["user_memory"])
    print_section("TOOL_EXECUTION_LOGS", tool_logs_payload)
    print_section("TOOLS", tools_payload)
    print_section("JD_RESULT", jd_payload.get("result"))
    print_section("RESUME_TAILOR_RESULT", resume_tailor_payload.get("result"))
    print(f"\nReport written to: {output_path}")


def main() -> None:
    asyncio.run(run_check())


if __name__ == "__main__":
    main()

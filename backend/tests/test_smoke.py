import json
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
PYTHON_EXE = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
REPORT_PATH = BACKEND_DIR / "tmp" / "integration-check-report.json"


def test_integration_script_generates_report() -> None:
    completed = subprocess.run(
        [str(PYTHON_EXE), "scripts/integration_check.py"],
        cwd=BACKEND_DIR,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr
    assert REPORT_PATH.exists()

    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))

    assert report["session_id"]
    assert report["user_id"]
    assert report["message_count"] >= 2
    assert report["session_memory"] is not None
    assert report["user_memory"] is not None
    assert report["user_memory"]["session_memory_stable_profile_count"] >= 1
    assert report["user_memory"]["second_session_summary"]
    assert report["user_memory"]["initial_memory"] is not None
    assert report["user_memory"]["manual_upsert_memory"] is not None
    assert report["user_memory"]["after_delete_memory"] is not None
    assert report["user_memory"]["pending_candidates_before_approve"]
    assert report["user_memory"]["approved_candidate"] is not None
    assert report["user_memory"]["approved_candidate"]["candidate"]["status"] == "approved"
    assert report["user_memory"]["after_candidate_approve_memory"] is not None
    assert report["user_memory"]["pending_candidates_before_reject"]
    assert report["user_memory"]["rejected_candidate"] is not None
    assert report["user_memory"]["rejected_candidate"]["candidate"]["status"] == "rejected"

    manual_values = [
        item["value"]
        for item in report["user_memory"]["manual_upsert_memory"]["stable_profile"]
    ]
    assert "后端实习冲刺期" in manual_values

    deleted_keys = [
        item["key"] for item in report["user_memory"]["after_delete_memory"]["stable_profile"]
    ]
    assert "job_search_stage" not in deleted_keys

    approved_values = [
        item["value"]
        for item in report["user_memory"]["after_candidate_approve_memory"]["stable_profile"]
    ]
    assert "数据分析实习" in approved_values
    assert (
        report["user_memory"]["rejected_candidate"]["candidate"]["value"]
        == "Java, Spring Boot, MySQL"
    )

    assert "confidence" in report["session_memory"]
    assert "source_turn_start" in report["session_memory"]
    assert "source_turn_end" in report["session_memory"]
    assert "stable_profile" in report["session_memory"]
    assert "temporary_state" in report["session_memory"]
    assert "conflicts" in report["session_memory"]
    assert report["session_memory"]["stable_profile"]
    assert report["session_memory"]["temporary_state"]
    assert report["tool_definitions"]
    assert report["tool_execution_logs"]
    assert report["jd_result"]["summary"]
    assert report["resume_tailor_result"]["summary"]
    assert "tailored_summary" in report["resume_tailor_result"]
    assert "keyword_additions" in report["resume_tailor_result"]
    assert (
        report["jd_result"]["resume_keywords"]
        or report["jd_result"]["interview_focus"]
        or report["jd_result"]["gap_analysis"]
    )
    assert any(
        tool["name"] == "resume_tailor" for tool in report["tool_definitions"]
    )

    jd_turn = next(
        (
            item
            for item in report["chat_results"]
            if "岗位：" in item["user"] or "职责：" in item["user"]
        ),
        None,
    )
    assert jd_turn is not None
    assert jd_turn["tool_calls"], report
    assert jd_turn["tool_calls"][0]["tool_name"] == "analyze_jd"
    assert jd_turn["tool_calls"][0]["status"] == "success"
    deep_result = jd_turn["tool_calls"][0]["result"]
    assert (
        deep_result["resume_keywords"]
        or deep_result["interview_focus"]
        or deep_result["gap_analysis"]
    )

    jd_tool_log = next(
        (item for item in report["tool_execution_logs"] if item["tool_name"] == "analyze_jd"),
        None,
    )
    assert jd_tool_log is not None
    assert jd_tool_log["status"] == "success"
    assert jd_tool_log["output_json"]["summary"]

    correction_turn = next(
        (item for item in report["chat_results"] if "纠正一下" in item["user"]),
        None,
    )
    assert correction_turn is not None

    temporary_values = [
        item["value"] for item in report["session_memory"]["temporary_state"]
    ]
    assert any("消息队列" in value or "Linux" in value for value in temporary_values)

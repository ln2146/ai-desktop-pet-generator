from __future__ import annotations

import json
from pathlib import Path

from petgen.hook_context import (
    antigravity_event_from_hook_input,
    claude_event_from_hook_input,
    codex_event_from_notify_args,
    compact_text,
    format_duration,
    summarize_agent_message,
)


def test_codex_notify_uses_final_message_and_duration() -> None:
    payload = {
        "type": "task_complete",
        "last_agent_message": "已修复托盘显示问题\n\n验证：283 passed",
        "duration_ms": 125000,
        "cwd": "/Users/loge/A_project/ai-desktop-pet-generator",
    }

    kind, title, detail = codex_event_from_notify_args([json.dumps(payload, ensure_ascii=False)])

    assert kind == "task_completed"
    assert title == "ai-desktop-pet-generator 已完成：已修复托盘显示问题"
    assert detail == "耗时 2 分 5 秒"


def test_codex_notify_permission_request_stays_responding() -> None:
    kind, title, detail = codex_event_from_notify_args(['{"type": "permission-request"}'])

    assert kind == "ai_responding"
    assert title == "需要处理：permission-request"
    assert detail is None


def test_codex_notify_falls_back_to_latest_session(tmp_path: Path) -> None:
    session_dir = tmp_path / ".codex" / "sessions" / "2026" / "07" / "24"
    session_dir.mkdir(parents=True)
    session = session_dir / "rollout.jsonl"
    session.write_text(
        json.dumps(
            {
                "type": "event_msg",
                "cwd": "/Users/loge/A_project/ai-desktop-pet-generator",
                "payload": {"type": "agent_message", "message": "working"},
            },
            ensure_ascii=False,
        )
        + "\n"
        +
        json.dumps(
            {
                "type": "event_msg",
                "payload": {
                    "type": "task_complete",
                    "last_agent_message": "已完成完成提示优化",
                    "duration_ms": 91000,
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    kind, title, detail = codex_event_from_notify_args(["turn-ended"], home=tmp_path)

    assert kind == "task_completed"
    assert title == "ai-desktop-pet-generator 已完成：已完成完成提示优化"
    assert detail == "耗时 1 分 31 秒"


def test_claude_hook_reads_transcript_for_task_summary(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "message": {"role": "user", "content": [{"type": "text", "text": "帮我优化任务完成提示"}]},
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {"role": "assistant", "content": [{"type": "text", "text": "已把完成提示改成包含任务摘要和耗时。"}]},
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    kind, title, detail = claude_event_from_hook_input(
        {
            "hook_event_name": "Stop",
            "transcript_path": str(transcript),
            "cwd": "/Users/loge/A_project/ai-desktop-pet-generator",
        },
        event_name="Stop",
        fallback_title="Claude 任务完成",
    )

    assert kind == "task_completed"
    assert title == "ai-desktop-pet-generator 已完成：已把完成提示改成包含任务摘要和耗时。"
    assert detail == "任务：帮我优化任务完成提示"


def test_claude_hook_prefers_result_and_skips_low_signal_closer(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "message": {"role": "user", "content": [{"type": "text", "text": "把三个工具提示统一"}]},
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "message": {"role": "assistant", "content": [{"type": "text", "text": "已统一 Codex、Claude Code、Antigravity 的完成提示格式。"}]},
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "message": {"role": "assistant", "content": [{"type": "text", "text": "后台正常运行中，如果您后续还有需求，随时告诉我。"}]},
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    _kind, title, detail = claude_event_from_hook_input(
        {
            "hook_event_name": "Stop",
            "transcriptPath": str(transcript),
            "workspacePaths": ["/Users/loge/A_project/ai-desktop-pet-generator"],
            "durationMs": 62000,
        },
        event_name="Stop",
        fallback_title="Claude 任务完成",
    )

    assert title == "ai-desktop-pet-generator 已完成：已统一 Codex、Claude Code、Antigravity 的完成提示格式。"
    assert detail == "任务：把三个工具提示统一；耗时 1 分 2 秒"


def test_antigravity_hook_uses_project_summary_and_duration() -> None:
    kind, title, detail = antigravity_event_from_hook_input(
        {
            "hook_event_name": "Stop",
            "workspace": "/Users/loge/A_project/ai-desktop-pet-generator",
            "summary": "已优化完成提示，包含项目和结果摘要。",
            "duration_ms": 45000,
        },
        event_name="Stop",
        fallback_title="Antigravity 任务完成",
    )

    assert kind == "task_completed"
    assert title == "ai-desktop-pet-generator 已完成：已优化完成提示，包含项目和结果摘要。"
    assert detail == "耗时 45 秒"


def test_antigravity_hook_falls_back_to_transcript_for_codex_like_summary(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "source": "USER_EXPLICIT",
                        "type": "USER_INPUT",
                        "content": "<USER_REQUEST> 这个改成自定义就好了 </USER_REQUEST>",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "source": "MODEL",
                        "type": "PLANNER_RESPONSE",
                        "content": "已按照您的指示，将重复模式下拉菜单与提醒卡片中的名称精简修改为 **`自定义`**，并已完成 Git 提交。",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "source": "MODEL",
                        "type": "PLANNER_RESPONSE",
                        "content": "应用在后台正常运行中。如果您后续还有任何需求，随时告诉我！",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    kind, title, detail = antigravity_event_from_hook_input(
        {
            "executionNum": 1,
            "terminationReason": "model_stop",
            "fullyIdle": True,
            "workspacePaths": ["/Users/loge/A_project/ai-desktop-pet-generator"],
            "transcriptPath": str(transcript),
        },
        event_name="Stop",
        fallback_title="Antigravity 任务完成",
    )

    assert kind == "task_completed"
    assert title == "ai-desktop-pet-generator 已完成：已按照您的指示，将重复模式下拉菜单与提醒卡片中的名称精简修改为 自定义，并已完成 Git 提交。"
    assert detail is None


def test_antigravity_hook_uses_user_task_when_transcript_has_no_final(tmp_path: Path) -> None:
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "content": "<USER_REQUEST> 优化 Antigravity 完成提示 </USER_REQUEST>",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    _kind, title, detail = antigravity_event_from_hook_input(
        {
            "terminationReason": "error",
            "error": "hook failed",
            "workspacePaths": ["/tmp/demo"],
            "transcriptPath": str(transcript),
        },
        event_name="Stop",
        fallback_title="Antigravity 任务完成",
    )

    assert title == "demo 已完成：优化 Antigravity 完成提示"
    assert detail == "停止原因：error；错误：hook failed"


def test_text_helpers_compact_without_hiding_absence() -> None:
    assert compact_text("  a\n b  ") == "a b"
    assert compact_text("查到了：**有一个相关项目**，路径是 `demo.py`") == "查到了：有一个相关项目，路径是 demo.py"
    assert format_duration(61000) == "耗时 1 分 1 秒"
    assert summarize_agent_message("qa_note=已检查通过\nbackend=x") == "已检查通过"

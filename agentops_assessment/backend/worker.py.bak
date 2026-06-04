from __future__ import annotations

from agentops_assessment.backend import database


def execute_run(run_id: str) -> None:
    """后台执行入口。

    TODO(candidate/P0): 用完整的 Planner -> Executor 流程替换此占位实现。
    预期实现应更新 running/completed/failed 状态，持久化步骤事件，
    通过 ToolRegistry 调用工具，记录 token 成本，并保存最终业务结果。
    """
    with database.connect() as conn:
        database.init_db(conn)
        now = database.now_iso()
        conn.execute(
            "UPDATE runs SET status = ?, started_at = ? WHERE id = ?",
            ("running", now, run_id),
        )
        database.insert_run_event(
            conn,
            run_id,
            "run.started",
            {"message": "起始 worker 运行到了占位实现。"},
        )
        conn.execute(
            """
            UPDATE runs
            SET status = ?, error = ?, finished_at = ?
            WHERE id = ?
            """,
            (
                "failed",
                "TODO(candidate/P0): 实现 Agent 规划和执行流程。",
                database.now_iso(),
                run_id,
            ),
        )
        conn.commit()

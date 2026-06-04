from __future__ import annotations
import json
import time
from agentops_assessment.backend import database
from agentops_assessment.agent.planner import create_plan
from agentops_assessment.agent.executor import execute_plan

def _extract_sku(prompt: str) -> str:
    import re
    match = re.search(r'SKU[-\s]?([A-Z0-9]+)', prompt, re.IGNORECASE)
    if match:
        return f"SKU-{match.group(1)}" if not match.group(0).startswith("SKU-") else match.group(0)
    return "SKU-001"

def execute_run(run_id: str) -> None:
    with database.connect() as conn:
        database.init_db(conn)
        run_row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not run_row:
            return
        task_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (run_row["task_id"],)).fetchone()
        if not task_row:
            return

        user_id = run_row["requested_by"]
        print(f"[WORKER] run_id={run_id}, user_id={user_id}, task_prompt={task_row['prompt']}")

        now = database.now_iso()
        conn.execute("UPDATE runs SET status = ?, started_at = ? WHERE id = ?", ("running", now, run_id))
        database.insert_run_event(conn, run_id, "run.started", {"message": "开始执行 Agent 计划"})

        try:
            task_dict = {"title": task_row["title"], "prompt": task_row["prompt"]}
            plan = create_plan(task_dict)
            print(f"[WORKER] plan={plan}")
            context = {"sku": _extract_sku(task_row["prompt"]), "prompt": task_row["prompt"], "warehouse": "WH-SH-01"}
            final_result, events = execute_plan(plan, context, user_id, task_row["id"], run_id, conn=conn)
            print(f"[WORKER] final_result approval_draft_id={final_result.get('approval_draft_id')}")
            cost = len(events) * 0.001
            for ev in events:
                database.insert_run_event(conn, run_id, ev["type"], payload=ev.get("payload", {}), tool_name=ev.get("tool_name"))
            conn.execute(
                "UPDATE runs SET status = ?, result_json = ?, token_cost = ?, finished_at = ? WHERE id = ?",
                ("completed", database.encode_json(final_result), int(cost), database.now_iso(), run_id)
            )
        except Exception as e:
            error_msg = str(e)
            print(f"[WORKER] ERROR: {error_msg}")
            conn.execute(
                "UPDATE runs SET status = ?, error = ?, finished_at = ? WHERE id = ?",
                ("failed", error_msg, database.now_iso(), run_id)
            )
            database.insert_run_event(conn, run_id, "run.failed", {"error": error_msg})
        conn.commit()

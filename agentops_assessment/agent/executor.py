import time
from typing import Dict, Any, List, Optional
from agentops_assessment.backend import tools
from agentops_assessment.backend.auth import has_permission
from agentops_assessment.backend.database import insert_audit_log_with_conn

TOOL_MAP = {
    "erp.get_inventory": tools.erp_get_inventory,
    "bi.get_sales": tools.bi_get_sales,
    "knowledge.search": tools.knowledge_search,
    "supplier.get_risk": tools.supplier_get_risk,
    "oa.create_approval_draft": tools.oa_create_approval_draft,
}

REQUIRED_PERMISSIONS = {
    "oa.create_approval_draft": "oa:approval:write",
}

def execute_plan(plan: List[str], context: Dict[str, Any], user_id: str, task_id: str, run_id: str, conn=None):
    results = {}
    events = []
    final = {
        "sku": context.get("sku", ""),
        "warehouse": context.get("warehouse", "WH-SH-01"),
        "stock_gap": None,
        "forecast_units_next_14d": None,
        "supplier_risk": {},
        "citations": [],
        "recommended_action": "",
        "approval_draft_id": None,
    }

    for seq, tool_name in enumerate(plan):
        required_perm = REQUIRED_PERMISSIONS.get(tool_name)
        if required_perm and not has_permission(user_id, required_perm):
            if conn:
                insert_audit_log_with_conn(conn, user_id, "tool.call", tool_name, "deny", {"reason": f"Missing permission {required_perm}"})
            events.append({
                "seq": seq, "type": "tool.call", "tool_name": tool_name,
                "payload": {"status": "skipped", "reason": "permission denied"},
                "created_at": time.time()
            })
            continue

        func = TOOL_MAP.get(tool_name)
        if not func:
            raise ValueError(f"Unknown tool: {tool_name}")

        try:
            if tool_name == "erp.get_inventory":
                out = func(sku=context.get("sku"), warehouse=context.get("warehouse", "WH-SH-01"))
                final["stock_gap"] = out.get("safety_stock", 0) - out.get("stock", 0)
            elif tool_name == "bi.get_sales":
                out = func(sku=context.get("sku"), days=14)
                final["forecast_units_next_14d"] = out.get("forecast_units_next_14d")
            elif tool_name == "knowledge.search":
                out = func(query=context.get("prompt", ""), user_id=user_id)
                final["citations"] = out.get("citations", [])
            elif tool_name == "supplier.get_risk":
                supplier_id = results.get("erp.get_inventory", {}).get("supplier_id", "default_supplier")
                out = func(supplier_id=supplier_id)
                final["supplier_risk"] = out
            elif tool_name == "oa.create_approval_draft":
                # 二次检查（防御）
                if not has_permission(user_id, required_perm):
                    if conn:
                        insert_audit_log_with_conn(conn, user_id, "tool.call", tool_name, "deny", {"reason": "Defensive check"})
                    events.append({
                        "seq": seq, "type": "tool.call", "tool_name": tool_name,
                        "payload": {"status": "skipped", "reason": "permission denied (secondary)"},
                        "created_at": time.time()
                    })
                    continue
                draft_data = {"title": f"补货审批 - {context.get('sku')}", "content": f"缺口: {final['stock_gap']}", "requester": user_id}
                out = func(data=draft_data, user_id=user_id)
                final["approval_draft_id"] = out.get("approval_draft_id")
                final["recommended_action"] = "create_replenishment_approval"
                if conn:
                    insert_audit_log_with_conn(conn, user_id, "approval.draft.create", out.get("approval_draft_id", ""), "allow", {"sku": context.get("sku")})
                else:
                    from agentops_assessment.backend.auth import write_audit_log
                    write_audit_log(user_id, "approval.draft.create", out.get("approval_draft_id", ""), "allow", {"sku": context.get("sku")})
            else:
                out = func()
            results[tool_name] = out
            events.append({
                "seq": seq, "type": "tool.call", "tool_name": tool_name,
                "payload": {"status": "success", "output_summary": str(out)[:200]},
                "created_at": time.time()
            })
        except Exception as e:
            events.append({
                "seq": seq, "type": "tool.call", "tool_name": tool_name,
                "payload": {"status": "failed", "error": str(e)},
                "created_at": time.time()
            })
            raise

    if final["approval_draft_id"] is None:
        final["recommended_action"] = "analysis_only"

    from agentops_assessment.backend.auth import sanitize_result
    final = sanitize_result(final)
    return final, events

from typing import List, Dict, Any

def create_plan(task: Dict[str, Any]) -> List[str]:
    prompt = task.get("prompt", "").lower()
    title = task.get("title", "").lower()

    should_write_oa = (
        ("创建审批" in prompt or "生成草稿" in prompt or "create approval" in prompt)
        and "只分析" not in prompt
        and "不要创建" not in prompt
    )

    base_plan = ["erp.get_inventory", "bi.get_sales", "knowledge.search", "supplier.get_risk"]
    if should_write_oa:
        base_plan.append("oa.create_approval_draft")
    return base_plan

def validate_plan(plan: List[str]) -> bool:
    required = ["erp.get_inventory", "bi.get_sales", "knowledge.search", "supplier.get_risk"]
    return all(r in plan for r in required)

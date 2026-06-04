import json
import os
from datetime import datetime
from typing import Dict, Any, List
import sqlite3

def _load_fixture(name: str) -> Any:
    fixture_dir = os.environ.get("ASSESSMENT_FIXTURES_DIR", "fixtures")
    path = os.path.join(fixture_dir, f"{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def erp_get_inventory(sku: str, warehouse: str = "WH-SH-01") -> Dict[str, Any]:
    inventory_data = _load_fixture("erp_inventory")
    for item in inventory_data:
        if item["sku"] == sku and item["warehouse"] == warehouse:
            safe_item = {k: v for k, v in item.items() if k not in ["unit_cost_usd", "vendor_secret"]}
            return safe_item
    return {"sku": sku, "warehouse": warehouse, "stock": 0, "safety_stock": 100}

def bi_get_sales(sku: str, days: int = 14) -> Dict[str, Any]:
    bi_data = _load_fixture("bi_forecast")
    for record in bi_data:
        if record["sku"] == sku:
            return {"sku": sku, "forecast_units_next_14d": record.get("forecast_units_next_14d", 0), "period_days": days}
    return {"sku": sku, "forecast_units_next_14d": 0, "period_days": days}

def knowledge_search(query: str, user_id: str) -> Dict[str, Any]:
    """
    直接查询数据库，执行关键词匹配和权限过滤，返回符合测评契约的结果。
    """
    db_path = os.environ.get("ASSESSMENT_DB_PATH", ".data/assessment.sqlite")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # 获取用户权限列表
    cursor.execute("SELECT permissions_json FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    user_permissions = json.loads(row[0]) if row else []
    # 查询所有知识库 chunks
    cursor.execute("SELECT id, doc_id, source_path, title, permission, content FROM knowledge_chunks")
    all_chunks = cursor.fetchall()
    conn.close()

    visible_chunks = []
    filtered_doc_ids = []
    for chunk_id, doc_id, source_path, title, permission, content in all_chunks:
        # 权限过滤
        if permission and permission not in user_permissions:
            filtered_doc_ids.append(doc_id)
            continue
        # 简单的关键词匹配（可扩展为更复杂的检索）
        if query.lower() in content.lower() or query.lower() in title.lower():
            visible_chunks.append({
                "doc_id": doc_id,
                "title": title,
                "source_path": source_path,
                "chunk_id": chunk_id,
                "content": content
            })

    # 生成简短 answer（取第一个可见 chunk 的前200字）
    answer = ""
    citations = []
    if visible_chunks:
        first = visible_chunks[0]
        answer = first["content"][:200] + ("..." if len(first["content"]) > 200 else "")
        citations = [{
            "doc_id": c["doc_id"],
            "title": c["title"],
            "source_path": c["source_path"],
            "chunk_id": c["chunk_id"]
        } for c in visible_chunks[:3]]  # 最多返回3个引用

    return {
        "answer": answer,
        "citations": citations,
        "filtered_doc_ids": filtered_doc_ids
    }

def supplier_get_risk(supplier_id: str) -> Dict[str, Any]:
    supplier_data = _load_fixture("suppliers")
    for s in supplier_data:
        if s["supplier_id"] == supplier_id:
            return {
                "supplier_id": supplier_id,
                "risk_level": s.get("risk_level", "unknown"),
                "summary": s.get("risk_summary", ""),
                "last_assessed": s.get("last_assessed", "")
            }
    return {"supplier_id": supplier_id, "risk_level": "unknown", "summary": "No data"}

def oa_create_approval_draft(data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    draft_id = f"OA-DRAFT-{int(datetime.now().timestamp())}"
    return {"approval_draft_id": draft_id, "title": data.get("title", "补货审批")}

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, Any, List
from fastapi import Depends, HTTPException, status, Header

DB_PATH = os.environ.get("ASSESSMENT_DB_PATH", ".data/assessment.sqlite")

def get_user_permissions(user_id: str) -> List[str]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT permissions_json FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return []
    permissions = json.loads(row[0])
    return permissions if isinstance(permissions, list) else []

def has_permission(user_id: str, required_permission: str) -> bool:
    return required_permission in get_user_permissions(user_id)

def write_audit_log(actor_id: str, action: str, resource: str, decision: str, payload: Dict[str, Any]):
    safe_payload = {k: v for k, v in payload.items() if k not in ["vendor_secret", "unit_cost_usd", "contract_detail", "debug", "candidate_note"]}
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO audit_logs (actor_id, action, resource, decision, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (actor_id, action, resource, decision, json.dumps(safe_payload), datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def sanitize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return result
    safe = {}
    for k, v in result.items():
        if k in ["vendor_secret", "unit_cost_usd", "contract_detail", "debug", "candidate_note"]:
            continue
        if isinstance(v, dict):
            safe[k] = sanitize_result(v)
        elif isinstance(v, list):
            safe[k] = [sanitize_result(item) for item in v]
        else:
            safe[k] = v
    return safe

def get_current_user(x_user_id: str = Header(None)) -> dict:
    if not x_user_id:
        raise HTTPException(status_code=400, detail="Missing X-User-Id header")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, permissions_json FROM users WHERE id = ?", (x_user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail=f"User {x_user_id} not found")
    return {
        "id": row[0],
        "name": row[1],
        "permissions": json.loads(row[2])
    }

def require_permissions(required: str):
    def dependency(user: dict = Depends(get_current_user)):
        if required not in user["permissions"]:
            # 按照测试期望的格式返回 403 错误
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"missing_permissions": [required]}
            )
        return user
    return dependency

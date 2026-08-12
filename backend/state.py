"""会话状态存储：SQLAlchemy + SQLite，单表 JSON 列存画像卡/大纲/消息/交付物。"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import Column, Text, create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

_engine = create_engine(f"sqlite:///{DATA_DIR / 'grill.db'}", connect_args={"check_same_thread": False})
_Session = sessionmaker(bind=_engine)
_Base = declarative_base()
_LOCK = threading.Lock()

CONFIDENCE_THRESHOLD = 0.8

# 画像卡必填/选填字段定义（label 与 PRD §3 对齐）
REQUIRED_FIELDS = {
    "position_name": "岗位名称",
    "job_category": "岗位类别",
    "degree_min": "学历门槛",
    "graduation_window": "届别/毕业时间",
    "base_city": "Base 地",
    "hard_skills": "核心技术要求",
    "must_have_experience": "必备经历",
}
OPTIONAL_FIELDS = {
    "bonus_items": "加分项",
    "soft_traits": "软素质偏好",
    "target_schools": "目标院校倾向",
    "team_fit": "团队匹配/培养预期",
}


class SessionORM(_Base):
    __tablename__ = "sessions"

    id = Column(Text, primary_key=True)
    created_at = Column(Text)
    updated_at = Column(Text)
    profile = Column(Text)      # 画像卡 JSON
    outline = Column(Text)      # 提问大纲节点列表 JSON
    messages = Column(Text)     # 对话历史 JSON [{role, text, tools}]
    deliverables = Column(Text) # 三件套 JSON，finalize 后写入
    converged = Column(Text)    # "0"/"1"
    running = Column(Text)      # "0"/"1"：Agent 是否正在生成（worker 线程存活期间为 1）


_Base.metadata.create_all(_engine)

with _engine.begin() as _conn:
    # 老库补 running 列；启动即清零（进程重启意味着所有 worker 线程已死）
    _cols = [r[1] for r in _conn.execute(text("PRAGMA table_info(sessions)"))]
    if "running" not in _cols:
        _conn.execute(text("ALTER TABLE sessions ADD COLUMN running TEXT DEFAULT '0'"))
    _conn.execute(text("UPDATE sessions SET running = '0'"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_profile() -> dict[str, Any]:
    def field(label: str) -> dict[str, Any]:
        return {"label": label, "value": None, "confidence": 0.0, "evidence": "", "status": "empty"}

    return {
        "required_fields": {k: field(v) for k, v in REQUIRED_FIELDS.items()},
        "optional_fields": {k: field(v) for k, v in OPTIONAL_FIELDS.items()},
        "conflicts": [],
        "converged": False,
    }


def create_session() -> dict[str, Any]:
    sid = "s_" + uuid.uuid4().hex[:12]
    now = _now()
    with _LOCK, _Session() as db:
        db.add(SessionORM(
            id=sid, created_at=now, updated_at=now,
            profile=json.dumps(empty_profile(), ensure_ascii=False),
            outline="[]", messages="[]", deliverables="", converged="0",
        ))
        db.commit()
    return get_session(sid)


def get_session(sid: str) -> dict[str, Any] | None:
    with _Session() as db:
        rec = db.get(SessionORM, sid)
        if rec is None:
            return None
        return _to_dict(rec)


def _title_of(sess: dict[str, Any]) -> str:
    # 标题策略：岗位名称 → 首条用户消息截断 → 未命名会话
    pos = (sess["profile"].get("required_fields", {}).get("position_name") or {}).get("value")
    if isinstance(pos, list):
        pos = "、".join(map(str, pos))
    if pos:
        return str(pos)[:30]
    for m in sess["messages"]:
        if m.get("role") == "user" and str(m.get("text") or "").strip():
            return str(m["text"]).strip()[:20]
    return "未命名会话"


def delete_sessions(sids: list[str]) -> int:
    """删除会话：单表存储，删行即级联清掉消息/画像卡/大纲/三件套。"""
    with _LOCK, _Session() as db:
        n = db.query(SessionORM).filter(SessionORM.id.in_(sids)).delete(synchronize_session=False)
        db.commit()
    return n


def list_sessions() -> list[dict[str, Any]]:
    """会话列表（侧栏用）：按最后活跃倒序。"""
    with _Session() as db:
        recs = db.query(SessionORM).all()
    out = []
    for rec in recs:
        sess = _to_dict(rec)
        out.append({
            "session_id": sess["session_id"],
            "title": _title_of(sess),
            "created_at": sess["created_at"],
            "updated_at": sess["updated_at"],
            "status": "已交付" if sess["deliverables"] else ("已澄清" if sess["converged"] else "进行中"),
        })
    out.sort(key=lambda s: s["updated_at"], reverse=True)
    return out


def save_session(sid: str, **fields: Any) -> None:
    """可更新键：profile / outline / messages / deliverables / converged。"""
    with _LOCK, _Session() as db:
        rec = db.get(SessionORM, sid)
        if rec is None:
            return
        for key, value in fields.items():
            if key in ("profile", "outline", "messages", "deliverables"):
                setattr(rec, key, json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value)
            elif key == "converged":
                rec.converged = "1" if value else "0"
            elif key == "running":
                rec.running = "1" if value else "0"
        rec.updated_at = _now()
        db.commit()


def check_converged(profile: dict[str, Any]) -> bool:
    return all(
        float(f.get("confidence") or 0) >= CONFIDENCE_THRESHOLD
        for f in profile.get("required_fields", {}).values()
    )


def _to_dict(rec: SessionORM) -> dict[str, Any]:
    return {
        "session_id": rec.id,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
        "profile": json.loads(rec.profile or "{}"),
        "outline": json.loads(rec.outline or "[]"),
        "messages": json.loads(rec.messages or "[]"),
        "deliverables": json.loads(rec.deliverables) if rec.deliverables else None,
        "converged": rec.converged == "1",
        "running": getattr(rec, "running", "0") == "1",
    }

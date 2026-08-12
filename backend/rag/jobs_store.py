"""岗位检索：embedding + Qdrant 封装，供 Agent 工具与 ingestion 共用。"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.core.embedding import embed_texts
from backend.core.vector_store import CURRENT_INDEX_VERSION, QdrantVectorStore

_STORE: QdrantVectorStore | None = None
_FULL_JOBS: dict[str, dict] | None = None
# 完整 JD 源数据（ingest 同一来源，只读回补 description/requirement）
_DEFAULT_FULL = Path(__file__).resolve().parents[2] / "data" / "jobs" / "campus_jobs_all.json"
_FULL_PATH = Path(os.getenv("JOBS_FULL_JSON", "") or _DEFAULT_FULL)


def _full_jobs() -> dict[str, dict]:
    global _FULL_JOBS
    if _FULL_JOBS is None:
        if not _FULL_PATH.exists():
            raise RuntimeError(f"完整岗位数据不存在：{_FULL_PATH}（先跑 scripts/ingest_jobs.py 或配置 JOBS_FULL_JSON）")
        raw = json.load(open(_FULL_PATH, encoding="utf-8"))
        records = raw["jobs"] if isinstance(raw, dict) else raw
        _FULL_JOBS = {str(r["id"]): r for r in records}
    return _FULL_JOBS


def get_store() -> QdrantVectorStore:
    global _STORE
    if _STORE is None:
        _STORE = QdrantVectorStore(collection="campus_jobs")
    return _STORE


def search_jobs(query: str, top_k: int = 5, job_category: str | None = None,
                score_threshold: float = 0.3) -> list[dict[str, Any]]:
    """向量检索真实校招岗位；失败时返回空列表（检索只影响话术不伤主链路）。"""
    vector = embed_texts([query])[0]
    filters = {"job_category": job_category} if job_category else None
    hits = get_store().search(vector, top_k=top_k, filters=filters)
    jobs = []
    for hit in hits:
        if hit.score < score_threshold:
            continue
        p = hit.payload
        full = _full_jobs().get(str(p.get("job_id"))) or {}
        jobs.append({
            "job_id": p.get("job_id"),
            "title": p.get("title"),
            "job_category": p.get("job_category"),
            "city_info": p.get("city_info"),
            "recruit_type": p.get("recruit_type"),
            "requirement_excerpt": p.get("requirement_excerpt"),
            "description": full.get("description") or "",
            "requirement": full.get("requirement") or "",
            "score": round(hit.score, 4),
        })
    return jobs


def indexed_count() -> int:
    return get_store().count()


def full_job(job_id: str) -> dict | None:
    """按 job_id 取完整岗位记录（含 description/requirement 全文）。"""
    return _full_jobs().get(str(job_id))


def find_by_title(title: str) -> dict | None:
    """按标题精确匹配岗位记录（蓝本句式兜底）。"""
    for r in _full_jobs().values():
        if (r.get("title") or "") == title:
            return r
    return None


__all__ = ["get_store", "search_jobs", "indexed_count", "full_job", "find_by_title", "CURRENT_INDEX_VERSION"]

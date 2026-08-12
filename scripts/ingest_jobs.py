"""校招岗位一次性入库：合并去重 → 拼检索文本 → embedding → Qdrant upsert。"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.core.embedding import MAX_INPUTS_PER_BATCH, embed_texts  # noqa: F401
from backend.core.embedding import EMBEDDING_DIM
from backend.core.vector_store import CURRENT_INDEX_VERSION, VectorPoint
from backend.rag.jobs_store import get_store

DATA_DIR = Path(os.getenv("JOBS_DATA_DIR", "") or Path(__file__).resolve().parents[1] / "data" / "jobs")
SOURCE_FILES = [
    "campus_jobs_all.json",  # 权威源，按 id 优先
    "campus_jobs.json",
    "campus_jobs_2.json",
]
UPSERT_BATCH = 64


def load_jobs() -> list[dict]:
    jobs: dict[str, dict] = {}
    for name in SOURCE_FILES:
        path = DATA_DIR / name
        if not path.exists():
            continue  # 源文件可选，有几个读几个
        raw = json.load(open(path, encoding="utf-8"))
        records = raw["jobs"] if isinstance(raw, dict) else raw
        for rec in records:
            jobs.setdefault(str(rec["id"]), rec)  # 按 id 去重，all 文件优先
    return list(jobs.values())


def city_names(rec: dict) -> str:
    info = rec.get("city_info")
    if isinstance(info, dict):
        info = [info]
    if isinstance(info, list):
        names = [str(c.get("name") or "") for c in info if isinstance(c, dict)]
        return "/".join(n for n in names if n)
    return str(info or "")


def category_name(rec: dict) -> str:
    cat = rec.get("job_category")
    return str(cat.get("name") or "") if isinstance(cat, dict) else str(cat or "")


def recruit_type_name(rec: dict) -> str:
    rt = rec.get("recruit_type")
    return str(rt.get("name") or "") if isinstance(rt, dict) else str(rt or "")


def build_text(rec: dict) -> str:
    parts = [
        rec.get("title") or "",
        rec.get("sub_title") or "",
        category_name(rec),
        city_names(rec),
        rec.get("description") or "",
        rec.get("requirement") or "",
    ]
    return "\n".join(p for p in parts if p)


def build_payload(rec: dict) -> dict:
    return {
        "job_id": str(rec["id"]),
        "title": rec.get("title") or "",
        "job_category": category_name(rec),
        "city_info": city_names(rec),
        "recruit_type": recruit_type_name(rec),
        "requirement_excerpt": (rec.get("requirement") or "")[:300],
        "index_version": CURRENT_INDEX_VERSION,
    }


def embed_with_retry(texts: list[str], retries: int = 3) -> list[list[float]]:
    for attempt in range(retries):
        try:
            return embed_texts(texts)
        except Exception as exc:
            if attempt + 1 == retries:
                raise
            wait = 2.0 ** attempt * 5
            print(f"  embedding 批次失败({exc})，{wait:.0f}s 后重试", flush=True)
            time.sleep(wait)
    return []


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    jobs = load_jobs()
    print(f"合并去重后岗位数：{len(jobs)}", flush=True)

    store = get_store()
    store.ensure_collection(EMBEDDING_DIM)

    texts = [build_text(rec) for rec in jobs]
    total = 0
    for start in range(0, len(jobs), UPSERT_BATCH):
        batch_jobs = jobs[start:start + UPSERT_BATCH]
        vectors = embed_with_retry(texts[start:start + UPSERT_BATCH])
        points = [
            VectorPoint(vector=v, payload=build_payload(rec), point_id=int(rec["id"]))
            for rec, v in zip(batch_jobs, vectors)
        ]
        store.upsert(points)
        total += len(points)
        print(f"已入库 {total}/{len(jobs)}", flush=True)

    count = store.count()
    print(f"Qdrant 向量数：{count}（岗位数 {len(jobs)}）", flush=True)
    assert count == len(jobs), "向量数与岗位数不一致"

    from backend.rag.jobs_store import search_jobs
    for q in ["抖音电商后端开发", "推荐算法工程师", "产品经理"]:
        hits = search_jobs(q, top_k=3)
        print(f"抽样检索「{q}」: " + "; ".join(f"{h['title']}({h['score']})" for h in hits), flush=True)


if __name__ == "__main__":
    main()

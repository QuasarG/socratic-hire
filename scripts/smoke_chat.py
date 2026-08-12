"""后端冒烟：建会话 → 发 3 轮消息 → 校验画像卡/大纲变化；第 4 轮可选确认 finalize。

用法：先起后端（conda run -n usuall python -m backend.app），再跑本脚本。
"""
from __future__ import annotations

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8510"

# 按演示剧本设计的回答：模糊开场 → 具体化 → 明确硬门槛
TURNS = [
    "我们想招个后端，抖音电商方向的。",
    "要技术扎实的，Java 或 Go 至少一个扎实，做过完整项目，本科及以上，27 届，Base 北京。",
    "对，实习经历至少一段对口的；竞赛获奖是加分项不强制。",
    "岗位就叫后端开发工程师（抖音电商），岗位类别研发-后端。我选 B：实战产出优先、原理深度次之，扎实的定义就是真扛过线上流量。",
    "流量证据 A 或 B 我都认，C 不算。软素质要皮实能扛压，三个月内能独立接需求。",
    "画像总结确认无误，请生成三件套。",
]


def post(path: str, body: dict):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req)


def get(path: str):
    return json.load(urllib.request.urlopen(BASE + path))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sid = json.load(urllib.request.urlopen(urllib.request.Request(BASE + "/api/sessions", data=b"{}")))["session_id"]
    print(f"session: {sid}")

    for i, text in enumerate(TURNS, 1):
        print(f"\n=== 第 {i} 轮：{text}")
        events = {"profile": 0, "outline": 0, "tools": []}
        with post("/api/chat", {"session_id": sid, "message": text}) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                evt = json.loads(line[6:])
                t, p = evt["type"], evt["payload"]
                if t == "answer_delta":
                    print(p["text"], end="", flush=True)
                elif t == "tool_end":
                    events["tools"].append(f"{p['tool']}({p['status']})")
                elif t == "profile_update":
                    events["profile"] += 1
                elif t == "outline_update":
                    events["outline"] += 1
                elif t == "deliverables":
                    print("\n[deliverables 已生成]")
                elif t == "error":
                    print(f"\n[error] {p['message']}")
        print(f"\n--- 工具: {events['tools']} | profile_update×{events['profile']} outline_update×{events['outline']}")

        st = get(f"/api/sessions/{sid}/state")
        req_fields = st["profile"]["required_fields"]
        filled = {k: (v["value"], v["confidence"]) for k, v in req_fields.items() if v["value"]}
        print(f"--- 必填已填 {len(filled)}/{len(req_fields)}: {json.dumps(filled, ensure_ascii=False)[:400]}")
        print(f"--- 大纲节点 {len(st['outline'])}: " + "; ".join(f"{n['topic']}[{n['status']}]" for n in st["outline"][:8]))
        print(f"--- converged={st['converged']} deliverables={'有' if st['deliverables'] else '无'}")

    print("\n冒烟完成")


if __name__ == "__main__":
    main()

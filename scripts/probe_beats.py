# -*- coding: utf-8 -*-
# 固定节拍冒烟：脚本问题 → 检索授权 → 选好出卡片 → 加分项多选固定问题
import json, sys, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "http://127.0.0.1:8510"

def chat(sid, text):
    req = urllib.request.Request(
        BASE + "/api/chat",
        data=json.dumps({"session_id": sid, "message": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    tools, askq, jobs = [], None, None
    with urllib.request.urlopen(req, timeout=170) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data: "):
                continue
            evt = json.loads(line[6:])
            if evt["type"] == "tool_end":
                tools.append(evt["payload"]["tool"])
                if evt["payload"]["tool"] == "ask_question":
                    askq = json.loads(evt["payload"]["detail"])
                if evt["payload"]["tool"] == "search_jobs":
                    jobs = json.loads(evt["payload"]["detail"])["jobs"]
    return tools, askq, jobs

sid = json.load(urllib.request.urlopen(urllib.request.Request(BASE + "/api/sessions", data=b"{}")))["session_id"]
print("session:", sid, flush=True)

msg = "我们想招个后端，抖音电商方向的。"
seen = {"scripted": False, "auth": False, "cards": False, "bonus": False}
for rnd in range(1, 8):
    tools, q, jobs = chat(sid, msg)
    qs = (q or {}).get("questions") or [{"text": (q or {}).get("question", "?"), "options": (q or {}).get("options"), "multi_select": (q or {}).get("multi_select")}]
    print(f"[R{rnd}] tools={tools}", flush=True)
    for s in qs:
        print(f"      Q: {s['text'][:70]} | multi={bool(s.get('multi_select'))} | opts={s.get('options')}", flush=True)
    if "一句话" in qs[0]["text"]:
        seen["scripted"] = True
    if any("检索" in s["text"] for s in qs):
        seen["auth"] = True
    if "search_jobs" in tools:
        seen["cards"] = True
        print(f"      岗位卡 {len(jobs or [])} 张", flush=True)
    if any("加分" in s["text"] for s in qs):
        seen["bonus"] = True
        print("      ★ 加分项固定问题", flush=True)
        break
    # 答题策略：授权题选「好」；契合度题选第一张卡；其余选第一项
    if any("检索" in s["text"] for s in qs):
        msg = "【选择了预设选项】好，帮我检索匹配"
    elif "search_jobs" in tools and jobs:
        msg = f"【选择了预设选项】我觉得「{jobs[0]['title']}」和我的需求最契合"
    elif q and q.get("options"):
        msg = "【选择了预设选项】" + q["options"][0]
    else:
        msg = "都可以，继续问"

print("\n节拍覆盖:", seen)

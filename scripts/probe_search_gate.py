# -*- coding: utf-8 -*-
# 重复检索闸门冒烟：选定蓝本后 3 轮不再检索；说「换一批」后允许重检
import json, sys, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "http://127.0.0.1:8510"

def chat(sid, text):
    req = urllib.request.Request(
        BASE + "/api/chat",
        data=json.dumps({"session_id": sid, "message": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    tools, askq, jobs, search_err = [], None, None, []
    with urllib.request.urlopen(req, timeout=170) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data: "):
                continue
            evt = json.loads(line[6:])
            if evt["type"] == "tool_end":
                p = evt["payload"]
                tools.append(p["tool"])
                if p["tool"] == "ask_question":
                    askq = json.loads(p["detail"])
                if p["tool"] == "search_jobs":
                    d = json.loads(p["detail"])
                    if d.get("ok"):
                        jobs = d["jobs"]
                    else:
                        search_err.append(p["summary"])
    return tools, askq, jobs, search_err

sid = json.load(urllib.request.urlopen(urllib.request.Request(BASE + "/api/sessions", data=b"{}")))["session_id"]
print("session:", sid, flush=True)

msg = "我们想招个推荐算法工程师，电商方向。"
picked = False
for rnd in range(1, 10):
    tools, q, jobs, errs = chat(sid, msg)
    qt = (q or {}).get("question", "?")
    print(f"[R{rnd}] tools={tools} | Q: {qt[:50]}", flush=True)
    if errs:
        print(f"      检索被拒: {errs[0][:60]}", flush=True)
    if jobs:
        print(f"      岗位卡 {len(jobs)} 张", flush=True)
    if not picked and jobs:
        msg = f"【选择了预设选项】我觉得「{jobs[0]['title']}」和我的需求最契合"
        picked = True
        continue
    if picked and rnd >= 8:
        msg = "以上岗位都不太符合我的需求，换一批"
        print("      → 发送重检请求", flush=True)
        continue
    if q and q.get("options"):
        msg = "【选择了预设选项】" + q["options"][0]
    else:
        msg = "都可以，继续问"

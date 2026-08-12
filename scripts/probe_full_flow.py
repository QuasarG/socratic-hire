# -*- coding: utf-8 -*-
# 全流程冒烟：收敛维度覆盖 + 取舍题范式 + finalize 不自动弹
import json, sys, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "http://127.0.0.1:8510"

def chat(sid, text):
    req = urllib.request.Request(
        BASE + "/api/chat",
        data=json.dumps({"session_id": sid, "message": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    tools, text_out, askq, got_deliv = [], [], None, False
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
            elif evt["type"] == "answer_delta":
                text_out.append(evt["payload"]["text"])
            elif evt["type"] == "deliverables":
                got_deliv = True
    return tools, "".join(text_out), askq, got_deliv

sid = json.load(urllib.request.urlopen(urllib.request.Request(BASE + "/api/sessions", data=b"{}")))["session_id"]
print("session:", sid, flush=True)

msg = "我们想招个后端，抖音电商交易链路，27届校招，Base 北京，本科及以上，Go 或 Java 扎实，至少一段对口实习。"
summary_at = None
tradeoff_q = None
for rnd in range(1, 15):
    tools, text, q, deliv = chat(sid, msg)
    qt = (q or {}).get("question", "")
    mech = (q or {}).get("mechanism", "")
    print(f"[R{rnd}] tools={tools}", flush=True)
    if qt:
        print(f"      Q[{mech}]: {qt[:90]}", flush=True)
    if text:
        print(f"      正文: {text[:80]}", flush=True)
    if mech == "tradeoff" and not tradeoff_q:
        tradeoff_q = qt
    if deliv:
        print("      ★ deliverables 事件到达", flush=True)
        break
    if "总结" in text and "确认" in text and summary_at is None:
        summary_at = rnd
        st = json.load(urllib.request.urlopen(f"{BASE}/api/sessions/{sid}/state"))
        opt = st["profile"]["optional_fields"]
        cov = {k: bool(v["value"]) for k, v in opt.items()}
        print(f"      ★ 总结出现于 R{rnd}，选填覆盖: {cov}", flush=True)
        msg = "画像总结确认无误，请生成需求包。"
        continue
    if "检索" in qt and q.get("options"):
        msg = "【选择了预设选项】不用了，直接继续聊"
    elif q and q.get("options"):
        msg = "【选择了预设选项】" + q["options"][0]
    else:
        msg = "基础扎实优先，但最好也有点业务感觉；软素质要皮实能扛压，三个月内独立接需求。"

print("\ntradeoff 样例:", tradeoff_q or "(未出现)")
print("总结轮次:", summary_at)

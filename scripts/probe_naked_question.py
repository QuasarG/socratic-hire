# -*- coding: utf-8 -*-
# 6 轮真实对话：统计每轮 ask_question 覆盖率 + 正文裸问残余
import json, re, sys, time, urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = "http://127.0.0.1:8510"
QRE = re.compile(r"[吗呢？?]|什么|哪[里些个一]|怎么|如何|是否")

def chat(sid, text):
    req = urllib.request.Request(
        BASE + "/api/chat",
        data=json.dumps({"session_id": sid, "message": text}).encode(),
        headers={"Content-Type": "application/json"},
    )
    tools, text_out, askq = [], [], None
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
    return tools, "".join(text_out), askq

sid = json.load(urllib.request.urlopen(urllib.request.Request(BASE + "/api/sessions", data=b"{}")))["session_id"]
print("session:", sid, flush=True)

msg = "我们想招个后端，抖音电商方向的。"
covered = naked = 0
for rnd in range(1, 7):
    t0 = time.time()
    tools, text, askq = chat(sid, msg)
    has_card = "ask_question" in tools
    has_naked = bool(QRE.search(text))
    covered += has_card
    naked += has_naked and not has_card
    print(f"[R{rnd}] {time.time()-t0:.0f}s card={has_card} 正文疑问={has_naked} | tools={tools}", flush=True)
    print(f"      正文: {text[:80]!r}", flush=True)
    if askq:
        print(f"      提问: {askq['question'][:60]}", flush=True)
    msg = "【选择了预设选项】" + (askq["options"][0] if askq and askq.get("options") else "都可以，继续问")

print(f"\n提问卡覆盖率: {covered}/6 | 裸问无卡轮次: {naked}")

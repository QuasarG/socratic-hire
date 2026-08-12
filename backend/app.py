"""Flask 入口：会话 API + SSE 聊天 + 静态前端（dist 存在时）。端口 8510。"""
from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

from backend import state
from backend.agent.service import chat_events

DIST_DIR = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def _sse_response(events) -> Response:
    def generate():
        for event in events:
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

    response = Response(stream_with_context(generate()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(DIST_DIR), static_url_path="")

    @app.post("/api/sessions")
    def create_session():
        sess = state.create_session()
        return jsonify({"session_id": sess["session_id"]}), 201

    @app.get("/api/sessions")
    def list_sessions():
        return jsonify({"sessions": state.list_sessions()})

    @app.delete("/api/sessions/<sid>")
    def delete_session(sid: str):
        if state.get_session(sid) is None:
            return jsonify({"detail": "会话不存在"}), 404
        state.delete_sessions([sid])
        return jsonify({"deleted": 1})

    @app.post("/api/sessions/batch-delete")
    def batch_delete_sessions():
        body = request.get_json(silent=True) or {}
        sids = [str(s) for s in body.get("session_ids") or [] if str(s).strip()]
        if not sids:
            return jsonify({"detail": "session_ids 必填"}), 400
        return jsonify({"deleted": state.delete_sessions(sids)})

    @app.get("/api/sessions/<sid>/state")
    def get_state(sid: str):
        sess = state.get_session(sid)
        if sess is None:
            return jsonify({"detail": "会话不存在"}), 404
        return jsonify(sess)

    @app.get("/api/sessions/<sid>/deliverables")
    def get_deliverables(sid: str):
        sess = state.get_session(sid)
        if sess is None:
            return jsonify({"detail": "会话不存在"}), 404
        if not sess["deliverables"]:
            return jsonify({"detail": "尚未生成需求包"}), 404
        return jsonify(sess["deliverables"])

    @app.post("/api/sessions/<sid>/deliverables/regenerate")
    def regenerate_deliverables(sid: str):
        sess = state.get_session(sid)
        if sess is None:
            return jsonify({"detail": "会话不存在"}), 404
        if not sess["deliverables"]:
            return jsonify({"detail": "需求包尚未生成，无法重新生成"}), 400
        from backend.agent.tools import generate_deliverables

        try:
            deliverables = generate_deliverables(sess)
        except Exception as exc:  # noqa: BLE001 失败不动旧 deliverables
            return jsonify({"detail": f"生成失败：{exc}"}), 500
        state.save_session(sid, deliverables=deliverables)
        return jsonify(deliverables)

    @app.post("/api/chat")
    def chat():
        body = request.get_json(silent=True) or {}
        sid = str(body.get("session_id") or "").strip()
        message = str(body.get("message") or "").strip()
        if not sid or not message:
            return jsonify({"detail": "session_id 与 message 必填"}), 400
        sess = state.get_session(sid)
        if sess is None:
            return jsonify({"detail": "会话不存在"}), 404
        if sess.get("running"):
            return jsonify({"detail": "上一条回复还在生成中，请稍候"}), 409
        return _sse_response(chat_events(sid, message))

    @app.get("/")
    def index():
        if (DIST_DIR / "index.html").exists():
            return send_from_directory(DIST_DIR, "index.html")
        return jsonify({"detail": "前端未构建，请用 vite dev（5174）或先 npm run build"})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8510, threaded=True, debug=False)

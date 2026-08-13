import { useCallback, useEffect, useRef, useState } from "react";
import { chatStream, createSession, deleteSessions, getState, listSessions, parseSSE, regenerateDeliverables } from "@/lib/api";
import type { SessionSummary } from "@/lib/api";
import type {
  ChatMessage,
  ChatSegment,
  Deliverables,
  OutlineNode,
  ProfileCard,
  StoredMessage,
} from "@/types";
import PageToolbar from "@/components/layout/PageToolbar";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Icon from "@/components/ui/Icon";
import LoadingIndicator from "@/components/ui/LoadingIndicator";
import OnboardingTour, { resetOnboarding } from "@/components/OnboardingTour";
import ChatInput from "@/features/chat/ChatInput";
import AssistantMessage from "@/features/chat/AssistantMessage";
import SessionSidebar from "@/features/chat/SessionSidebar";
import OutlinePanel from "@/features/clarify/OutlinePanel";
import ProfileCardPanel from "@/features/clarify/ProfileCardPanel";
import DeliverablesPanel from "@/features/clarify/DeliverablesPanel";

interface SseEvent {
  type: string;
  payload: Record<string, unknown>;
}

/** 历史消息（文本 + 工具记录）→ segments 渲染模型 */
function storedToSegments(m: StoredMessage): ChatSegment[] {
  const segments: ChatSegment[] = [];
  if (m.text.trim()) segments.push({ type: "text", text: m.text });
  (m.tools || []).forEach((t, i) =>
    segments.push({
      type: "tool",
      call_id: `hist-${i}-${t.tool}`,
      tool: t.tool,
      label: t.label,
      status: t.status === "ok" ? "ok" : "error",
      summary: t.summary,
      detail: t.detail,
    })
  );
  return segments;
}

/** 逐事件更新正在流式生成的 assistant 消息（按 call_id 匹配工具卡片） */
function applyEvent(msg: ChatMessage, e: SseEvent): ChatMessage {
  const segments = [...msg.segments];
  const p = e.payload as { text?: string; call_id?: string; tool?: string; label?: string; args_summary?: string; status?: string; summary?: string; detail?: string; message?: string };
  switch (e.type) {
    case "answer_delta": {
      const last = segments[segments.length - 1];
      if (last?.type === "text") {
        segments[segments.length - 1] = { ...last, text: last.text + (p.text || "") };
      } else {
        segments.push({ type: "text", text: p.text || "" });
      }
      return { ...msg, segments };
    }
    case "tool_start":
      segments.push({
        type: "tool",
        call_id: p.call_id || "",
        tool: p.tool || "",
        label: p.label || "",
        args_summary: p.args_summary,
      });
      return { ...msg, segments };
    case "tool_end": {
      const idx = segments.findIndex((s) => s.type === "tool" && s.call_id === p.call_id);
      if (idx >= 0) {
        segments[idx] = {
          ...(segments[idx] as ChatSegment & { type: "tool" }),
          status: p.status === "ok" ? "ok" : "error",
          summary: p.summary,
          detail: p.detail,
        };
      }
      return { ...msg, segments };
    }
    case "error":
      return { ...msg, error: p.message };
    default:
      return msg;
  }
}

export default function App() {
  const [sessionId, setSessionId] = useState("");
  const [ready, setReady] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [profile, setProfile] = useState<ProfileCard | null>(null);
  const [outline, setOutline] = useState<OutlineNode[]>([]);
  const [deliverables, setDeliverables] = useState<Deliverables | null>(null);
  const [showDeliverables, setShowDeliverables] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [regenError, setRegenError] = useState("");
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [tourSignal, setTourSignal] = useState(0);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const convRef = useRef<HTMLDivElement>(null);
  const activeIdRef = useRef("");
  const pollRef = useRef<number | null>(null);
  const sessionIdRef = useRef("");
  // 轮询回调里读不到最新 state，镜像一份
  const messagesRef = useRef<ChatMessage[]>([]);

  const stopFollow = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const loadSessions = useCallback(async () => {
    setSessions(await listSessions().catch(() => []));
  }, []);

  /** 轮询跟随：Agent 在跑（running=true）时每 2s 拉状态，直到新 assistant 消息落库或进程结束 */
  const startFollow = useCallback(() => {
    stopFollow();
    pollRef.current = window.setInterval(async () => {
      const st = await getState(sessionIdRef.current).catch(() => null);
      if (!st) return;
      setProfile(st.profile);
      setOutline(st.outline || []);
      if (st.deliverables) setDeliverables(st.deliverables);
      const stored = (st.messages || []) as StoredMessage[];
      const assistantCount = stored.filter((m) => m.role === "assistant").length;
      const prevAssistant = messagesRef.current.filter(
        (m) => m.role === "assistant" && !m.id.startsWith("streaming-")
      ).length;
      // 新消息落库，或 Agent 已结束（含后端重启的僵死恢复）：整体替换为完整历史
      if (assistantCount <= prevAssistant && st.running) return;
      stopFollow();
      setBusy(false);
      loadSessions();
      setMessages(
        stored.map((m, i) => ({ id: `hist-${i}`, role: m.role, segments: storedToSegments(m) }))
      );
    }, 2000);
  }, [stopFollow, loadSessions]);

  /** 打开指定会话：拉取状态并填充各面板；Agent 还在跑则挂占位消息并轮询跟随 */
  const openSession = useCallback(
    async (sid: string, st?: Awaited<ReturnType<typeof getState>>) => {
      stopFollow();
      setBusy(false);
      setShowDeliverables(false);
      sessionStorage.setItem("grill.session-id", sid);
      sessionIdRef.current = sid;
      setSessionId(sid);
      const state = st ?? (await getState(sid).catch(() => null));
      setProfile(state?.profile ?? null);
      setOutline(state?.outline || []);
      setDeliverables(state?.deliverables || null);
      const msgs = ((state?.messages || []) as StoredMessage[]).map((m, i) => ({
        id: `hist-${i}`,
        role: m.role,
        segments: storedToSegments(m),
      }));
      if (state?.running) {
        // 刷新撞上 Agent 在跑：补占位 assistant 消息（思考动画），跑完整体替换
        const tempId = `streaming-${Date.now()}`;
        activeIdRef.current = tempId;
        msgs.push({ id: tempId, role: "assistant", segments: [] });
        setMessages(msgs);
        setBusy(true);
        startFollow();
      } else {
        setMessages(msgs);
      }
      setReady(true);
    },
    [stopFollow, startFollow]
  );

  // 会话恢复：?session= 优先，其次 sessionStorage，都没有才新建
  useEffect(() => {
    (async () => {
      loadSessions();
      const cached =
        new URLSearchParams(window.location.search).get("session") ||
        sessionStorage.getItem("grill.session-id");
      const cachedState = cached ? await getState(cached).catch(() => null) : null;
      if (cachedState) {
        await openSession(cached as string, cachedState);
      } else {
        await openSession(await createSession());
        loadSessions();
      }
    })();
    return stopFollow;
  }, [stopFollow, openSession, loadSessions]);

  useEffect(() => {
    convRef.current?.scrollTo(0, convRef.current.scrollHeight);
  }, [messages]);

  const updateActive = (e: SseEvent) => {
    const id = activeIdRef.current;
    setMessages((prev) => prev.map((m) => (m.id === id ? applyEvent(m, e) : m)));
  };

  const send = async (text: string) => {
    if (busy || !sessionId) return;
    setBusy(true);
    const tempId = `streaming-${Date.now()}`;
    activeIdRef.current = tempId;
    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: "user", segments: [{ type: "text", text }] },
      { id: tempId, role: "assistant", segments: [] },
    ]);
    try {
      const resp = await chatStream(sessionId, text);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      for await (const event of parseSSE(resp)) {
        const e = event as unknown as SseEvent;
        if (e.type === "profile_update") {
          setProfile(e.payload.profile as ProfileCard);
        } else if (e.type === "outline_update") {
          setOutline(e.payload.outline as OutlineNode[]);
        } else if (e.type === "deliverables") {
          // 不自动弹窗：Agent 正文告知，用户从画像卡/工具栏按钮打开
          setDeliverables(e.payload as unknown as Deliverables);
        } else {
          updateActive(e);
        }
      }
    } catch (err) {
      updateActive({
        type: "error",
        payload: { message: err instanceof Error ? err.message : "请求失败" },
      });
      startFollow();
      return;
    }
    setBusy(false);
    loadSessions();
  };

  /** 侧栏：切换/新建会话 */
  const selectSession = (sid: string) => {
    if (busy || sid === sessionId) return;
    openSession(sid);
  };

  const newChat = async () => {
    if (busy) return;
    await openSession(await createSession());
    loadSessions();
  };

  /** 重新开始演示：新建会话 + 重放使用引导（旧会话留在侧栏历史中） */
  const handleRestart = async () => {
    setConfirmRestart(false);
    if (busy) return;
    await newChat();
    resetOnboarding();
    setTourSignal((n) => n + 1);
  };

  /** 删除会话（单个/批量统一走批量端点）；删掉当前会话则切到最新或新建 */
  const handleDelete = async (ids: string[]) => {
    if (busy) return;
    await deleteSessions(ids).catch(() => {});
    const list = await listSessions().catch(() => []);
    setSessions(list);
    if (!ids.includes(sessionIdRef.current)) return;
    if (list.length) {
      await openSession(list[0].session_id);
    } else {
      await openSession(await createSession());
      loadSessions();
    }
  };

  const converged = profile?.converged ?? false;

  /** 重新生成需求包：同步等待，成功后直接打开面板；失败保留旧内容 */
  const handleRegen = async () => {
    if (regenerating || !deliverables) return;
    setRegenerating(true);
    setRegenError("");
    try {
      setDeliverables(await regenerateDeliverables(sessionId));
      setShowDeliverables(true);
    } catch (err) {
      setRegenError(err instanceof Error ? err.message : "生成失败");
      window.setTimeout(() => setRegenError(""), 5000);
    } finally {
      setRegenerating(false);
    }
  };

  return (
    <div className="flex flex-col h-screen px-6 pb-3">
      <PageToolbar
        title="画像澄清 Agent"
        subtitle="面向用人部门 leader · 把模糊画像逼问清楚"
        right={
          <div className="flex items-center gap-2">
            {regenError && <span className="text-label text-error">{regenError}</span>}
            <Button
              variant="outlined"
              icon="replay"
              disabled={busy}
              title="开启全新会话并重放使用引导"
              onClick={() => setConfirmRestart(true)}
            >
              重新开始演示
            </Button>
            <Button
              variant="tonal"
              icon="refresh"
              disabled={!deliverables || regenerating}
              title={deliverables ? "基于当前画像与对话重新生成" : "需求包生成后可重新生成"}
              onClick={handleRegen}
            >
              {regenerating ? "生成中…" : "重新生成需求包"}
            </Button>
          </div>
        }
      />

      <div className="flex gap-6 flex-1 min-h-0">
        {/* 侧栏：历史会话 */}
        <SessionSidebar
          sessions={sessions}
          currentId={sessionId}
          busy={busy}
          onSelect={selectSession}
          onCreate={newChat}
          onDelete={handleDelete}
        />

        {/* 左栏：对话流 */}
        <div data-tour="chat-flow" className="flex-1 min-w-[480px] flex flex-col">
          <div ref={convRef} className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-5 pr-1 pb-2">
            {!ready ? (
              <div className="flex-1 flex items-center justify-center">
                <LoadingIndicator size={28} label="初始化会话…" />
              </div>
            ) : messages.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center gap-3">
                <Icon name="psychology" size={40} className="text-on-surface-variant" />
                <p className="text-title">说说你想招什么样的人？</p>
                <p className="text-body-sm text-on-surface-variant">
                  Agent 会像资深 HR 一样追问，右侧大纲与画像卡实时填充
                </p>
                <div className="flex flex-wrap justify-center gap-2">
                  {["我们想招个后端，抖音电商方向的。", "招一个 AI 产品经理实习生，base 北京。"].map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => send(t)}
                      className="state-layer rounded-full border border-primary/50 bg-surface-lowest px-3 py-1.5 text-body-sm text-primary cursor-pointer hover:bg-primary-container"
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg, idx) => {
                if (msg.role === "user") {
                  return (
                    <div
                      key={msg.id}
                      className="chat-enter self-end max-w-[80%] px-4 py-3 rounded-lg bg-primary-container text-on-primary-container text-body whitespace-pre-wrap"
                    >
                      {msg.segments.map((s) => (s.type === "text" ? s.text : "")).join("")}
                    </div>
                  );
                }
                // 该 assistant 消息之后的下一条用户消息：历史回放时供卡片反推已选项
                const nextUser = messages.slice(idx + 1).find((m) => m.role === "user");
                const userReply = nextUser?.segments
                  .map((s) => (s.type === "text" ? s.text : ""))
                  .join("");
                return (
                  <AssistantMessage
                    key={msg.id}
                    message={msg}
                    busy={busy && msg.id === activeIdRef.current}
                    interactive={idx === messages.length - 1 && !busy}
                    onSend={send}
                    userReply={userReply}
                  />
                );
              })
            )}
          </div>
          <ChatInput busy={busy} onSend={send} />
        </div>

        {/* 中栏：提问大纲 */}
        <div data-tour="outline" className="w-[300px] shrink-0 min-h-0">
          <OutlinePanel outline={outline} />
        </div>

        {/* 右栏：画像卡 */}
        <div data-tour="profile" className="w-[360px] shrink-0 min-h-0">
          <ProfileCardPanel
            profile={profile}
            hasDeliverables={!!deliverables}
            busy={busy}
            onConfirm={() => send("画像总结确认无误，请生成需求包。")}
            onOpenDeliverables={() => setShowDeliverables(true)}
          />
        </div>
      </div>

      {showDeliverables && deliverables && (
        <DeliverablesPanel deliverables={deliverables} onClose={() => setShowDeliverables(false)} />
      )}

      {confirmRestart && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 p-6"
          onClick={() => setConfirmRestart(false)}
        >
          <Card
            variant="elevated"
            className="w-full max-w-sm rounded-xl p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-title-lg">重新开始演示？</h3>
            <p className="mt-2 text-body-sm text-on-surface-variant">
              将开启全新会话并重新播放使用引导。当前会话会保留在左侧历史列表中。
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="text" onClick={() => setConfirmRestart(false)}>
                取消
              </Button>
              <Button variant="filled" icon="replay" onClick={handleRestart}>
                重新开始
              </Button>
            </div>
          </Card>
        </div>
      )}

      <OnboardingTour restartSignal={tourSignal} />
    </div>
  );
}

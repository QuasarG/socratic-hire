import { useState, useEffect, useRef, useCallback } from "react";

const STORAGE_KEY = "grill.onboarding.v1";

/** 引导步骤：selector 定位高亮元素，title/desc 展示文案 */
interface TourStep {
  selector: string;
  title: string;
  desc: string;
  placement?: "right" | "bottom" | "top" | "left";
}

const STEPS: TourStep[] = [
  {
    selector: '[data-tour="chat-flow"]',
    title: "① 一句话描述要招的人",
    desc: "在对话区用一句话开场，比如「我们想招个后端，抖音电商方向的」。Agent 会像资深 HR 一样持续追问，把模糊画像逼问清楚。",
    placement: "right",
  },
  {
    selector: "[data-chat-input]",
    title: "② 点选项回答追问",
    desc: "Agent 的追问以选项卡形式弹出，点选项即答；也可以在下方输入框自由回答，说抽象词会被追问具体证据。",
    placement: "top",
  },
  {
    selector: '[data-tour="outline"]',
    title: "中栏 · 提问大纲",
    desc: "澄清进度实时可见：哪些维度已覆盖、正在问什么、还有哪些待追问，一目了然。",
    placement: "left",
  },
  {
    selector: '[data-tour="profile"]',
    title: "右栏 · 画像卡",
    desc: "每轮回答都会实时沉淀成简历式画像卡。收敛后确认画像，即可生成需求包（JD 草稿 / 筛选标准 / 参考岗位）。",
    placement: "left",
  },
  {
    selector: "",
    title: "开始使用",
    desc: "空态页的示例开场白点击即可发送。右上角「重新开始演示」可以随时开启全新会话并重看本引导。祝演示顺利～",
    placement: "top",
  },
];

export function resetOnboarding(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

interface Props {
  /** 递增即重播引导（重新开始演示时 bump） */
  restartSignal: number;
}

/** 首次进入的高亮引导：聚光灯镂空 + 气泡步骤条，看完写 localStorage */
export default function OnboardingTour({ restartSignal }: Props) {
  const [active, setActive] = useState(false);
  const [step, setStep] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [bubbleVisible, setBubbleVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const finish = useCallback(() => {
    setActive(false);
    setStep(0);
    setBubbleVisible(false);
    try {
      localStorage.setItem(STORAGE_KEY, "done");
    } catch {
      /* ignore */
    }
  }, []);

  // 首次访问自动启动
  useEffect(() => {
    let seen = false;
    try {
      seen = localStorage.getItem(STORAGE_KEY) === "done";
    } catch {
      /* ignore */
    }
    if (!seen) timerRef.current = setTimeout(() => setActive(true), 600);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  // 重播信号：从头开始
  useEffect(() => {
    if (restartSignal > 0) {
      setStep(0);
      setActive(true);
    }
  }, [restartSignal]);

  // 步骤变化：先藏气泡 → 延迟定位高亮框 → 气泡淡入
  useEffect(() => {
    if (!active) return;
    const s = STEPS[step];
    setBubbleVisible(false);
    timerRef.current = setTimeout(() => {
      const el = s.selector ? document.querySelector(s.selector) : null;
      setRect(el ? el.getBoundingClientRect() : null);
      timerRef.current = setTimeout(() => setBubbleVisible(true), 350);
    }, 300);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [step, active]);

  // 窗口大小变化时重新定位
  useEffect(() => {
    if (!active) return;
    const handler = () => {
      const s = STEPS[step];
      const el = s.selector ? document.querySelector(s.selector) : null;
      if (el) setRect(el.getBoundingClientRect());
    };
    window.addEventListener("resize", handler);
    return () => window.removeEventListener("resize", handler);
  }, [step, active]);

  if (!active) return null;

  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;
  const hasTarget = rect !== null;

  // 气泡定位
  const bubbleStyle: React.CSSProperties = {};
  if (hasTarget && rect) {
    const placement = current.placement || "right";
    const spacing = 16;
    switch (placement) {
      case "right":
        bubbleStyle.left = rect.right + spacing;
        bubbleStyle.top = Math.max(16, Math.min(rect.top, window.innerHeight - 280));
        break;
      case "left":
        bubbleStyle.right = window.innerWidth - rect.left + spacing;
        bubbleStyle.top = Math.max(16, Math.min(rect.top, window.innerHeight - 280));
        break;
      case "bottom":
        bubbleStyle.left = Math.max(16, Math.min(rect.left, window.innerWidth - 380));
        bubbleStyle.top = rect.bottom + spacing;
        break;
      case "top":
        bubbleStyle.left = Math.max(16, Math.min(rect.left, window.innerWidth - 380));
        bubbleStyle.bottom = window.innerHeight - rect.top + spacing;
        break;
    }
  } else {
    // 无高亮目标（结束步骤）：居中
    bubbleStyle.left = "50%";
    bubbleStyle.top = "50%";
    bubbleStyle.transform = "translate(-50%, -50%)";
  }

  return (
    <>
      {/* 遮罩：有高亮时 box-shadow 镂空，无高亮时纯半透明 */}
      {hasTarget && rect ? (
        <div
          className="fixed z-[300] pointer-events-none"
          style={{
            left: rect.left - 4,
            top: rect.top - 4,
            width: rect.width + 8,
            height: rect.height + 8,
            borderRadius: 12,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.55)",
            border: "2px solid var(--color-primary)",
            transition: "all 350ms cubic-bezier(0.4, 0, 0.2, 1)",
          }}
        />
      ) : (
        <div className="fixed inset-0 z-[300] bg-black/55 transition-opacity duration-300" />
      )}

      {/* 解释气泡：高亮框到位后才淡入 */}
      <div
        className="fixed z-[301] w-[340px] bg-surface rounded-lg shadow-2xl p-5 flex flex-col gap-3 transition-all duration-300"
        style={{
          ...bubbleStyle,
          opacity: bubbleVisible ? 1 : 0,
          transform: bubbleVisible
            ? hasTarget
              ? "translateY(0)"
              : "translate(-50%, -50%)"
            : hasTarget
              ? "translateY(8px)"
              : "translate(-50%, calc(-50% + 8px))",
        }}
      >
        <div className="flex items-center gap-2">
          <span className="text-title font-bold text-on-surface">{current.title}</span>
          <span className="ml-auto text-label text-on-surface-variant">
            {step + 1} / {STEPS.length}
          </span>
        </div>
        <p className="text-body-sm text-on-surface-variant leading-relaxed">{current.desc}</p>
        <div className="flex items-center gap-2 mt-1">
          {step > 0 && (
            <button
              onClick={() => setStep((s) => s - 1)}
              className="state-layer px-3 py-1.5 rounded-full text-body-sm text-on-surface-variant hover:bg-surface-low cursor-pointer"
            >
              上一步
            </button>
          )}
          <button
            onClick={finish}
            className="state-layer ml-auto px-3 py-1.5 rounded-full text-body-sm text-on-surface-variant hover:bg-surface-low cursor-pointer"
          >
            跳过
          </button>
          <button
            onClick={() => (isLast ? finish() : setStep((s) => s + 1))}
            className="state-layer px-4 py-1.5 rounded-full text-body-sm font-semibold bg-primary text-on-primary hover:opacity-90 cursor-pointer"
          >
            {isLast ? "完成" : "下一步"}
          </button>
        </div>
      </div>
    </>
  );
}

/* ================================================================
   Dev Preview — 卡片实时编辑器
   左侧属性面板 + 右侧卡片实时预览
   两种模式: 数据编辑 / 样式编辑 (点击元素直接改 CSS)
   访问 http://localhost:3002
   ================================================================ */

import React, { useState, useCallback, useMemo, useRef, useEffect } from "react";
import { Player, PlayerRef } from "@remotion/player";
import { CoverCard } from "./CoverCard";
import { EventCard } from "./EventCard";
import { AtmosphereCard } from "./AtmosphereCard";
import { ClosingCard } from "./ClosingCard";
import { ChapterProvider } from "./design";
import { PropEditor } from "./PropEditor";
import {
  StyleInspector,
  StyleEditorPanel,
  type ElementInfo,
} from "./StyleInspector";

// ---- 默认示例数据 ----
const DEFAULTS: Record<string, Record<string, unknown>> = {
  cover: {
    headline: "HN TechPulse",
    subtitle: "2026年5月30日",
    section_counts: { focus: 3 },
    highlight_entries: [
      { score: 489, comment_count: 127, editor_angle: "AI 模型新进展", original_title: "GPT-5 Released" },
      { score: 234, comment_count: 56, editor_angle: "开源社区动态", original_title: "Rust 2.0 Preview" },
    ],
  },
  event: {
    display_index: 0,
    story_count: 5,
    source_domain: "github.com",
    editor_angle: "GitHub 发布 AI 结对编程功能",
    source_title: "GitHub Launches AI Pair Programming",
    heat_level: "L2",
    score: 342,
    comment_count: 89,
    key_points: [
      { label: "为何关注", text: "这是开发者工作流的重大变革" },
      { label: "影响分析", text: "可能改变代码审查和 PR 流程" },
    ],
    keywords: ["AI", "GitHub", "编程助手"],
    image_src: "/favicon.svg",
    image_type: "logo",
  },
  atmosphere: {
    controversy_score: 6,
    debate_focus: ["AI 是否会取代程序员", "代码所有权归属", "安全风险"],
    stance_distribution: { support: 45, skeptic: 32, neutral: 15, tease: 5, worry: 3 },
    comment_count: 127,
    quotes: [
      { display_text: "这将彻底改变我们写代码的方式", text: "这将彻底改变我们写代码的方式", author: "dev_lead_42", upvotes: 89, likes: 89, stance: "support" },
      { display_text: "听起来很美好，但实际效果还需要验证", text: "听起来很美好，但实际效果还需要验证", author: "skeptic_dev", upvotes: 56, likes: 56, stance: "skeptic" },
    ],
  },
  closing: {
    signal_label: "今日信号",
    signal: "AI 编程工具正在从辅助走向主导",
    question: "AI 编程工具正在从辅助走向主导",
    keywords: ["AI", "Copilot", "自动化", "效率", "未来"],
    summary_items: [
      { category: "AI", title: "GitHub AI 编程" },
      { category: "开源", title: "Rust 2.0 发布" },
      { category: "产品", title: "Notion AI 更新" },
    ],
    totals: { story_count: 5, score_total: 1247, comment_total: 342 },
    visual_mood: "积极",
  },
};

// ---- 卡片类型映射 ----
type CardKey = "cover" | "event" | "atmosphere" | "closing";

const CARD_META: Record<CardKey, {
  label: string;
  Component: React.FC<{ elementProps: Record<string, unknown>; width: number; height: number; duration: number }>;
  chapter: "cover" | "focus" | "atmosphere" | "closing";
}> = {
  cover:      { label: "封面卡 (Cover)",        Component: CoverCard,      chapter: "cover" },
  event:      { label: "事件卡 (Event)",        Component: EventCard,      chapter: "focus" },
  atmosphere: { label: "氛围卡 (Atmosphere)",   Component: AtmosphereCard, chapter: "atmosphere" },
  closing:    { label: "结束卡 (Closing)",      Component: ClosingCard,    chapter: "closing" },
};

const TOTAL_FRAMES = 54;

// ---- 共享暗色主题 UI 常量 ----
const DARK = {
  bg: "#121926",
  panel: "#16213e",
  input: "#0f3460",
  border: "#1e3a5f",
  accent: "#e94560",
  text: "#e0e0e0",
  muted: "#8ea8c3",
  dim: "#4a6078",
};

// ---- 卡片渲染 ----
interface CardPlayerProps {
  cardKey: CardKey;
  data: Record<string, unknown>;
  containerRef: React.RefObject<HTMLDivElement | null>;
}

function CardPlayer({ cardKey, data, containerRef }: CardPlayerProps) {
  const meta = CARD_META[cardKey];
  const playerRef = useRef<PlayerRef>(null);
  const [paused, setPaused] = useState(false);

  const togglePlay = () => {
    const p = playerRef.current;
    if (!p) return;
    if (paused) {
      p.play();
      setPaused(false);
    } else {
      p.pause();
      setPaused(true);
    }
  };

  const CardComponent = useMemo(() => {
    // eslint-disable-next-line react/display-name
    return React.memo((playerProps: Record<string, unknown>) => {
      const width = (playerProps.width as number) ?? 1920;
      const height = (playerProps.height as number) ?? 1080;
      return (
        <ChapterProvider chapter={meta.chapter}>
          <meta.Component elementProps={data} width={width} height={height} duration={10} />
        </ChapterProvider>
      );
    });
  }, [cardKey, data]);

  return (
    <div ref={(el) => { (containerRef as React.MutableRefObject<HTMLDivElement | null>).current = el; }} style={{ position: "relative", width: "100%" }}>
      <Player
        ref={playerRef}
        component={CardComponent}
        durationInFrames={TOTAL_FRAMES}
        fps={24}
        compositionWidth={1920}
        compositionHeight={1080}
        style={{ width: "100%", display: "block" }}
        controls={false}
        autoPlay
        loop
        acknowledgeRemotionLicense
      />
      {/* 悬浮暂停按钮 */}
      <button
        onClick={togglePlay}
        title={paused ? "播放" : "暂停"}
        style={{
          position: "absolute",
          bottom: 10,
          right: 10,
          width: 32,
          height: 32,
          borderRadius: "50%",
          border: "none",
          background: "rgba(0,0,0,0.55)",
          color: "#fff",
          fontSize: 16,
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 10,
          lineHeight: 1,
        }}
      >
        {paused ? "▶" : "⏸"}
      </button>
    </div>
  );
}

type EditMode = "data" | "style";

// ---- 主组件 ----
export const DevPreview: React.FC = () => {
  const [cardType, setCardType] = useState<CardKey>("event");
  const [scale, setScale] = useState<number>(0.45);
  const [editMode, setEditMode] = useState<EditMode>("data");

  // 每个卡片类型维护独立的编辑数据状态
  const [editedData, setEditedData] = useState<Record<string, Record<string, unknown>>>(DEFAULTS);

  // 样式覆盖状态: selector → { prop: value }
  const [styleOverrides, setStyleOverrides] = useState<Record<string, Record<string, string>>>({});
  const [selectedElement, setSelectedElement] = useState<ElementInfo | null>(null);

  // 卡片容器 ref (用于 StyleInspector)
  const cardContainerRef = useRef<HTMLDivElement | null>(null);

  const currentData = editedData[cardType] ?? DEFAULTS[cardType];
  const meta = CARD_META[cardType];

  const handleDataChange = useCallback(
    (newData: Record<string, unknown>) => {
      setEditedData((prev) => ({ ...prev, [cardType]: newData }));
    },
    [cardType],
  );

  const handleReset = useCallback(() => {
    setEditedData((prev) => ({ ...prev, [cardType]: { ...DEFAULTS[cardType] } }));
  }, [cardType]);

  // 样式更新
  const handleUpdateStyleProp = useCallback(
    (selector: string, prop: string, value: string) => {
      setStyleOverrides((prev) => {
        const next = { ...prev };
        if (!next[selector]) next[selector] = {};
        if (value === "" || value === null) {
          const cleaned = { ...next[selector] };
          delete cleaned[prop];
          if (Object.keys(cleaned).length === 0) {
            delete next[selector];
          } else {
            next[selector] = cleaned;
          }
        } else {
          next[selector] = { ...next[selector], [prop]: value };
        }
        return next;
      });
      // 同时更新 selectedElement (使用函数式更新避免闭包陈旧)
      setSelectedElement((prev) => {
        if (!prev || prev.selector !== selector) return prev;
        const existing = { ...prev.overrides };
        if (value === "" || value === null) {
          delete existing[prop];
        } else {
          existing[prop] = value;
        }
        return { ...prev, overrides: existing };
      });
    },
    [],
  );

  const handleClearElementStyle = useCallback((selector: string) => {
    setStyleOverrides((prev) => {
      const next = { ...prev };
      delete next[selector];
      return next;
    });
    setSelectedElement((prev) => (prev?.selector === selector ? { ...prev, overrides: {} } : prev));
  }, []);

  const handleSelectElement = useCallback((info: ElementInfo | null) => {
    setSelectedElement(info);
  }, []);

  // 切换卡片时清除样式选择
  const handleCardTypeChange = useCallback(
    (key: CardKey) => {
      setCardType(key);
      setSelectedElement(null);
    },
    [],
  );

  // ---- 保存 & 加载样式补丁 ----
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");

  // 启动时从磁盘加载
  useEffect(() => {
    fetch("/api/style-patches")
      .then((r) => r.json())
      .then((data) => {
        if (data && Object.keys(data).length > 0) {
          setStyleOverrides(data as Record<string, Record<string, string>>);
        }
      })
      .catch(() => {}); // 文件不存在则忽略
  }, []);

  const handleSave = useCallback(async () => {
    setSaveStatus("saving");
    try {
      const res = await fetch("/api/style-patches", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(styleOverrides, null, 2),
      });
      if (res.ok) {
        setSaveStatus("saved");
        setTimeout(() => setSaveStatus("idle"), 2000);
      } else {
        setSaveStatus("error");
      }
    } catch {
      setSaveStatus("error");
    }
  }, [styleOverrides]);

  return (
    <div
      style={{
        display: "flex",
        height: "100vh",
        background: DARK.bg,
        fontFamily: "system-ui, -apple-system, sans-serif",
        overflow: "hidden",
      }}
    >
      {/* ========== 左侧面板 ========== */}
      <div
        style={{
          width: 380,
          minWidth: 380,
          background: DARK.panel,
          borderRight: `1px solid ${DARK.border}`,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* 面板头部 */}
        <div style={{ padding: "14px 16px", borderBottom: `1px solid ${DARK.border}` }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: DARK.text, marginBottom: 10 }}>
            🎬 属性编辑器
          </div>

          {/* 编辑模式切换 */}
          <div
            style={{
              display: "flex",
              gap: 0,
              marginBottom: 8,
              borderRadius: 6,
              overflow: "hidden",
              border: `1px solid ${DARK.border}`,
            }}
          >
            <button
              onClick={() => { setEditMode("data"); setSelectedElement(null); }}
              style={{
                flex: 1,
                padding: "6px 0",
                border: "none",
                background: editMode === "data" ? DARK.accent : "transparent",
                color: editMode === "data" ? "#fff" : DARK.muted,
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
                transition: "background 0.15s",
              }}
            >
              📝 数据
            </button>
            <button
              onClick={() => setEditMode("style")}
              style={{
                flex: 1,
                padding: "6px 0",
                border: "none",
                background: editMode === "style" ? DARK.accent : "transparent",
                color: editMode === "style" ? "#fff" : DARK.muted,
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
                transition: "background 0.15s",
              }}
            >
              🎨 样式
            </button>
          </div>

          {/* 卡片选择 */}
          <select
            value={cardType}
            onChange={(e) => handleCardTypeChange(e.target.value as CardKey)}
            style={{
              width: "100%",
              padding: "7px 12px",
              borderRadius: 6,
              border: `1px solid ${DARK.border}`,
              background: DARK.input,
              color: DARK.text,
              fontSize: 13,
              cursor: "pointer",
              marginBottom: 8,
            }}
          >
            {(Object.keys(CARD_META) as CardKey[]).map((k) => (
              <option key={k} value={k}>
                {CARD_META[k].label}
              </option>
            ))}
          </select>

          {/* 操作按钮 */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <button
              onClick={handleReset}
              style={{
                padding: "5px 12px",
                borderRadius: 5,
                border: `1px solid ${DARK.border}`,
                background: "transparent",
                color: DARK.muted,
                fontSize: 12,
                cursor: "pointer",
              }}
            >
              ↺ 重置
            </button>
            <button
              onClick={handleSave}
              disabled={saveStatus === "saving"}
              title="保存到 style_patches.json"
              style={{
                padding: "5px 12px",
                borderRadius: 5,
                border: `1px solid ${saveStatus === "saved" ? "#00d4aa" : DARK.border}`,
                background: saveStatus === "saved" ? "rgba(0,212,170,0.15)" : "transparent",
                color: saveStatus === "saved" ? "#00d4aa" : saveStatus === "error" ? "#e94560" : DARK.muted,
                fontSize: 12,
                cursor: "pointer",
                fontWeight: 600,
              }}
            >
              {saveStatus === "saving" ? "⏳ 保存中..." : saveStatus === "saved" ? "✓ 已保存" : saveStatus === "error" ? "✕ 失败" : "💾 保存"}
            </button>
            {editMode === "data" ? (
              <span style={{ fontSize: 11, color: DARK.dim }}>
                {Object.keys(currentData).length} 字段
              </span>
            ) : (
              <span style={{ fontSize: 11, color: DARK.dim }}>
                {Object.keys(styleOverrides).length} 覆盖
              </span>
            )}
          </div>
        </div>

        {/* 可滚动属性列表 */}
        <div style={{ flex: 1, overflowY: "auto", padding: "12px 14px" }}>
          {editMode === "data" ? (
            <PropEditor data={currentData} onChange={handleDataChange} />
          ) : (
            <StyleEditorPanel
              element={selectedElement}
              overrides={styleOverrides}
              onUpdateProp={handleUpdateStyleProp}
              onClearElement={handleClearElementStyle}
            />
          )}
        </div>

        {/* 面板底部 — 缩放 */}
        <div style={{ padding: "10px 16px", borderTop: `1px solid ${DARK.border}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 11, color: DARK.muted }}>缩放</span>
            <input
              type="range"
              min={0.2}
              max={0.8}
              step={0.05}
              value={scale}
              onChange={(e) => setScale(Number(e.target.value))}
              style={{ flex: 1, accentColor: DARK.accent, height: 4 }}
            />
            <span style={{ fontSize: 12, color: DARK.accent, fontWeight: 600, width: 36, textAlign: "right" }}>
              {Math.round(scale * 100)}%
            </span>
          </div>
        </div>
      </div>

      {/* ========== 右侧卡片预览 ========== */}
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 20,
          overflow: "auto",
          background: `radial-gradient(ellipse at center, #1a2740 0%, ${DARK.bg} 70%)`,
        }}
      >
        <div
          style={{
            width: Math.round(1920 * scale),
            borderRadius: 8,
            overflow: "hidden",
            boxShadow: "0 16px 64px rgba(0,0,0,0.5)",
            transition: "width 0.15s",
            position: "relative",
          }}
        >
          <CardPlayer key={cardType} cardKey={cardType} data={currentData} containerRef={cardContainerRef} />

          {/* 样式检查器 overlay (在卡片上方) */}
          <StyleInspector
            containerRef={cardContainerRef}
            enabled={editMode === "style"}
            selectedElement={selectedElement}
            onSelectElement={handleSelectElement}
            overrides={styleOverrides}
            onOverridesChange={setStyleOverrides}
          />
        </div>
      </div>
    </div>
  );
};

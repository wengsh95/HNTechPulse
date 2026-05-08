/**
 * Elements.tsx —— 场景元素的 React 渲染组件
 *
 * Apple-inspired Clean Design System
 * - Minimal, clean aesthetic
 * - White backgrounds with subtle shadows
 * - Rounded corners
 * - System fonts (SF Pro-inspired)
 * - Plentiful whitespace
 * - Neutral grays with blue accents
 */
import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";

import { CueData } from "../types";

// ── 通用 Props 接口 ──────────────────────────────────
interface ElementProps {
  elementProps: Record<string, unknown>;
  duration: number;
  width: number;
  height: number;
}

// ── 通用工具函数 ─────────────────────────────────────

/** 安全地从 props 取值 */
function p<T = string>(props: Record<string, unknown>, key: string, fallback: T): T {
  const val = props[key];
  return (val as T) ?? fallback;
}

/** 截断文字 */
function truncate(text: string, maxLen: number): string {
  if (!text) return "";
  return text.length <= maxLen ? text : text.slice(0, maxLen - 3) + "...";
}

/** 去除 HTML 标签 */
function stripHtml(text: string): string {
  if (!text) return "";
  return text.replace(/<[^>]+>/g, "");
}

// ── Apple-inspired Design System ─────────────────────
const FONTS = {
  mono: '"SF Mono", "Monaco", "Courier New", monospace',
  sans: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif',
  bold: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif',
};

const COLORS = {
  bg: "#ffffff",
  text: "#1d1d1f",
  dim: "#86868b",
  accent: "#007aff",
  cardBg: "#ffffff",
  background: "#f5f5f7",
  border: "#e5e5ea",
  borderLight: "#f0f0f5",
  textLight: "#6e6e73",
};

const SHADOWS = {
  card: "0 1px 2px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.06), 0 8px 40px rgba(0,0,0,0.06)",
  cardHover: "0 2px 4px rgba(0,0,0,0.06), 0 8px 24px rgba(0,0,0,0.10), 0 16px 56px rgba(0,0,0,0.08)",
};

const S: React.CSSProperties = { position: "absolute" as const };

// ==================================================================
//  1. TitleCard —— 开场标题卡
// ==================================================================

export const TitleCard: React.FC<ElementProps> = ({ elementProps, width, height }) => (
  <div style={{ ...S, left: 0, top: 0, width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", backgroundColor: COLORS.background }}>
    <div style={{
      fontFamily: FONTS.bold,
      fontWeight: 700,
      fontSize: 76,
      color: COLORS.text,
      lineHeight: 1.1,
      letterSpacing: -1.5,
    }}>
      {p(elementProps, "title", "HN TechPulse")}
    </div>
    {p(elementProps, "subtitle", "") && (
      <div style={{
        fontFamily: FONTS.sans,
        fontSize: 30,
        color: COLORS.dim,
        marginTop: 24,
        fontWeight: 400,
        letterSpacing: 0.3,
      }}>
        {p(elementProps, "subtitle", "")}
      </div>
    )}
  </div>
);

// ==================================================================
//  2. Subtitle —— 底部字幕条（按 cues 逐句切换）
// ==================================================================

export const Subtitle: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cues = (elementProps.cues as CueData[]) ?? [];
  const fallbackText = truncate(stripHtml(p(elementProps, "text", "")), 120);

  const currentTime = frame / fps;

  let displayText = fallbackText;
  let opacity = 1;
  if (cues.length > 0) {
    // Find the cue whose time range contains currentTime (with small tolerance)
    let activeCue = cues.find(
      (c) => currentTime >= c.start_time - 0.05 && currentTime <= c.end_time + 0.05
    );
    if (!activeCue) {
      // Between cues: find the nearest cue by distance to its boundaries
      let minDist = Infinity;
      for (const c of cues) {
        const distToStart = Math.abs(currentTime - c.start_time);
        const distToEnd = Math.abs(currentTime - c.end_time);
        const dist = Math.min(distToStart, distToEnd);
        if (dist < minDist) {
          minDist = dist;
          activeCue = c;
        }
      }
    }
    if (activeCue) {
      displayText = activeCue.text;
    } else if (currentTime >= cues[cues.length - 1].end_time) {
      const fadeOutDuration = 0.5;
      const timeSinceEnd = currentTime - cues[cues.length - 1].end_time;
      if (timeSinceEnd < fadeOutDuration) {
        displayText = cues[cues.length - 1].text;
        opacity = 1 - timeSinceEnd / fadeOutDuration;
      } else {
        displayText = "";
        opacity = 0;
      }
    } else if (currentTime < cues[0].start_time) {
      displayText = cues[0].text;
    }
  }

  return (
    <div style={{
      ...S,
      left: "50%",
      bottom: 24,
      transform: "translateX(-50%)",
      backgroundColor: "rgba(0, 0, 0, 0.45)",
      backdropFilter: "blur(12px)",
      WebkitBackdropFilter: "blur(12px)",
      borderRadius: 20,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "10px 24px",
      width: "94%",
      opacity,
    }}>
      <span style={{
        fontFamily: FONTS.sans,
        fontSize: 26,
        color: "#ffffff",
        textAlign: "center",
        lineHeight: 1.4,
        fontWeight: 500,
        letterSpacing: 0.2,
      }}>
        {displayText}
      </span>
    </div>
  );
};

// ==================================================================
//  3. ClosingCard —— 结尾卡片
// ==================================================================

export const ClosingCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const question = p(elementProps, "question", "");
  const visualMood = p(elementProps, "visual_mood", "");

  return (
    <div style={{
      ...S,
      left: 0,
      top: 0,
      width: "100%",
      height: "100%",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: COLORS.background,
    }}>
      {question && (
        <div style={{
          fontFamily: FONTS.sans,
          fontSize: 36,
          color: COLORS.text,
          lineHeight: 1.4,
          textAlign: "center",
          maxWidth: "80%",
          fontWeight: 500,
        }}>
          {question}
        </div>
      )}
      {visualMood && (
        <div style={{
          fontFamily: FONTS.mono,
          fontSize: 24,
          color: COLORS.dim,
          marginTop: 24,
        }}>
          {visualMood}
        </div>
      )}
      <div style={{
        fontFamily: FONTS.bold,
        fontWeight: 700,
        fontSize: 52,
        color: COLORS.text,
        marginTop: 48,
        lineHeight: 1.2,
        letterSpacing: -1,
      }}>
        HN TechPulse
      </div>
    </div>
  );
};

// ==================================================================
//  4. DashboardCard —— Top10 热度仪表盘（列表形式）
// ==================================================================

export const DashboardCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const entries = (elementProps.entries as Array<{
    rank?: number;
    original_title?: string;
    title?: string;
    title_translation?: string;
    title_cn?: string;
    score?: number;
    comment_count?: number;
  }>) ?? [];

  const cardW = width - 160;
  const rowH = 58;
  const headerH = 60;
  const visibleRows = Math.min(entries.length, 10);
  const tableH = headerH + visibleRows * rowH + 20;
  const topY = Math.max(40, (height - tableH) / 2 - 20);

  return (
    <div style={{ ...S, left: 80, top: topY, width: cardW, background: "linear-gradient(180deg, #ffffff 0%, #fafafc 100%)", borderRadius: 20, padding: "32px 36px", boxShadow: SHADOWS.cardHover, border: `1px solid ${COLORS.border}` }}>
      <div style={{ fontFamily: FONTS.bold, fontWeight: 700, fontSize: 28, color: COLORS.text, marginBottom: 20, letterSpacing: -0.3 }}>
        🔥 今日热度 Top 10
      </div>

      <div style={{ display: "flex", alignItems: "center", fontFamily: FONTS.mono, fontSize: 18, color: COLORS.dim, borderBottom: `1px solid ${COLORS.borderLight}`, paddingBottom: 12, marginBottom: 8, fontWeight: 600 }}>
        <span style={{ width: 44 }}>#</span>
        <span style={{ flex: 1 }}>Title</span>
        <span style={{ width: 80, textAlign: "right" }}>▲</span>
        <span style={{ width: 80, textAlign: "right" }}>💬</span>
      </div>

      {entries.slice(0, 10).map((entry, i) => {
        const title = entry.original_title || entry.title || "";
        const titleCn = entry.title_translation || entry.title_cn || "";
        const rank = entry.rank || i + 1;
        const medalColors = ["#d4a853", "#b0b7c0", "#c4874a"];
        const rankColor = rank <= 3 ? medalColors[rank - 1] : COLORS.dim;
        const rankBg = rank <= 3 ? (medalColors[rank - 1] + "18") : "transparent";
        return (
          <div key={i} style={{
            display: "flex",
            alignItems: "center",
            fontFamily: FONTS.sans,
            fontSize: 18,
            color: COLORS.text,
            minHeight: rowH,
            borderBottom: i < entries.length - 1 ? `1px solid ${COLORS.borderLight}` : "none",
            padding: "8px 0",
            backgroundColor: i % 2 === 0 ? "rgba(0,0,0,0.015)" : "transparent",
          }}>
            <span style={{
              width: 44, fontFamily: FONTS.mono, color: rankColor, fontWeight: 700, fontSize: 20,
              ...(rank <= 3 ? { backgroundColor: rankBg, borderRadius: 10, padding: "2px 0", textAlign: "center" as const } : {}),
            }}>{rank}</span>
            <span style={{ flex: 1, paddingRight: 16, display: "flex", flexDirection: "column", gap: 4 }}>
              <span style={{ lineHeight: 1.3, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as const, fontWeight: 500 }}>{titleCn || title}</span>
              {titleCn && title && <span style={{ fontSize: 16, color: COLORS.dim, lineHeight: 1.3, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 1, WebkitBoxOrient: "vertical" as const }}>{title}</span>}
            </span>
            <span style={{ width: 80, textAlign: "right", fontFamily: FONTS.mono, fontSize: 18, color: COLORS.accent, flexShrink: 0, fontWeight: 600 }}>{entry.score || 0}</span>
            <span style={{ width: 80, textAlign: "right", fontFamily: FONTS.mono, fontSize: 18, color: COLORS.dim, flexShrink: 0 }}>{entry.comment_count || 0}</span>
          </div>
        );
      })}
    </div>
  );
};

// ==================================================================
//  StancePie —— 态度分布饼图（StoryScanCard 内部使用）
// ==================================================================

const STANCE_COLORS: Record<string, string> = {
  "支持": "#007aff",
  "质疑": "#ff3b30",
  "中立": "#8e8e93",
  "调侃": "#ff9500",
  "担忧": "#5856d6",
};

const StancePie: React.FC<{ distribution: Record<string, number>; size: number }> = ({ distribution, size }) => {
  const cx = size / 2;
  const cy = size / 2;
  const outerR = size / 2 - 4;
  const innerR = outerR * 0.58;
  const entries = Object.entries(distribution).filter(([, v]) => v > 0);

  let cumulative = 0;
  const arcs = entries.map(([label, value]) => {
    const startAngle = cumulative * 2 * Math.PI;
    cumulative += value;
    const endAngle = cumulative * 2 * Math.PI;
    const largeArc = value > 0.5 ? 1 : 0;

    const outerX1 = cx + outerR * Math.cos(startAngle - Math.PI / 2);
    const outerY1 = cy + outerR * Math.sin(startAngle - Math.PI / 2);
    const outerX2 = cx + outerR * Math.cos(endAngle - Math.PI / 2);
    const outerY2 = cy + outerR * Math.sin(endAngle - Math.PI / 2);
    const innerX1 = cx + innerR * Math.cos(startAngle - Math.PI / 2);
    const innerY1 = cy + innerR * Math.sin(startAngle - Math.PI / 2);
    const innerX2 = cx + innerR * Math.cos(endAngle - Math.PI / 2);
    const innerY2 = cy + innerR * Math.sin(endAngle - Math.PI / 2);

    const path = `M ${outerX1} ${outerY1} A ${outerR} ${outerR} 0 ${largeArc} 1 ${outerX2} ${outerY2} L ${innerX2} ${innerY2} A ${innerR} ${innerR} 0 ${largeArc} 0 ${innerX1} ${innerY1} Z`;
    const color = STANCE_COLORS[label] || COLORS.dim;
    return { label, value, path, color };
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {arcs.map((arc, i) => (
          <path key={i} d={arc.path} fill={arc.color} stroke="rgba(255,255,255,0.4)" strokeWidth={1.5} />
        ))}
      </svg>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 10px", marginTop: 8, justifyContent: "center" }}>
        {entries.map(([label, value]) => {
          const color = STANCE_COLORS[label] || COLORS.dim;
          return (
            <span key={label} style={{ fontFamily: FONTS.sans, fontSize: 13, color, display: "flex", alignItems: "center", gap: 4, fontWeight: 500 }}>
              <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 4, backgroundColor: color }} />
              {label} {Math.round(value * 100)}%
            </span>
          );
        })}
      </div>
    </div>
  );
};

// ==================================================================
//  5. StoryScanCard —— 逐条速览卡（事件 + 观点列表 + 饼图）
// ==================================================================

export const StoryScanCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const storyTitle = p(elementProps, "story_title", "");
  const titleCn = p(elementProps, "title_cn", "");
  const eventSummary = p(elementProps, "event_summary", "");
  const viewpoints = (elementProps.viewpoints as Array<{
    stance?: string;
    summary?: string;
    quote?: string;
  }>) ?? [];
  const stanceDistribution = elementProps.stance_distribution as Record<string, number> | undefined;

  const cardW = width - 160;
  const topY = 80;
  const hasPie = stanceDistribution && Object.keys(stanceDistribution).length > 0;
  const contentW = hasPie ? cardW - 200 : cardW;

  return (
    <div style={{ ...S, left: 80, top: topY, width: cardW, background: "linear-gradient(180deg, #ffffff 0%, #fafafc 100%)", borderRadius: 24, padding: "36px 40px", boxShadow: SHADOWS.cardHover, border: `1px solid ${COLORS.border}` }}>
      <div style={{ fontFamily: FONTS.bold, fontWeight: 700, fontSize: 32, color: COLORS.text, lineHeight: 1.2, wordBreak: "break-word", letterSpacing: -0.5 }}>
        {titleCn || storyTitle}
      </div>
      {titleCn && storyTitle && (
        <div style={{ fontFamily: FONTS.bold, fontSize: 32, color: COLORS.dim, marginTop: 10, lineHeight: 1.2, wordBreak: "break-word", letterSpacing: -0.5 }}>
          {storyTitle}
        </div>
      )}

      {eventSummary && (
        <div style={{ fontFamily: FONTS.sans, fontSize: 26, color: COLORS.textLight, marginTop: 20, lineHeight: 1.5, fontWeight: 500 }}>
          {eventSummary}
        </div>
      )}

      {viewpoints.length > 0 && (
        <>
          <div style={{ height: 1, backgroundColor: COLORS.borderLight, margin: "24px 0 20px" }} />
          <div style={{ display: "flex", gap: 32 }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: FONTS.bold, fontSize: 18, color: COLORS.dim, marginBottom: 16, fontWeight: 600, letterSpacing: 0.3 }}>社区观点</div>
              {viewpoints.map((vp, i) => {
                const stance = vp.stance || "";
                const summary = vp.summary || "";
                const quote = vp.quote || "";
                const stanceColor = STANCE_COLORS[stance] || COLORS.dim;
                return (
                  <div key={i} style={{ marginTop: i > 0 ? 16 : 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                      <span style={{
                        fontFamily: FONTS.sans,
                        fontSize: 14,
                        color: stanceColor,
                        backgroundColor: stanceColor + "18",
                        borderRadius: 14,
                        padding: "3px 14px",
                        whiteSpace: "nowrap",
                        fontWeight: 600,
                        letterSpacing: 0.2,
                      }}>
                        {stance}
                      </span>
                      <span style={{ fontFamily: FONTS.sans, fontSize: 20, color: COLORS.text, lineHeight: 1.4, fontWeight: 500 }}>
                        {summary}
                      </span>
                    </div>
                    {quote && (
                      <div style={{ fontFamily: FONTS.sans, fontSize: 20, color: COLORS.dim, marginTop: 8, marginLeft: 14, fontStyle: "italic", lineHeight: 1.4 }}>
                        "{quote}"
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {hasPie && <StancePie distribution={stanceDistribution!} size={170} />}
          </div>
        </>
      )}
    </div>
  );
};

// ==================================================================
//  6. ImageCard —— 文章配图卡片（带标题叠加）
// ==================================================================

export const ImageCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const imageSrc = p(elementProps, "image_src", "");
  const caption = p(elementProps, "caption", "");

  if (!imageSrc) return null;

  const pad = 80;
  const cardW = width - pad * 2;
  const cardH = Math.floor(height * 0.55);
  const topY = Math.floor(height * 0.15);

  return (
    <div style={{
      ...S, left: pad, top: topY, width: cardW, height: cardH,
      borderRadius: 24, overflow: "hidden",
      border: `1px solid ${COLORS.border}`,
      boxShadow: SHADOWS.card,
    }}>
      <img
        src={imageSrc}
        alt={caption}
        style={{
          width: "100%", height: "100%",
          objectFit: "cover" as const,
        }}
      />
      {caption && (
        <div style={{
          position: "absolute" as const, bottom: 0, left: 0, right: 0,
          background: "linear-gradient(to top, rgba(0,0,0,0.65) 0%, rgba(0,0,0,0.35) 60%, transparent 100%)",
          padding: "40px 28px 20px",
          fontFamily: FONTS.sans, fontSize: 24, color: "#ffffff",
          lineHeight: 1.4,
          fontWeight: 500,
        }}>
          {truncate(caption, 80)}
        </div>
      )}
    </div>
  );
};

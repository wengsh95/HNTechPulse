/**
 * Elements.tsx —— 所有场景元素的 React 渲染组件
 *
 * 每个组件接收统一 props 接口，与 Python 端 element_renderers 注册表中的同名方法对应。
 * Remotion 的优势：
 * - 文字渲染由浏览器原生完成（GPU 加速），不需要 Pillow/Pango
 * - 并行帧渲染（多 worker），不卡在单线程
 * - CSS Flexbox/Grid 布局远比手动计算坐标直观
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

// ── 共享样式常量 ─────────────────────────────────────
const FONTS = {
  mono: '"Courier New", Consolas, monospace',
  sans: 'Verdana, Geneva, sans-serif',
  bold: 'Verdana, Geneva, sans-serif',
};

const COLORS = {
  bg: "#f6f6ef",
  text: "#000000",
  dim: "#828282",
  info: "#3c7bb3",
  hnOrange: "#ff6600",
  comment: "#5a5a5a",
  warn: "#a03030",
  code: "#4a4a4a",
  perspA: "#3c7bb3",
  perspB: "#9b4dca",
  cardBg: "#ffffff",
};

const SEPARATOR = "#e0e0e0";

const S: React.CSSProperties = { position: "absolute" as const };

// ==================================================================
//  1. TitleCard —— 开场标题卡
// ==================================================================

export const TitleCard: React.FC<ElementProps> = ({ elementProps, width, height }) => (
  <div style={{ ...S, left: 0, top: 0, width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
    <div style={{ fontFamily: FONTS.mono, fontWeight: 700, fontSize: 80, color: COLORS.hnOrange, lineHeight: 1.2 }}>
      {p(elementProps, "title", "HN TechPulse")}
    </div>
    {p(elementProps, "subtitle", "") && (
      <div style={{ fontFamily: FONTS.mono, fontSize: 32, color: COLORS.dim, marginTop: 24 }}>
        {p(elementProps, "subtitle", "")}
      </div>
    )}
  </div>
);

// ==================================================================
//  2. StoryHeader —— 故事标题头（含 score/comments）
// ==================================================================

export const StoryHeader: React.FC<ElementProps> = ({ elementProps, width }) => (
  <div style={{ ...S, left: 80, top: 80, right: 80 }}>
    <div style={{
      fontFamily: FONTS.bold,
      fontWeight: 700,
      fontSize: 48,
      color: COLORS.text,
      lineHeight: 1.3,
      wordBreak: "break-word",
    }}>
      {truncate(p(elementProps, "story_title", ""), 70)}
    </div>
    <div style={{
      fontFamily: FONTS.mono,
      fontSize: 28,
      color: COLORS.hnOrange,
      marginTop: 16,
    }}>
      ▲ {p(elementProps, "score", 0)}   |   💬 {p(elementProps, "comments", 0)}
    </div>
    <div style={{ height: 1, backgroundColor: SEPARATOR, marginTop: 20 }} />
  </div>
);

// ==================================================================
//  3. Highlight —— 高亮关键词
// ==================================================================

export const Highlight: React.FC<ElementProps> = ({ elementProps, height }) => {
  const words = (elementProps.words as string[]) ?? [];
  const text = words.slice(0, 5).join("  ·  ");
  return (
    <div style={{
      ...S,
      left: 0,
      top: height / 2 - 100,
      width: "100%",
      textAlign: "center",
    }}>
      <span style={{ fontFamily: FONTS.bold, fontSize: 38, color: COLORS.info }}>
        {text}
      </span>
    </div>
  );
};

// ==================================================================
//  4. CommentBubble —— 评论气泡
// ==================================================================

export const CommentBubble: React.FC<ElementProps> = ({ elementProps, width }) => {
  const author = p(elementProps, "author", "");
  const originalText = p(elementProps, "original_text", "");
  const chineseSummary = p(elementProps, "chinese_summary", "");
  const text = truncate(stripHtml(chineseSummary || originalText), 150);

  const bgWidth = width - 200;

  return (
    <div style={{ ...S, left: 100, top: 420, width: bgWidth }}>
      {/* 背景 */}
      <div style={{ backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "20px 28px" }}>
        <div style={{ fontFamily: FONTS.mono, fontSize: 26, color: COLORS.comment }}>
          @{author}
        </div>
        <div style={{
          fontFamily: FONTS.sans,
          fontSize: 28,
          color: COLORS.text,
          marginTop: 12,
          lineHeight: 1.5,
        }}>
          {text}
        </div>
      </div>
    </div>
  );
};

// ==================================================================
//  5. Subtitle —— 底部字幕条（按 cues 逐句切换）
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
    // 更宽松的匹配：包含边界，且允许小范围重叠
    let activeCue = cues.find(
      (c) => currentTime >= c.start_time - 0.05 && currentTime <= c.end_time + 0.05
    );
    // 如果找不到，找最近一个已经开始但还没结束太久的
    if (!activeCue) {
      const startedCues = cues.filter((c) => currentTime >= c.start_time);
      if (startedCues.length > 0) {
        activeCue = startedCues[startedCues.length - 1];
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
      bottom: 25,
      transform: "translateX(-50%)",
      backgroundColor: COLORS.cardBg,
      borderRadius: 2,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "14px 40px",
      width: "90%",
      opacity,
    }}>
      <span style={{
        fontFamily: FONTS.sans,
        fontSize: 30,
        color: COLORS.text,
        textAlign: "center",
        lineHeight: 1.4,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}>
        {displayText}
      </span>
    </div>
  );
};

// ==================================================================
//  6. DiscussionOverview —— 讨论概览统计卡
// ==================================================================

export const DiscussionOverview: React.FC<ElementProps> = ({ elementProps }) => {
  const lines = [
    `Participants :  ${p(elementProps, "participant_count", 0)}`,
    `Max Depth     :  ${p(elementProps, "thread_depth_max", 0)} levels`,
    `Active Time   :  ${p(elementProps, "active_duration", "0h")}`,
  ];

  return (
    <div style={{ ...S, left: 80, top: 320, width: 400, height: 90, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "14px 24px" }}>
      {lines.map((line, i) => (
        <div key={i} style={{ fontFamily: FONTS.mono, fontSize: 20, color: COLORS.dim, lineHeight: 1.8 }}>
          {line}
        </div>
      ))}
    </div>
  );
};

// ==================================================================
//  7. CommentCard —— 单条评论卡片（双语）
// ==================================================================

export const CommentCard: React.FC<ElementProps> = ({ elementProps, width }) => {
  const margin = 80;
  const cardW = width - margin * 2;
  const author = p(elementProps, "author", "?");
  const score = p(elementProps, "score", 0);
  const text = truncate(stripHtml(p(elementProps, "text", "")), 180);
  const translation = p(elementProps, "translation", "") as string;
  const angleLabel = p(elementProps, "angle_label", "") as string;
  const transText = translation ? truncate(translation, 160) : "";

  return (
    <div style={{ ...S, left: margin, top: 430, width: cardW, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "18px 20px" }}>
      {/* 头部：@作者 + 分数 */}
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ fontFamily: FONTS.mono, fontSize: 24, color: COLORS.comment }}>
          @{author}   ▲ {score}
        </span>
        {angleLabel && (
          <span style={{ fontFamily: FONTS.sans, fontSize: 18, color: COLORS.info }}>
            [{angleLabel}]
          </span>
        )}
      </div>

      {/* 分隔线 */}
      <div style={{ height: 1, backgroundColor: SEPARATOR, margin: "8px 0" }} />

      {/* 英文原文 */}
      <div style={{ fontFamily: FONTS.mono, fontSize: 24, color: COLORS.code, lineHeight: 1.5, wordBreak: "break-word" }}>
        {text}
      </div>

      {/* 中文翻译 */}
      {transText && (
        <div style={{ fontFamily: FONTS.sans, fontSize: 22, color: COLORS.text, marginTop: 12, lineHeight: 1.4 }}>
          {transText}
        </div>
      )}
    </div>
  );
};

// ==================================================================
//  8. PerspectiveCompare —— 左右分屏视角对照
// ==================================================================

export const PerspectiveCompare: React.FC<ElementProps> = ({ elementProps, width }) => {
  const pad = 160;
  const halfW = Math.floor((width - pad) / 2);
  const cardH = 340;
  const leftX = 80;
  const rightX = 80 + halfW + 20;

  const pa = (elementProps.perspective_a ?? {}) as Record<string, unknown>;
  const pb = (elementProps.perspective_b ?? {}) as Record<string, unknown>;

  const renderPanel = (
    data: Record<string, unknown>,
    x: number,
    labelColor: string
  ) => {
    const label = p(data, "label", "");
    const text = truncate(stripHtml(p(data, "text", "")), 160);
    const translation = p(data, "translation", "") as string;

    return (
      <div key={x} style={{ ...S, left: x, top: 380, width: halfW, height: cardH, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "16px 20px" }}>
        <div style={{ fontFamily: FONTS.bold, fontSize: 28, color: labelColor }}>{label}</div>
        <div style={{ height: 1, backgroundColor: SEPARATOR, margin: "12px 0" }} />
        <div style={{ fontFamily: FONTS.mono, fontSize: 20, color: COLORS.code, lineHeight: 1.5, wordBreak: "break-word" }}>
          {text}
        </div>
        {translation && (
          <div style={{ fontFamily: FONTS.sans, fontSize: 19, color: COLORS.text, marginTop: 12, lineHeight: 1.4 }}>
            {truncate(translation, 140)}
          </div>
        )}
      </div>
    );
  };

  return (
    <>
      {renderPanel(pa, leftX, COLORS.perspA)}
      {renderPanel(pb, rightX, COLORS.perspB)}
      {/* 中间分隔线 */}
      <div style={{ ...S, left: leftX + halfW + 9, top: 380, width: 2, height: cardH, backgroundColor: SEPARATOR }} />
    </>
  );
};

// ==================================================================
//  9. SynthesisCard —— 洞察提炼要点列表
// ==================================================================

export const SynthesisCard: React.FC<ElementProps> = ({ elementProps, width }) => {
  const points = (elementProps.points as string[]) ?? [];
  const cardW = width - 160;
  const cardH = Math.min(points.length * 56 + 60, 280);

  return (
    <div style={{ ...S, left: 80, top: 400, width: cardW, height: cardH, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "18px 24px" }}>
      <div style={{ fontFamily: FONTS.bold, fontSize: 26, color: COLORS.info }}>Key Takeaways</div>
      {points.slice(0, 5).map((point, i) => (
        <div key={i} style={{
          fontFamily: FONTS.sans,
          fontSize: 22,
          color: COLORS.text,
          marginTop: i === 0 ? 16 : 12,
          lineHeight: 1.4,
          paddingLeft: 8,
        }}>
          ■  {truncate(point, 120)}
        </div>
      ))}
    </div>
  );
};

// ==================================================================
//  10. NewsCarouselCard —— 快速浏览全幅卡片
// ==================================================================

export const NewsCarouselCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const pad = 120;
  const cardW = width - pad * 2;
  const cardH = height - 280;
  const title = truncate(p(elementProps, "story_title", ""), 80);
  const score = p(elementProps, "score", 0);
  const commentCount = p(elementProps, "comment_count", 0);
  const author = p(elementProps, "author", "?");
  const cmtScore = p(elementProps, "comment_score", 0);
  const cmtText = truncate(stripHtml(p(elementProps, "comment_text", "")), 250);
  const cmtTrans = p(elementProps, "comment_translation", "") as string;

  return (
    <div style={{ ...S, left: pad, top: 140, width: cardW, height: cardH, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "24px 28px" }}>
      {/* 标题 */}
      <div style={{ fontFamily: FONTS.bold, fontWeight: 700, fontSize: 42, color: COLORS.text, lineHeight: 1.3 }}>
        {title}
      </div>

      {/* Meta 行 */}
      <div style={{ fontFamily: FONTS.mono, fontSize: 22, color: COLORS.hnOrange, marginTop: 16 }}>
        ▲ {score}   |   💬 {commentCount}
      </div>

      {/* 分隔线 */}
      <div style={{ height: 1, backgroundColor: SEPARATOR, margin: "16px 0" }} />

      {/* @作者 + 评论分数 */}
      <div style={{ fontFamily: FONTS.mono, fontSize: 20, color: COLORS.comment }}>
        @{author}   ▲ {cmtScore}
      </div>

      {/* 评论原文 */}
      <div style={{ fontFamily: FONTS.mono, fontSize: 21, color: COLORS.code, marginTop: 12, lineHeight: 1.5, wordBreak: "break-word" }}>
        {cmtText}
      </div>

      {/* 中文翻译 */}
      {cmtTrans && (
        <div style={{
          position: "absolute",
          bottom: 28,
          left: 28,
          right: 28,
          fontFamily: FONTS.sans,
          fontSize: 20,
          color: COLORS.dim,
          lineHeight: 1.4,
        }}>
          {truncate(cmtTrans, 220)}
        </div>
      )}
    </div>
  );
};

// ==================================================================
//  11. PatternInsight —— 今日洞察模式展示
// ==================================================================

export const PatternInsight: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const name = p(elementProps, "pattern_name", "");
  const description = truncate(p(elementProps, "description", ""), 300);
  const evidenceList = (elementProps.evidence as Array<Record<string, unknown> | string>) ?? [];
  const cardW = width - 280;
  const cardH = height - 240;

  // 兼容两种 evidence 格式
  const renderEvidence = (ev: Record<string, unknown> | string, i: number) => {
    const baseY = 212 + i * 72;
    if (typeof ev === "object" && ev !== null) {
      const source = p(ev, "source", "?") as string;
      const quote = truncate(p(ev, "quote", "") as string, 200);
      return (
        <React.Fragment key={i}>
          {source && (
            <div style={{ fontFamily: FONTS.mono, fontSize: 17, color: COLORS.comment, marginTop: 4 }}>
              {source}
            </div>
          )}
          <div style={{ fontFamily: FONTS.sans, fontSize: 19, color: COLORS.dim, lineHeight: 1.4, marginTop: source ? 4 : 0 }}>
            {source ? quote : `• ${quote}`}
          </div>
        </React.Fragment>
      );
    } else {
      // 纯字符串格式
      return (
        <div key={i} style={{ fontFamily: FONTS.sans, fontSize: 19, color: COLORS.dim, lineHeight: 1.4, marginTop: i > 0 ? 8 : 0 }}>
          • {truncate(String(ev), 200)}
        </div>
      );
    }
  };

  return (
    <div style={{ ...S, left: 140, top: 120, width: cardW, height: cardH, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "24px 28px" }}>
      {/* 模式名称 */}
      <div style={{ fontFamily: FONTS.bold, fontWeight: 700, fontSize: 38, color: COLORS.info, lineHeight: 1.3 }}>
        {name}
      </div>

      {/* 描述 */}
      <div style={{ fontFamily: FONTS.sans, fontSize: 24, color: COLORS.text, marginTop: 16, lineHeight: 1.5 }}>
        {description}
      </div>

      {/* Evidence 区域 */}
      {evidenceList.length > 0 && (
        <>
          <div style={{ height: 1, backgroundColor: SEPARATOR, margin: "20px 0 12px" }} />
          <div style={{ fontFamily: FONTS.bold, fontSize: 18, color: COLORS.dim }}>Evidence</div>
          <div style={{ marginTop: 8 }}>
            {evidenceList.slice(0, 3).map((ev, i) => renderEvidence(ev, i))}
          </div>
        </>
      )}
    </div>
  );
};

// ==================================================================
//  12. HookCard —— 开场钩子卡（headline + subtext）
// ==================================================================

export const HookCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const headline = p(elementProps, "headline", "");
  const subtext = p(elementProps, "subtext", "");

  return (
    <div style={{ ...S, left: 0, top: 0, width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
      <div style={{ fontFamily: FONTS.bold, fontWeight: 700, fontSize: 56, color: COLORS.hnOrange, lineHeight: 1.3, textAlign: "center", maxWidth: "80%" }}>
        {headline}
      </div>
      {subtext && (
        <div style={{ fontFamily: FONTS.mono, fontSize: 30, color: COLORS.dim, marginTop: 28, textAlign: "center" }}>
          {subtext}
        </div>
      )}
    </div>
  );
};

// ==================================================================
//  13. ConflictCard —— 左右冲突对照卡
// ==================================================================

export const ConflictCard: React.FC<ElementProps> = ({ elementProps, width }) => {
  const left = p(elementProps, "left", "");
  const right = p(elementProps, "right", "");
  const verdict = p(elementProps, "verdict", "");
  const pad = 160;
  const halfW = Math.floor((width - pad) / 2);
  const cardH = 280;
  const leftX = 80;
  const rightX = 80 + halfW + 20;

  return (
    <>
      <div style={{ ...S, left: leftX, top: 300, width: halfW, height: cardH, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "20px 24px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div style={{ fontFamily: FONTS.bold, fontSize: 20, color: COLORS.warn, marginBottom: 16 }}>CLAIM</div>
        <div style={{ fontFamily: FONTS.sans, fontSize: 26, color: COLORS.text, lineHeight: 1.4, wordBreak: "break-word" }}>
          {left}
        </div>
      </div>
      <div style={{ ...S, left: rightX, top: 300, width: halfW, height: cardH, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "20px 24px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div style={{ fontFamily: FONTS.bold, fontSize: 20, color: COLORS.info, marginBottom: 16 }}>REALITY</div>
        <div style={{ fontFamily: FONTS.sans, fontSize: 26, color: COLORS.text, lineHeight: 1.4, wordBreak: "break-word" }}>
          {right}
        </div>
      </div>
      <div style={{ ...S, left: leftX + halfW + 9, top: 300, width: 2, height: cardH, backgroundColor: SEPARATOR }} />
      {verdict && (
        <div style={{ ...S, left: 80, top: 300 + cardH + 20, width: width - 160, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "14px 24px", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ fontFamily: FONTS.bold, fontSize: 24, color: COLORS.code }}>⚡ {verdict}</span>
        </div>
      )}
    </>
  );
};

// ==================================================================
//  14. TurnCard —— 转折点信息卡
// ==================================================================

export const TurnCard: React.FC<ElementProps> = ({ elementProps, width }) => {
  const message = p(elementProps, "message", "");
  const cardW = width - 160;

  return (
    <div style={{ ...S, left: 80, top: 380, width: cardW, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "28px 32px", borderLeft: `4px solid ${COLORS.info}` }}>
      <div style={{ fontFamily: FONTS.bold, fontSize: 20, color: COLORS.info, marginBottom: 12 }}>TURNING POINT</div>
      <div style={{ fontFamily: FONTS.sans, fontSize: 28, color: COLORS.text, lineHeight: 1.5 }}>
        {message}
      </div>
    </div>
  );
};

// ==================================================================
//  15. ClosingCard —— 结尾卡片（问题 + 氛围）
// ==================================================================

export const ClosingCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const question = p(elementProps, "question", "");
  const visualMood = p(elementProps, "visual_mood", "");

  return (
    <div style={{ ...S, left: 0, top: 0, width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
      {question && (
        <div style={{ fontFamily: FONTS.sans, fontSize: 32, color: COLORS.text, lineHeight: 1.5, textAlign: "center", maxWidth: "80%" }}>
          {question}
        </div>
      )}
      {visualMood && (
        <div style={{ fontFamily: FONTS.mono, fontSize: 22, color: COLORS.dim, marginTop: 24 }}>
          {visualMood}
        </div>
      )}
      <div style={{ fontFamily: FONTS.mono, fontWeight: 700, fontSize: 48, color: COLORS.hnOrange, marginTop: 40, lineHeight: 1.2 }}>
        HN TechPulse
      </div>
    </div>
  );
};

// ==================================================================
//  16. DebateCard —— 每日辩题卡（正方 vs 反方 + 主播判断）
// ==================================================================

export const DebateCard: React.FC<ElementProps> = ({ elementProps, width }) => {
  const question = p(elementProps, "question", "");
  const sideA = p(elementProps, "side_a", "");
  const sideB = p(elementProps, "side_b", "");
  const yourTake = p(elementProps, "your_take", "");
  const commentA = (elementProps.comment_a ?? {}) as Record<string, unknown>;
  const commentB = (elementProps.comment_b ?? {}) as Record<string, unknown>;

  const cardW = width - 160;
  const halfW = (cardW - 20) / 2;
  const leftX = 80;
  const rightX = 80 + halfW + 20;

  return (
    <div style={{ ...S, left: 0, top: 0, width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
      {/* 辩题 */}
      {question && (
        <div style={{ fontFamily: FONTS.bold, fontSize: 34, color: COLORS.hnOrange, textAlign: "center", maxWidth: "85%", marginBottom: 32, lineHeight: 1.4 }}>
          {question}
        </div>
      )}

      {/* 左右阵营 */}
      <div style={{ display: "flex", width: cardW, gap: 20, marginBottom: 28 }}>
        <div style={{ flex: 1, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "18px 20px" }}>
          <div style={{ fontFamily: FONTS.bold, fontSize: 18, color: COLORS.perspA, marginBottom: 12 }}>正方</div>
          <div style={{ fontFamily: FONTS.sans, fontSize: 22, color: COLORS.text, lineHeight: 1.4 }}>
            {sideA}
          </div>
          {commentA && (commentA.author || commentA.text) && (
            <div style={{ fontFamily: FONTS.mono, fontSize: 16, color: COLORS.dim, marginTop: 12, lineHeight: 1.4 }}>
              @{p(commentA, "author", "?")}: {truncate(stripHtml(p(commentA, "text", "")), 80)}
            </div>
          )}
        </div>

        <div style={{ flex: 1, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "18px 20px" }}>
          <div style={{ fontFamily: FONTS.bold, fontSize: 18, color: COLORS.perspB, marginBottom: 12 }}>反方</div>
          <div style={{ fontFamily: FONTS.sans, fontSize: 22, color: COLORS.text, lineHeight: 1.4 }}>
            {sideB}
          </div>
          {commentB && (commentB.author || commentB.text) && (
            <div style={{ fontFamily: FONTS.mono, fontSize: 16, color: COLORS.dim, marginTop: 12, lineHeight: 1.4 }}>
              @{p(commentB, "author", "?")}: {truncate(stripHtml(p(commentB, "text", "")), 80)}
            </div>
          )}
        </div>
      </div>

      {/* 主播判断 */}
      {yourTake && (
        <div style={{ width: cardW, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "16px 24px", textAlign: "center", borderLeft: `4px solid ${COLORS.hnOrange}` }}>
          <span style={{ fontFamily: FONTS.bold, fontSize: 24, color: COLORS.code }}>
            {yourTake}
          </span>
        </div>
      )}
    </div>
  );
};

// ==================================================================
//  17. InfoTable —— 核心数据展示表
// ==================================================================

export const InfoTable: React.FC<ElementProps> = ({ elementProps, width }) => {
  const rows = (elementProps.rows as Array<{ label: string; value: string }>) ?? [];
  const cardW = width - 160;

  return (
    <div style={{ ...S, left: 80, top: 380, width: cardW, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "20px 28px" }}>
      {rows.map((row, i) => (
        <div key={i} style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: i > 0 ? "12px 0 0 0" : "0",
          borderTop: i > 0 ? `1px solid ${SEPARATOR}` : "none",
          marginTop: i > 0 ? 12 : 0,
        }}>
          <span style={{ fontFamily: FONTS.mono, fontSize: 20, color: COLORS.dim }}>{row.label}</span>
          <span style={{ fontFamily: FONTS.bold, fontSize: 22, color: COLORS.info }}>{row.value}</span>
        </div>
      ))}
    </div>
  );
};

// ==================================================================
//  12. OutroCard —— 结尾卡片（与 TitleCard 风格一致）
// ==================================================================

export const OutroCard: React.FC<ElementProps> = ({ elementProps, width, height }) => (
  <div style={{ ...S, left: 0, top: 0, width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
    <div style={{ fontFamily: FONTS.mono, fontWeight: 700, fontSize: 64, color: COLORS.hnOrange, lineHeight: 1.2 }}>
      {p(elementProps, "text", "HN TechPulse")}
    </div>
    {p(elementProps, "subtitle", "") && (
      <div style={{ fontFamily: FONTS.mono, fontSize: 28, color: COLORS.dim, marginTop: 20 }}>
        {p(elementProps, "subtitle", "")}
      </div>
    )}
  </div>
);

// ==================================================================
//  18. DashboardCard —— Top10 热度仪表盘（列表形式）
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
  const rowH = 54;
  const headerH = 60;
  const visibleRows = Math.min(entries.length, 10);
  const tableH = headerH + visibleRows * rowH + 20;
  const topY = Math.max(40, (height - tableH) / 2 - 20);

  return (
    <div style={{ ...S, left: 80, top: topY, width: cardW, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "20px 28px" }}>
      {/* 标题 */}
      <div style={{ fontFamily: FONTS.bold, fontWeight: 700, fontSize: 28, color: COLORS.hnOrange, marginBottom: 12 }}>
        🔥 今日热度 Top 10
      </div>

      {/* 表头 */}
      <div style={{ display: "flex", alignItems: "center", fontFamily: FONTS.mono, fontSize: 18, color: COLORS.dim, borderBottom: `1px solid ${SEPARATOR}`, paddingBottom: 8, marginBottom: 4 }}>
        <span style={{ width: 40 }}>#</span>
        <span style={{ flex: 1 }}>Title</span>
        <span style={{ width: 80, textAlign: "right" }}>▲</span>
        <span style={{ width: 80, textAlign: "right" }}>💬</span>
      </div>

      {/* 行 */}
      {entries.slice(0, 10).map((entry, i) => {
        const title = entry.original_title || entry.title || "";
        const titleCn = entry.title_translation || entry.title_cn || "";
        return (
          <div key={i} style={{
            display: "flex",
            alignItems: "center",
            fontFamily: FONTS.sans,
            fontSize: 18,
            color: COLORS.text,
            minHeight: rowH,
            borderBottom: i < entries.length - 1 ? `1px solid ${SEPARATOR}` : "none",
            padding: "4px 0",
          }}>
            <span style={{ width: 40, fontFamily: FONTS.mono, color: COLORS.hnOrange, fontWeight: 700 }}>{entry.rank || i + 1}</span>
            <span style={{ flex: 1, paddingRight: 12, display: "flex", flexDirection: "column", gap: 2 }}>
              <span style={{ lineHeight: 1.3, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as const }}>{title}</span>
              {titleCn && <span style={{ fontSize: 16, color: COLORS.dim, lineHeight: 1.3, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 1, WebkitBoxOrient: "vertical" as const }}>{titleCn}</span>}
            </span>
            <span style={{ width: 80, textAlign: "right", fontFamily: FONTS.mono, fontSize: 18, color: COLORS.hnOrange, flexShrink: 0 }}>{entry.score || 0}</span>
            <span style={{ width: 80, textAlign: "right", fontFamily: FONTS.mono, fontSize: 18, color: COLORS.dim, flexShrink: 0 }}>{entry.comment_count || 0}</span>
          </div>
        );
      })}
    </div>
  );
};

// ==================================================================
//  19. StancePie —— 态度分布饼图
// ==================================================================

const StancePie: React.FC<{ distribution: Record<string, number>; size: number }> = ({ distribution, size }) => {
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 8;
  const entries = Object.entries(distribution).filter(([, v]) => v > 0);

  let cumulative = 0;
  const arcs = entries.map(([label, value]) => {
    const startAngle = cumulative * 2 * Math.PI;
    cumulative += value;
    const endAngle = cumulative * 2 * Math.PI;
    const largeArc = value > 0.5 ? 1 : 0;
    const x1 = cx + r * Math.cos(startAngle - Math.PI / 2);
    const y1 = cy + r * Math.sin(startAngle - Math.PI / 2);
    const x2 = cx + r * Math.cos(endAngle - Math.PI / 2);
    const y2 = cy + r * Math.sin(endAngle - Math.PI / 2);
    const path = value >= 1
      ? `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`
      : `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`;
    const color = STANCE_COLORS[label] || COLORS.dim;
    return { label, value, path, color };
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {arcs.map((arc, i) => (
          <path key={i} d={arc.path} fill={arc.color} stroke={COLORS.cardBg} strokeWidth={2} />
        ))}
      </svg>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 10px", marginTop: 6, justifyContent: "center" }}>
        {entries.map(([label, value]) => {
          const color = STANCE_COLORS[label] || COLORS.dim;
          return (
            <span key={label} style={{ fontFamily: FONTS.mono, fontSize: 13, color, display: "flex", alignItems: "center", gap: 3 }}>
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
//  20. StoryScanCard —— 逐条速览卡（事件 + 观点列表 + 饼图）
// ==================================================================

const STANCE_COLORS: Record<string, string> = {
  "支持": "#3c7bb3",
  "质疑": "#a03030",
  "中立": "#828282",
  "调侃": "#ff6600",
  "担忧": "#9b4dca",
};

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
    <div style={{ ...S, left: 80, top: topY, width: cardW, backgroundColor: COLORS.cardBg, borderRadius: 2, padding: "24px 28px" }}>
      {/* 故事标题 */}
      <div style={{ fontFamily: FONTS.bold, fontWeight: 700, fontSize: 36, color: COLORS.text, lineHeight: 1.3, wordBreak: "break-word" }}>
        {titleCn || storyTitle}
      </div>
      {titleCn && storyTitle && (
        <div style={{ fontFamily: FONTS.mono, fontSize: 18, color: COLORS.dim, marginTop: 6, lineHeight: 1.3, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" as const }}>
          {storyTitle}
        </div>
      )}

      {/* 事件简述 */}
      {eventSummary && (
        <div style={{ fontFamily: FONTS.sans, fontSize: 24, color: COLORS.info, marginTop: 16, lineHeight: 1.5 }}>
          {eventSummary}
        </div>
      )}

      {/* 观点列表 + 饼图 */}
      {viewpoints.length > 0 && (
        <>
          <div style={{ height: 1, backgroundColor: SEPARATOR, margin: "16px 0 12px" }} />
          <div style={{ display: "flex", gap: 20 }}>
            {/* 左侧：观点列表 */}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: FONTS.bold, fontSize: 18, color: COLORS.dim, marginBottom: 8 }}>社区观点</div>
              {viewpoints.map((vp, i) => {
                const stance = vp.stance || "";
                const summary = vp.summary || "";
                const quote = vp.quote || "";
                const stanceColor = STANCE_COLORS[stance] || COLORS.dim;
                return (
                  <div key={i} style={{ marginTop: i > 0 ? 10 : 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <span style={{
                        fontFamily: FONTS.mono,
                        fontSize: 16,
                        color: stanceColor,
                        backgroundColor: `${stanceColor}22`,
                        borderRadius: 4,
                        padding: "2px 8px",
                        whiteSpace: "nowrap",
                      }}>
                        {stance}
                      </span>
                      <span style={{ fontFamily: FONTS.sans, fontSize: 22, color: COLORS.text, lineHeight: 1.4 }}>
                        {summary}
                      </span>
                    </div>
                    {quote && (
                      <div style={{ fontFamily: FONTS.sans, fontSize: 17, color: COLORS.dim, marginTop: 4, marginLeft: 12, fontStyle: "italic", lineHeight: 1.4 }}>
                        "{quote}"
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* 右侧：饼图 */}
            {hasPie && <StancePie distribution={stanceDistribution!} size={160} />}
          </div>
        </>
      )}
    </div>
  );
};

// ==================================================================
//  21. ImageCard —— 文章配图卡片（带标题叠加）
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
      borderRadius: 2, overflow: "hidden",
      border: `1px solid ${SEPARATOR}`,
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
          backgroundColor: "rgba(246, 246, 239, 0.9)",
          padding: "12px 20px",
          fontFamily: FONTS.sans, fontSize: 22, color: COLORS.text,
          lineHeight: 1.4,
        }}>
          {truncate(caption, 80)}
        </div>
      )}
    </div>
  );
};

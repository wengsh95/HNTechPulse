/* ================================================================
   CoverCard — 封面卡 (Warm Paper Theme)
   ================================================================

   Layout: single-column vertical
     - Decorative left accent bar
     - Headline (display, hero size) with date badge
     - Extended gradient divider with decorative dots
     - Highlights list (rank badge + title + metric pills + subtitle)
     - Right side decorative vertical line

   Adapted for Remotion: accepts ElementProps, uses useDesign() for scaling,
   adds subtle entrance animation via useCurrentFrame/interpolate.
*/

import React from "react";
import { useCurrentFrame, interpolate } from "remotion";
import type { Highlight } from "./cardTypes";
import { COLORS } from "./design";
import type { ElementProps } from "./utils";
import { extractCoverProps } from "./propsExtractors";
import { useDesign, FONTS, FW, ANIM, EASE_CARD, CARD_LAYOUT } from "./design";
import { CardShell, Fill } from "./CardShell";

/* ---- sub-component ---- */

function HighlightRow({
  h,
  d,
  index,
  frame,
}: {
  h: Highlight;
  d: ReturnType<typeof useDesign>;
  index: number;
  frame: number;
}) {
  // 圆形纯色序号徽章 (对齐模板 .num-disc)
  const badgeColor = COLORS.brand;
  const badgeBg = h.rank === 1 ? COLORS.brand : h.rank === 2 ? COLORS.brandSoft : COLORS.muted;
  const badgeTextColor = h.rank === 1 ? COLORS.white : h.rank === 2 ? COLORS.brandDeep : COLORS.white;
  // 非第一名的徽章使用更柔和的样式

  // 进场动画延迟
  const rowProgress = interpolate(
    frame,
    [ANIM.bodyStart + index * 6, ANIM.bodyEnd + index * 6],
    [0, 1],
    {
      easing: EASE_CARD,
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: d.scaled(24),
        padding: `${d.scaled(18)}px 0`,
        opacity: rowProgress,
        transform: `translateX(${interpolate(rowProgress, [0, 1], [-20, 0])}px)`,
      }}
    >
      {/* 圆形纯色序号徽章 (对齐模板 .num-disc) */}
      <div
        style={{
          width: d.scaled(56),
          height: d.scaled(56),
          borderRadius: "50%",
          background: h.rank === 1 ? COLORS.brand : h.rank === 2 ? COLORS.brandSoft : COLORS.brandSoft,
          color: h.rank === 1 ? COLORS.white : COLORS.brandDeep,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: d.fs.subhead,
          fontWeight: FW.heavy,
          fontFamily: FONTS.serif,
          flexShrink: 0,
          boxShadow: h.rank === 1 ? "0 4px 12px rgba(255,102,0,0.24)" : "none",
        }}
      >
        {h.rank}
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column" as const, gap: d.scaled(8) }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: d.scaled(12),
            flexWrap: "wrap" as const,
          }}
        >
          <span
            style={{
              fontSize: d.fs.subhead,
              fontWeight: FW.bold,
              lineHeight: 1.3,
              color: COLORS.fg,
              fontFamily: FONTS.serif,
            }}
          >
            {h.editorAngle}
          </span>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: d.scaled(4),
              fontFamily: FONTS.mono,
              fontSize: d.fs.pill,
              fontWeight: FW.bold,
              padding: `${d.scaled(6)}px ${d.scaled(14)}px`,
              borderRadius: d.scaled(999),
              background: COLORS.surface2, // 模板 metric-pill: warm panel bg
              color: COLORS.fg,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            &#x1F525; {h.hnScore.toLocaleString()}
          </span>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: d.scaled(4),
              fontFamily: FONTS.mono,
              fontSize: d.fs.pill,
              fontWeight: FW.bold,
              padding: `${d.scaled(6)}px ${d.scaled(14)}px`,
              borderRadius: d.scaled(999),
              background: COLORS.surface2,
              color: COLORS.fg,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            &#x1F4AC; {h.commentCount.toLocaleString()}
          </span>
        </div>
        {h.originalTitle && (
          <div
            style={{
              fontSize: d.fs.body,
              color: COLORS.muted,
              fontFamily: FONTS.mono,
            }}
          >
            {h.originalTitle}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---- main component ---- */

export const CoverCard: React.FC<ElementProps> = ({
  elementProps,
  width: _width,
  height: _height,
}) => {
  const frame = useCurrentFrame();
  const d = useDesign();

  const typed = extractCoverProps(elementProps);
  const { headline, highlights } = typed;
  const hasHighlights = highlights.length > 0;

  // Entrance animation
  const titleProgress = interpolate(frame, [ANIM.titleStart, ANIM.titleEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyProgress = interpolate(frame, [ANIM.bodyStart, ANIM.bodyEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 装饰线条动画
  const decorProgress = interpolate(frame, [6, 24], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <CardShell
      elementProps={elementProps}
      justify="center" // 内容垂直居中 (有 headline + 几条 highlight, 中等密度)
      gutter={100} // 对称左右内边距
      paddingTop={60} // 上移, 让 cover 内容更靠近 header
      paddingBottom={120}
      showTopBar
      showWatermark={false}
      showWaveform
      reserveSubtitle // 字幕始终显示, 底部给字幕让位
    >
      {/* 右侧装饰竖线 */}
      <div
        style={{
          position: "absolute",
          right: d.scaled(CARD_LAYOUT.padding.right + 20),
          top: d.scaled(140),
          width: d.scaled(2),
          height: d.scaled(300),
          background: `linear-gradient(180deg, ${COLORS.brandSoft}, transparent)`,
          borderRadius: d.scaled(1),
          opacity: decorProgress,
        }}
      />

      <Fill gap={36} maxWidth={CARD_LAYOUT.content.wideMaxWidth}>
        {/* Headline — Fraunces serif, 对齐模板 card-title */}
        <h1
          style={{
            fontSize: d.fs.hero,
            fontWeight: FW.heavy,
            lineHeight: 1.12,
            letterSpacing: "0",
            color: COLORS.fg,
            fontFamily: FONTS.serifBold,
            maxWidth: d.scaled(1400),
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [28, 0])}px)`,
          }}
        >
          {headline}
        </h1>

        {/* 分隔线 — 延伸到更宽 + 装饰圆点 */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: d.scaled(12),
            opacity: bodyProgress,
          }}
        >
          <div
            style={{
              flex: 1,
              maxWidth: d.scaled(1200),
              height: d.scaled(6),
              borderRadius: d.scaled(3),
              background: `linear-gradient(90deg, ${COLORS.brand}, ${COLORS.brandSoft}, transparent)`,
            }}
          />
          {/* 装饰圆点 */}
          <div
            style={{
              display: "flex",
              gap: d.scaled(6),
            }}
          >
            {[COLORS.brand, COLORS.brandSoft, COLORS.dim].map((color, i) => (
              <div
                key={i}
                style={{
                  width: d.scaled(8),
                  height: d.scaled(8),
                  borderRadius: "50%",
                  background: color,
                  opacity: interpolate(bodyProgress, [0, 1], [0, 0.6]),
                }}
              />
            ))}
          </div>
        </div>

        {/* Highlights */}
        {hasHighlights && (
          <div
            style={{
              display: "flex",
              flexDirection: "column" as const,
              gap: d.scaled(24),
              width: "100%",
              opacity: bodyProgress,
            }}
          >
            {highlights.map((h, i) => (
              <HighlightRow key={h.rank} h={h} d={d} index={i} frame={frame} />
            ))}
          </div>
        )}
      </Fill>
    </CardShell>
  );
};

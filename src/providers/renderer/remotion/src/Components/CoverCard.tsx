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
import {
  useDesign,
  FONTS,
  FW,
  ANIM,
  EASE_CARD,
  CARD_LAYOUT,
  COMMON_LAYOUT,
  COVER_LAYOUT,
  GRADIENTS,
} from "./design";
import { CardShell, Fill } from "./CardShell";
import { MetricPill, NumberDisc, Panel } from "./CardPrimitives";

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
  const rowProgress = interpolate(
    frame,
    [
      ANIM.bodyStart + index * COVER_LAYOUT.rowStagger,
      ANIM.bodyEnd + index * COVER_LAYOUT.rowStagger,
    ],
    [0, 1],
    {
      easing: EASE_CARD,
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  return (
    <Panel
      style={{
        display: "grid",
        gridTemplateColumns: `${d.scaled(COMMON_LAYOUT.numDiscSize)}px minmax(0, 1fr) auto`,
        alignItems: "center",
        gap: d.scaled(COVER_LAYOUT.rowGap),
        padding: `${d.scaled(COVER_LAYOUT.rowPaddingY)}px ${d.scaled(30)}px`,
        opacity: rowProgress,
        transform: `translateX(${interpolate(rowProgress, [0, 1], [-COMMON_LAYOUT.contentGap, 0])}px)`,
      }}
    >
      <NumberDisc variant={h.rank === 1 ? "solid" : "soft"} size={COVER_LAYOUT.rankBadgeSize}>
        {h.rank}
      </NumberDisc>
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column" as const,
          gap: d.scaled(COVER_LAYOUT.originalGap),
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: d.scaled(COVER_LAYOUT.titleGap),
          }}
        >
          <span
            style={{
              fontSize: d.fs.textXl,
              fontWeight: FW.bold,
              lineHeight: 1.3,
              color: COLORS.fg,
              fontFamily: FONTS.serif,
            }}
          >
            {h.editorAngle}
          </span>
        </div>
        {h.originalTitle && (
          <div
            style={{
              fontSize: d.fs.textSm,
              color: COLORS.muted,
              fontFamily: FONTS.mono,
            }}
          >
            {h.originalTitle}
          </div>
        )}
      </div>
      <div
        style={{ display: "flex", gap: d.scaled(12), flexWrap: "wrap", justifyContent: "flex-end" }}
      >
        <MetricPill
          background="rgba(245,234,219,0.72)"
          fontSize={Math.round(d.fs.textXs * 1.05)}
          style={{ padding: `${d.scaled(8)}px ${d.scaled(18)}px` }}
        >
          hot {h.hnScore.toLocaleString()}
        </MetricPill>
        <MetricPill
          background="rgba(245,234,219,0.72)"
          fontSize={Math.round(d.fs.textXs * 1.05)}
          style={{ padding: `${d.scaled(8)}px ${d.scaled(18)}px` }}
        >
          com {h.commentCount.toLocaleString()}
        </MetricPill>
      </div>
    </Panel>
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
  const subtitle =
    typeof elementProps.subtitle === "string" && elementProps.subtitle !== elementProps.date_label
      ? elementProps.subtitle
      : "";
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

  return (
    <CardShell
      elementProps={elementProps}
      justify="center" // 内容垂直居中 (有 headline + 几条 highlight, 中等密度)
      gutter={COVER_LAYOUT.gutter}
      paddingTop={COVER_LAYOUT.paddingTop}
      paddingBottom={COVER_LAYOUT.paddingBottom}
      showTopBar
      showWatermark={false}
      showWaveform
      reserveSubtitle // 字幕始终显示, 底部给字幕让位
    >
      <Fill gap={COVER_LAYOUT.fillGap} maxWidth={CARD_LAYOUT.content.wideMaxWidth}>
        {/* Headline — Fraunces serif, 对齐模板 card-title */}
        <h1
          style={{
            margin: 0,
            fontSize: d.fs.text5xl,
            fontWeight: FW.heavy,
            lineHeight: 1.12,
            letterSpacing: "0",
            color: COLORS.fg,
            fontFamily: FONTS.serifBold,
            maxWidth: d.scaled(COVER_LAYOUT.headlineMaxWidth),
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [COMMON_LAYOUT.riseLarge, 0])}px)`,
          }}
        >
          {headline}
        </h1>

        {subtitle && (
          <p
            style={{
              margin: 0,
              maxWidth: d.scaled(COVER_LAYOUT.deckMaxWidth),
              color: COLORS.muted,
              fontFamily: FONTS.sans,
              fontSize: d.fs.textLg,
              lineHeight: 1.3,
              opacity: titleProgress,
            }}
          >
            {subtitle}
          </p>
        )}

        {/* 分隔线 — 延伸到更宽 + 装饰圆点 */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: d.scaled(COVER_LAYOUT.titleGap),
            opacity: bodyProgress,
          }}
        >
          <div
            style={{
              flex: 1,
              maxWidth: d.scaled(COVER_LAYOUT.dividerMaxWidth),
              height: d.scaled(COVER_LAYOUT.dividerHeight),
              borderRadius: d.scaled(COVER_LAYOUT.dividerRadius),
              background: GRADIENTS.accentSoft,
            }}
          />
          {/* 装饰圆点 */}
          <div
            style={{
              display: "flex",
              gap: d.scaled(COVER_LAYOUT.dotGap),
            }}
          >
            {[COLORS.brand, COLORS.brandSoft, COLORS.dim].map((color, i) => (
              <div
                key={i}
                style={{
                  width: d.scaled(COVER_LAYOUT.dotSize),
                  height: d.scaled(COVER_LAYOUT.dotSize),
                  borderRadius: COMMON_LAYOUT.circleRadius,
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
              gap: d.scaled(COVER_LAYOUT.rowGap),
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

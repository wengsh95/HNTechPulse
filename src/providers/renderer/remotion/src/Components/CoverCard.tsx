/* ================================================================
   CoverCard — 封面卡 (Warm Paper Theme)
   ================================================================

   Layout: single-column vertical
     - Decorative left accent bar
     - Headline (display, hero size) with date badge
     - Extended gradient divider with decorative dots
     - Highlights list (rank badge + title + metric pills + subtitle)
     - Right side decorative vertical line

   Adapted for Remotion: accepts ElementProps, uses useDesign() for scaling.
   Entrance animation: CardShell handles card-level fade-up; per-element
   staggered fade-up is applied via ANIM_PRESETS + fadeUp() from timing.ts.
*/

import React from "react";
import { useCurrentFrame } from "remotion";
import type { Highlight } from "./cardTypes";
import type { ElementProps } from "./utils";
import { extractCoverProps } from "./propsExtractors";
import {
  ANIM,
  COLORS,
  useDesign,
  FONTS,
  FW,
  CARD_LAYOUT,
  COMMON_LAYOUT,
  COVER_LAYOUT,
  GRADIENTS,
} from "./design";
import { CardShell, Fill } from "./CardShell";
import { MetricPill, NumberDisc, Panel } from "./CardPrimitives";
import { ANIM_PRESETS, fadeUp } from "./timing";

/* ---- sub-component ---- */

function HighlightRow({
  h,
  d,
  frame,
  index,
}: {
  h: Highlight;
  d: ReturnType<typeof useDesign>;
  frame: number;
  index: number;
}) {
  return (
    <Panel
      style={{
        display: "grid",
        gridTemplateColumns: `${d.scaled(COMMON_LAYOUT.numDiscSize)}px minmax(0, 1fr) auto`,
        alignItems: "center",
        gap: d.scaled(COVER_LAYOUT.rowGap),
        padding: `${d.scaled(COVER_LAYOUT.rowPaddingY)}px ${d.scaled(30)}px`,
        ...fadeUp(frame, ANIM_PRESETS.meta, index * ANIM.rowStagger),
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
  const d = useDesign();
  const frame = useCurrentFrame();

  const typed = extractCoverProps(elementProps);
  const { headline, highlights } = typed;
  const subtitle =
    typeof elementProps.subtitle === "string" && elementProps.subtitle !== elementProps.date_label
      ? elementProps.subtitle
      : "";
  const hasHighlights = highlights.length > 0;

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
      reserveSubtitle
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
            ...fadeUp(frame, ANIM_PRESETS.title),
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
              ...fadeUp(frame, ANIM_PRESETS.body),
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
            ...fadeUp(frame, ANIM_PRESETS.body, 2),
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
                  opacity: 0.6,
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
            }}
          >
            {highlights.map((h, i) => (
              <HighlightRow key={h.rank} h={h} d={d} frame={frame} index={i} />
            ))}
          </div>
        )}
      </Fill>
    </CardShell>
  );
};

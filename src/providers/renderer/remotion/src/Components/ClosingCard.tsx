/* ================================================================
   ClosingCard — 结束卡 (Warm Paper Theme)
   ================================================================

   Layout: single-column centered vertical
     - "今日信号" headline
     - Gradient divider (same as EventCard)
     - Signal entries: one per story (category · title · note)

   Adapted for Remotion: accepts ElementProps, uses useDesign() for scaling,
   adds entrance animation via useCurrentFrame/interpolate.
*/

import React from "react";
import { useCurrentFrame, interpolate } from "remotion";
import { COLORS } from "./design";
import type { ElementProps } from "./utils";
import { extractClosingProps } from "./propsExtractors";
import { useDesign, FONTS, FW, ANIM, EASE_CARD, CARD_LAYOUT } from "./design";
import { CardShell, Fill } from "./CardShell";

/* ---- main component ---- */

export const ClosingCard: React.FC<ElementProps> = ({
  elementProps,
  width: _width,
  height: _height,
}) => {
  const frame = useCurrentFrame();
  const d = useDesign();

  const typed = extractClosingProps(elementProps);
  const { summary, completedStories } = typed;

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

  const titleY = interpolate(titleProgress, [0, 1], [12, 0]);
  const bodyY = interpolate(bodyProgress, [0, 1], [12, 0]);

  // 内容少时用 center, 多时用 start; 这里动态判断 (1-2 条 vs 3+ 条)
  const justify = completedStories.length >= 3 ? "start" : "center";

  return (
    <CardShell
      elementProps={elementProps}
      justify={justify}
      gutter={100} // 对称左右内边距
      paddingTop={80}
      paddingBottom={100}
      showTopBar
      showWatermark={false}
      showWaveform
      reserveSubtitle // 字幕始终显示, 底部给字幕让位
    >
      <Fill gap={20} maxWidth={CARD_LAYOUT.content.maxWidth}>
        {/* Summary — Fraunces serif title (对齐模板 card-title) */}
        {summary && (
          <h1
            style={{
              fontSize: d.fs.headline,
              fontWeight: FW.heavy,
              lineHeight: 1.12,
              letterSpacing: "0",
              color: COLORS.fg,
              fontFamily: FONTS.serifBold,
              opacity: titleProgress,
              transform: `translateY(${titleY}px)`,
            }}
          >
            {summary}
          </h1>
        )}

        {/* Divider */}
        <div
          style={{
            width: "100%",
            maxWidth: d.scaled(CARD_LAYOUT.divider.maxWidth),
            height: d.scaled(CARD_LAYOUT.divider.height),
            borderRadius: d.scaled(CARD_LAYOUT.divider.borderRadius),
            background: `linear-gradient(90deg, ${COLORS.brand}, ${COLORS.brandSoft}, transparent)`,
            opacity: titleProgress,
          }}
        />

        {/* Signal entries — one per story */}
        {completedStories.length > 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: d.scaled(24),
              width: "100%",
              opacity: bodyProgress,
              transform: `translateY(${bodyY}px)`,
            }}
          >
            {completedStories.map((story, i) => (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: `${d.scaled(38)}px minmax(0, 1fr)`,
                  gap: d.scaled(16),
                  alignItems: "center",
                  padding: `${d.scaled(16)}px ${d.scaled(20)}px`,
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: d.scaled(14),
                  background: "rgba(255,253,248,0.82)",
                  boxShadow: "0 4px 12px rgba(32,25,20,0.04)",
                }}
              >
                {/* Num-disc --soft (alignment: template .num-disc--soft) */}
                <span
                  style={{
                    width: d.scaled(38),
                    height: d.scaled(38),
                    borderRadius: "50%",
                    background: COLORS.brandSoft,
                    color: COLORS.brandDeep,
                    fontFamily: FONTS.serif,
                    fontSize: d.fs.bodyLg,
                    fontWeight: FW.heavy,
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  {i + 1}
                </span>
                <div style={{ minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: d.fs.subhead,
                      fontWeight: FW.heavy,
                      lineHeight: 1.3,
                      color: COLORS.fg,
                    }}
                  >
                    {story.title}
                  </div>
                  {story.signal && (
                    <div
                      style={{
                        marginTop: d.scaled(4),
                        fontSize: d.fs.bodySmall,
                        color: COLORS.muted,
                        lineHeight: 1.3,
                      }}
                    >
                      {story.signal}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 结束语由 Subtitle 组件承载, 不再在卡片内部重复 */}
      </Fill>
    </CardShell>
  );
};

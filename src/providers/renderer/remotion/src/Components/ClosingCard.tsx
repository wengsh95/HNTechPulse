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
import type { ClosingCardProps } from "./cardTypes";
import { COLORS } from "./theme";
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
  const {
    summary,
    completedStories,
  } = typed;

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
      gutter={100}                              // 对称左右内边距
      paddingTop={80}
      paddingBottom={100}
      showTopBar
      showWatermark={false}
      showWaveform
      reserveSubtitle                           // 字幕始终显示, 底部给字幕让位
    >
      <Fill gap={20} maxWidth={CARD_LAYOUT.content.maxWidth}>
        {/* Summary */}
        {summary && (
          <h1
            style={{
              fontSize: d.fs.headline,
              fontWeight: FW.heavy,
              lineHeight: 1.15,
              letterSpacing: "-0.015em",
              color: COLORS.fg,
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
            background: `linear-gradient(90deg, ${COLORS.warmBrown}, ${COLORS.warmGold}99, transparent)`,
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
                  display: "flex",
                  flexDirection: "column",
                  gap: d.scaled(6),
                  paddingBottom: d.scaled(16),
                  borderBottom: i < completedStories.length - 1 ? `1px solid ${COLORS.border}` : undefined,
                }}
              >
                <span
                  style={{
                    fontSize: d.fs.body,
                    fontWeight: FW.heavy,
                    color: COLORS.fg,
                    lineHeight: 1.3,
                  }}
                >
                  {story.title}
                </span>
                {story.signal && (
                  <span
                    style={{
                      fontSize: d.fs.bodySmall,
                      color: COLORS.muted,
                      lineHeight: 1.5,
                    }}
                  >
                    {story.signal}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* 结束语由 Subtitle 组件承载, 不再在卡片内部重复 */}
      </Fill>
    </CardShell>
  );
};

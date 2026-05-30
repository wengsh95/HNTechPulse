/* ================================================================
   ClosingCard — 结束卡 (Warm Paper Theme)
   ================================================================

   Layout: single-column centered vertical
     - Summary statement (large headline)
     - Keyword tags row
     - Takeaways list (numbered items)
     - Completed stories list (✓ check + category + title)
     - Stats row (stories / points / comments)
     - Vibe tag

   Adapted for Remotion: accepts ElementProps, uses useDesign() for scaling,
   adds entrance animation via useCurrentFrame/interpolate.
*/

import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import type { ClosingCardProps } from "./cardTypes";
import { COLORS, CARD_REF } from "./theme";
import type { ElementProps } from "./utils";
import { extractClosingProps } from "./propsExtractors";
import { ANIM_PRESETS } from "./timing";
import { CardAudioWaveform } from "./CardAudioWaveform";
import { useDesign, FONTS, FW, CARD_PAD } from "./design";
import { WatermarkCharacter } from "./WatermarkCharacter";

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
    takeaways,
  } = typed;

  // Entrance animation — unified via ANIM_PRESETS
  const cardProgress = interpolate(frame, ANIM_PRESETS.card.range, [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleProgress = interpolate(frame, ANIM_PRESETS.title.range, [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyProgress = interpolate(frame, ANIM_PRESETS.body.range, [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const cardY = interpolate(cardProgress, [0, 1], [ANIM_PRESETS.card.yOffset, 0]);
  const titleY = interpolate(titleProgress, [0, 1], [ANIM_PRESETS.title.yOffset, 0]);
  const bodyY = interpolate(bodyProgress, [0, 1], [ANIM_PRESETS.body.yOffset, 0]);

  return (
    <div
      style={{
        width: d.scaled(CARD_REF.width),
        height: "100%" as const,
        background: COLORS.bg,
        position: "relative" as const,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          width: "100%",
          height: "100%",
          opacity: cardProgress,
          transform: `translateY(${cardY}px)`,
          padding: `${d.scaled(80)}px ${d.scaled(CARD_PAD.xNormal)}px ${d.scaled(140)}px ${d.scaled(100)}px`,
          display: "flex",
          flexDirection: "column" as const,
          justifyContent: "center",
          alignItems: "flex-start",
          textAlign: "left" as const,
          gap: d.scaled(20),
          position: "relative" as const,
        }}
      >
        {/* Summary */}
        {summary && (
          <h1
            style={{
              fontSize: d.fs.headline,
              fontWeight: FW.heavy,
              lineHeight: 1.15,
              letterSpacing: "-0.015em",
              color: COLORS.fg,
              maxWidth: d.scaled(1400),
              opacity: titleProgress,
              transform: `translateY(${titleY}px)`,
            }}
          >
            {summary}
          </h1>
        )}

        {/* Takeaways */}
        {takeaways.length > 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column" as const,
              gap: d.scaled(14),
              width: "100%",
              maxWidth: d.scaled(900),
              opacity: bodyProgress,
              transform: `translateY(${bodyY}px)`,
            }}
          >
            {takeaways.map((t, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: d.scaled(12),
                  fontSize: d.fs.body,
                  color: COLORS.fg,
                  lineHeight: 1.5,
                }}
              >
                <span
                  style={{
                    fontFamily: FONTS.mono,
                    color: COLORS.warmGold,
                    fontWeight: FW.bold,
                    fontSize: d.fs.caption,
                    width: d.scaled(28),
                    flexShrink: 0,
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span>{t}</span>
              </div>
            ))}
          </div>
        )}

        <WatermarkCharacter />

        <div style={{ position: "absolute" as const, bottom: d.scaled(20) }}>
          <CardAudioWaveform src={elementProps.audio_path as string | undefined} />
        </div>
      </div>
    </div>
  );
};
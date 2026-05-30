/* ================================================================
   CoverCard — 封面卡 (Warm Paper Theme)
   ================================================================

   Layout: single-column vertical
     - SectionLabel (mono, amber dot)
     - Headline (display, hero size)
     - Divider
     - Highlights list (rank badge + title + metric pills + subtitle)

   Adapted for Remotion: accepts ElementProps, uses useDesign() for scaling,
   adds subtle entrance animation via useCurrentFrame/interpolate.
*/

import React from "react";
import { useCurrentFrame, interpolate, Easing, staticFile } from "remotion";
import type { CoverCardProps, Highlight } from "./cardTypes";
import { COLORS, CARD_REF } from "./theme";
import type { ElementProps } from "./utils";
import { extractCoverProps } from "./propsExtractors";
import { CardAudioWaveform } from "./CardAudioWaveform";
import { useDesign, FONTS, FW } from "./design";
import { WatermarkCharacter } from "./WatermarkCharacter";

/* ---- sub-component ---- */

function HighlightRow({
  h,
  d,
}: {
  h: Highlight;
  d: ReturnType<typeof useDesign>;
}) {
  const badgeBg = h.rank === 1 ? COLORS.warmBrown : h.rank === 2 ? COLORS.warmGold : COLORS.dim;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: d.scaled(28), padding: `${d.scaled(20)}px 0` }}>
      <div
        style={{
          width: d.scaled(52),
          height: d.scaled(52),
          borderRadius: d.scaled(8),
          background: badgeBg,
          color: "#fff",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: d.fs.body,
          fontWeight: FW.heavy,
          fontFamily: FONTS.mono,
          flexShrink: 0,
        }}
      >
        {h.rank}
      </div>
      <div style={{ flex: 1, display: "flex", flexDirection: "column" as const, gap: d.scaled(8) }}>
        <div
          style={{
            fontSize: d.fs.subhead,
            fontWeight: FW.bold,
            lineHeight: 1.3,
            color: COLORS.fg,
          }}
        >
          {h.editorAngle}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: d.scaled(16), flexWrap: "wrap" as const }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: d.scaled(4),
              fontFamily: FONTS.mono,
              fontSize: d.fs.pill,
              fontWeight: FW.semibold,
              padding: `${d.scaled(4)}px ${d.scaled(12)}px`,
              borderRadius: d.scaled(999),
              background: COLORS.brownBg,
              color: COLORS.warmBrown,
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
              fontWeight: FW.semibold,
              padding: `${d.scaled(4)}px ${d.scaled(12)}px`,
              borderRadius: d.scaled(999),
              background: COLORS.goldBg,
              color: COLORS.warmGold,
            }}
          >
            &#x1F4AC; {h.commentCount.toLocaleString()}
          </span>
          {h.originalTitle && (
            <span
              style={{
                fontSize: d.fs.caption,
                color: COLORS.dim,
                fontFamily: FONTS.mono,
              }}
            >
              {h.originalTitle}
            </span>
          )}
        </div>
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
  const { headline, dateLabel, categories, highlights } = typed;
  const hasHighlights = highlights.length > 0;

  // Entrance animation
  const cardProgress = interpolate(frame, [4, 22], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleProgress = interpolate(frame, [8, 26], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyProgress = interpolate(frame, [14, 32], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        width: d.scaled(CARD_REF.width),
        height: "100%" as const,
        background: COLORS.bg,
        position: "relative" as const,
        overflow: "hidden",
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [32, 0])}px)`,
      }}
    >
      <div
        style={{
          padding: `${d.scaled(80)}px ${d.scaled(100)}px`,
          height: "100%",
          display: "flex",
          flexDirection: "column" as const,
          justifyContent: "center" as const,
          gap: d.scaled(52),
          position: "relative" as const,
        }}
      >
        {/* Section label */}
        <span
          style={{
            fontFamily: FONTS.mono,
            fontSize: d.fs.caption,
            fontWeight: FW.semibold,
            letterSpacing: "0.28em",
            textTransform: "uppercase" as const,
            color: COLORS.warmGold,
            paddingLeft: d.scaled(20),
            position: "relative" as const,
          }}
        >
          <span
            style={{
              position: "absolute" as const,
              left: 0,
              top: "50%",
              transform: "translateY(-50%)",
              width: d.scaled(8),
              height: d.scaled(8),
              borderRadius: "50%",
              background: COLORS.warmBrown,
            }}
          />
          {dateLabel}
        </span>

        {/* Headline */}
        <h1
          style={{
            fontSize: d.fs.hero,
            fontWeight: FW.heavy,
            lineHeight: 1.1,
            letterSpacing: "-0.02em",
            color: COLORS.fg,
            maxWidth: d.scaled(1500),
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [28, 0])}px)`,
          }}
        >
          {headline}
        </h1>

        {/* Category count bar */}
        {categories.length > 0 && (
          <div
            style={{
              opacity: bodyProgress,
              display: "flex",
              gap: d.scaled(4),
              height: d.scaled(6),
              maxWidth: d.scaled(900),
            }}
          >
            {categories.map((c) => (
              <div
                key={c.label}
                style={{
                  flex: c.flex,
                  height: "100%",
                  borderRadius: d.scaled(3),
                  background:
                    c.color === "red"
                      ? COLORS.warmBrown
                      : c.color === "amber"
                        ? COLORS.warmGold
                        : COLORS.dim,
                }}
              />
            ))}
          </div>
        )}

        {/* Highlights */}
        {hasHighlights && (
          <div
            style={{
              display: "flex",
              flexDirection: "column" as const,
              gap: d.scaled(24),
              width: "100%",
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [10, 0])}px)`,
            }}
          >
            {highlights.map((h) => (
              <HighlightRow key={h.rank} h={h} d={d} />
            ))}
          </div>
        )}

        {/* Waveform */}
        <div style={{ position: "absolute" as const, bottom: d.scaled(20) }}>
          <CardAudioWaveform src={elementProps.audio_path as string | undefined} />
        </div>

        {/* Watermark */}
        <WatermarkCharacter />
      </div>
    </div>
  );
};
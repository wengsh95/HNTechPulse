import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { ElementProps, p } from "./utils";
import { COLORS, FONTS, FW, FS, GRADIENTS, glassCard, glassCardShadow, LAYOUT, S } from "./design";
import { GlassShimmer, CapsuleBadge, overshootTranslateY } from "./HighlightShared";

export const ClosingCard: React.FC<ElementProps> = ({ elementProps }) => {
  const frame = useCurrentFrame();

  const question = p(elementProps, "question", "");
  const visualMood = p(elementProps, "visual_mood", "");

  const cardProgress = interpolate(frame, [4, 22], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const questionProgress = interpolate(frame, [8, 26], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  const moodProgress = interpolate(frame, [14, 32], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  const brandProgress = interpolate(frame, [20, 36], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <div
      style={{
        ...S,
        left: 0,
        top: 0,
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: COLORS.bg,
      }}
    >
      <div
        style={{
          ...glassCard,
          boxShadow: glassCardShadow,
          padding: "48px 64px",
          borderRadius: LAYOUT.cardRadius,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          opacity: cardProgress,
          transform: `translateY(${overshootTranslateY(cardProgress, 28)}px)`,
          overflow: "hidden",
          position: "relative",
          maxWidth: "80%",
        }}
      >
        <GlassShimmer frame={frame} />

        {/* Header row: capsule badge */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 8,
            marginBottom: 20,
            opacity: questionProgress,
            transform: `translateY(${interpolate(questionProgress, [0, 1], [6, 0])}px)`,
          }}
        >
          <CapsuleBadge text="每日速递" />
        </div>

        {question && (
          <div
            style={{
              fontFamily: FONTS.bold,
              fontSize: FS.headline,
              color: COLORS.text,
              lineHeight: 1.35,
              textAlign: "center",
              maxWidth: "100%",
              fontWeight: FW.bold,
              letterSpacing: 0,
              opacity: questionProgress,
              transform: `translateY(${interpolate(questionProgress, [0, 1], [22, 0])}px)`,
            }}
          >
            {question}
          </div>
        )}
        {visualMood && (
          <div
            style={{
              fontFamily: FONTS.mono,
              fontSize: FS.body,
              color: COLORS.textSecondary,
              marginTop: 32,
              fontWeight: FW.medium,
              letterSpacing: 0.4,
              textTransform: "uppercase",
              opacity: moodProgress,
              transform: `translateY(${interpolate(moodProgress, [0, 1], [10, 0])}px)`,
            }}
          >
            {visualMood}
          </div>
        )}
        <div
          style={{
            fontFamily: FONTS.bold,
            fontWeight: FW.bold,
            fontSize: FS.closing,
            color: COLORS.text,
            marginTop: visualMood ? 40 : 56,
            lineHeight: 1.15,
            letterSpacing: 0,
            opacity: brandProgress,
            transform: `translateY(${interpolate(brandProgress, [0, 1], [16, 0])}px)`,
          }}
        >
          <span style={{ color: COLORS.brand }}>HN</span> TechPulse
        </div>
      </div>

      {/* Bottom brand bar */}
      <div
        style={{
          ...S,
          left: 0,
          bottom: 0,
          width: "100%",
          height: 3,
          background: GRADIENTS.brandBar,
          opacity: 0.8 * brandProgress,
        }}
      />
    </div>
  );
};

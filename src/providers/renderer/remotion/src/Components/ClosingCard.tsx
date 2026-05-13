import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { ElementProps, p } from "./utils";
import { COLORS, FONTS, FW, S } from "./design";

export const ClosingCard: React.FC<ElementProps> = ({ elementProps }) => {
  const frame = useCurrentFrame();

  const question = p(elementProps, "question", "");
  const visualMood = p(elementProps, "visual_mood", "");

  const questionProgress = interpolate(frame, [0, 24], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  const moodProgress = interpolate(frame, [14, 36], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  const brandProgress = interpolate(frame, [28, 54], [0, 1], {
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
      {question && (
        <div
          style={{
            fontFamily: FONTS.bold,
            fontSize: 38,
            color: COLORS.text,
            lineHeight: 1.35,
            textAlign: "center",
            maxWidth: "78%",
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
            fontSize: 16,
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
          fontSize: 56,
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

      {/* Bottom brand bar — mirrors CoverCard */}
      <div
        style={{
          ...S,
          left: 0,
          bottom: 0,
          width: "100%",
          height: 3,
          background: "linear-gradient(90deg, #ff6600, #FF9F0A)",
          opacity: 0.8 * brandProgress,
        }}
      />
    </div>
  );
};

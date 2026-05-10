import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { ElementProps, p } from "./utils";
import { COLORS, FONTS, S } from "./design";

export const ClosingCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
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
        background: "radial-gradient(ellipse 60% 50% at 50% 50%, rgba(0,122,255,0.06) 0%, transparent 100%)",
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
            fontWeight: 700,
            letterSpacing: -0.4,
            opacity: questionProgress,
            transform: `translateY(${interpolate(questionProgress, [0, 1], [22, 0])}px)`,
            textShadow: "0 0 60px rgba(0,122,255,0.15)",
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
            fontWeight: 500,
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
          fontWeight: 700,
          fontSize: 56,
          color: COLORS.text,
          marginTop: visualMood ? 40 : 56,
          lineHeight: 1.15,
          letterSpacing: -1.2,
          opacity: brandProgress,
          transform: `translateY(${interpolate(brandProgress, [0, 1], [16, 0])}px)`,
        }}
      >
        HN TechPulse
      </div>
    </div>
  );
};

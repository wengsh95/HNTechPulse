import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { ElementProps, p } from "./utils";
import { COLORS, FONTS, S } from "./design";

export const TitleCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();

  const titleProgress = interpolate(frame, [0, 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  const subProgress = interpolate(frame, [10, 32], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  const subtitle = p(elementProps, "subtitle", "");

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
        background: "radial-gradient(ellipse 60% 50% at 50% 50%, rgba(0,122,255,0.08) 0%, transparent 100%)",
      }}
    >
      {/* Subtle glow behind title */}
      <div
        style={{
          ...S,
          top: "50%",
          left: "50%",
          width: 600,
          height: 120,
          transform: "translate(-50%, -65%)",
          background: "radial-gradient(ellipse 100% 100% at 50% 50%, rgba(0,122,255,0.12) 0%, transparent 70%)",
          opacity: titleProgress,
        }}
      />
      <div
        style={{
          fontFamily: FONTS.bold,
          fontWeight: 700,
          fontSize: 80,
          color: COLORS.text,
          lineHeight: 1.08,
          letterSpacing: -1.8,
          opacity: titleProgress,
          transform: `translateY(${interpolate(titleProgress, [0, 1], [20, 0])}px)`,
          textShadow: "0 0 80px rgba(0,122,255,0.2)",
        }}
      >
        {p(elementProps, "title", "HN TechPulse")}
      </div>
      {subtitle && (
        <div
          style={{
            fontFamily: FONTS.sans,
            fontSize: 32,
            color: COLORS.textSecondary,
            marginTop: 28,
            fontWeight: 400,
            letterSpacing: 0.2,
            opacity: subProgress,
            transform: `translateY(${interpolate(subProgress, [0, 1], [14, 0])}px)`,
          }}
        >
          {subtitle}
        </div>
      )}
    </div>
  );
};

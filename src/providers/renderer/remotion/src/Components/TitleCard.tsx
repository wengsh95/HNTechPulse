import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { ElementProps, p } from "./utils";
import { COLORS, FONTS, S } from "./design";

export const TitleCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();

  // Title: fade in + subtle slide up
  const titleProgress = interpolate(frame, [0, 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  // Subtitle: delayed entrance
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
        backgroundColor: COLORS.background,
      }}
    >
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
        }}
      >
        {p(elementProps, "title", "HN TechPulse")}
      </div>
      {subtitle && (
        <div
          style={{
            fontFamily: FONTS.sans,
            fontSize: 32,
            color: COLORS.dim,
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

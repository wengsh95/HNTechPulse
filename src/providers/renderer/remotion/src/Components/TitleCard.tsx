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
  const headline = p(elementProps, "headline", "");
  const topics = (elementProps.topics as string[]) ?? [];

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
        padding: "0 92px",
        boxSizing: "border-box",
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
          fontSize: topics.length > 0 ? 54 : 80,
          color: COLORS.text,
          lineHeight: 1.08,
          letterSpacing: 0,
          opacity: titleProgress,
          transform: `translateY(${interpolate(titleProgress, [0, 1], [20, 0])}px)`,
          textShadow: "0 0 80px rgba(0,122,255,0.2)",
        }}
      >
        {headline || p(elementProps, "title", "HN TechPulse")}
      </div>
      {subtitle && (
        <div
          style={{
            fontFamily: FONTS.sans,
            fontSize: 32,
            color: COLORS.textSecondary,
            marginTop: topics.length > 0 ? 16 : 28,
            fontWeight: 400,
            letterSpacing: 0,
            opacity: subProgress,
            transform: `translateY(${interpolate(subProgress, [0, 1], [14, 0])}px)`,
          }}
        >
          {subtitle}
        </div>
      )}
      {topics.length > 0 && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 12,
            marginTop: 34,
            width: "min(880px, 100%)",
            opacity: subProgress,
            transform: `translateY(${interpolate(subProgress, [0, 1], [14, 0])}px)`,
          }}
        >
          {topics.map((topic, index) => (
            <div
              key={topic}
              style={{
                display: "grid",
                gridTemplateColumns: "42px 1fr",
                columnGap: 14,
                alignItems: "center",
                padding: "11px 18px",
                borderRadius: 12,
                backgroundColor: "rgba(255,255,255,0.055)",
                border: "1px solid rgba(255,255,255,0.06)",
              }}
            >
              <span
                style={{
                  fontFamily: FONTS.mono,
                  fontSize: 14,
                  fontWeight: 800,
                  color: COLORS.accentLight,
                }}
              >
                0{index + 1}
              </span>
              <span
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: 22,
                  lineHeight: 1.32,
                  fontWeight: 650,
                  color: COLORS.text,
                  overflow: "hidden",
                  display: "-webkit-box",
                  WebkitLineClamp: 1,
                  WebkitBoxOrient: "vertical" as const,
                }}
              >
                {topic}
              </span>
            </div>
          ))}
        </div>
      )}
      {topics.length > 0 && (
        <div
          style={{
            position: "absolute",
            left: 42,
            top: 36,
            fontFamily: FONTS.sans,
            fontSize: 18,
            fontWeight: 750,
            color: COLORS.textSecondary,
            opacity: subProgress,
          }}
        >
          {p(elementProps, "title", "HN TechPulse")}
        </div>
      )}
    </div>
  );
};

import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing, staticFile } from "remotion";

import { ElementProps, p } from "./utils";
import { COLORS, FONTS, FW, LAYOUT, S } from "./design";

export const CoverCard: React.FC<ElementProps> = ({ elementProps, width, height, duration }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headline = p(elementProps, "headline", "HNTech 每日技术速览");
  const subtitle = p(elementProps, "subtitle", "");
  const coverImage = p(elementProps, "cover_image", "");
  const keywords = Array.isArray(elementProps.keywords) ? elementProps.keywords.filter((k): k is string => typeof k === "string") : [];
  const resolvedImage = coverImage ? staticFile(coverImage) : "";

  // Staggered animation
  const brandProgress = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const headlineProgress = interpolate(frame, [8, 32], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const subProgress = interpolate(frame, [20, 42], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  const totalFrames = Math.max(1, Math.round((duration || 5) * fps));
  const kenBurnsScale = interpolate(frame, [0, totalFrames], [1.0, 1.06], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
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
        overflow: "hidden",
      }}
    >
      {/* Optional background image */}
      {resolvedImage && (
        <>
          <img
            src={resolvedImage}
            alt=""
            style={{
              ...S,
              left: 0,
              top: 0,
              width: "100%",
              height: "100%",
              objectFit: "cover",
              opacity: 0.35,
              transform: `scale(${kenBurnsScale})`,
            }}
          />
          <div
            style={{
              ...S,
              left: 0,
              top: 0,
              width: "100%",
              height: "100%",
              background:
                "linear-gradient(135deg, rgba(13,13,15,0.88) 0%, rgba(13,13,15,0.65) 40%, rgba(13,13,15,0.88) 100%)",
            }}
          />
        </>
      )}

      {/* Brand label */}
      <div
        style={{
          position: "absolute",
          left: LAYOUT.chromeInsetX,
          top: LAYOUT.chromeTop,
          fontFamily: FONTS.bold,
          fontSize: 22,
          fontWeight: FW.heavy,
          color: COLORS.text,
          opacity: brandProgress,
          transform: `translateY(${interpolate(brandProgress, [0, 1], [-8, 0])}px)`,
        }}
      >
        <span style={{ color: COLORS.brand }}>HN</span> TechPulse
      </div>

      {/* Main content */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          maxWidth: LAYOUT.contentMaxWidth,
          padding: "0 64px",
          boxSizing: "border-box",
        }}
      >
        {/* Headline */}
        <div
          style={{
            fontFamily: FONTS.bold,
            fontWeight: FW.heavy,
            fontSize: 68,
            color: COLORS.text,
            lineHeight: 1.12,
            textAlign: "center",
            letterSpacing: 0,
            opacity: headlineProgress,
            transform: `translateY(${interpolate(headlineProgress, [0, 1], [24, 0])}px)`,
          }}
        >
          {headline}
        </div>

        {/* Subtitle */}
        {subtitle && (
          <div
            style={{
              fontFamily: FONTS.sans,
              fontSize: 28,
              color: COLORS.textSecondary,
              marginTop: 20,
              fontWeight: FW.regular,
              letterSpacing: 0.5,
              opacity: subProgress,
              transform: `translateY(${interpolate(subProgress, [0, 1], [10, 0])}px)`,
            }}
          >
            {subtitle}
          </div>
        )}

        {/* Keyword tags */}
        {keywords.length > 0 && (
          <div
            style={{
              display: "flex",
              gap: 14,
              marginTop: subtitle ? 36 : 48,
              flexWrap: "wrap",
              justifyContent: "center",
            }}
          >
            {keywords.slice(0, 3).map((kw, i) => {
              const tagDelay = 30 + i * 6;
              const tagProgress = interpolate(frame, [tagDelay, tagDelay + 18], [0, 1], {
                easing: Easing.bezier(0.16, 1, 0.3, 1),
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });
              return (
                <div
                  key={kw}
                  style={{
                    padding: "10px 24px",
                    borderRadius: 8,
                    background: "rgba(255,255,255,0.08)",
                    border: "none",
                    fontFamily: FONTS.sans,
                    fontSize: 18,
                    fontWeight: FW.medium,
                    color: COLORS.text,
                    letterSpacing: 0.2,
                    opacity: tagProgress,
                    transform: `translateY(${interpolate(tagProgress, [0, 1], [12, 0])}px)`,
                  }}
                >
                  {kw}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Bottom brand bar */}
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

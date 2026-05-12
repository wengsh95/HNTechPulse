import React from "react";
import { useCurrentFrame, interpolate, Easing, staticFile } from "remotion";

import { ElementProps, p } from "./utils";
import { COLORS, FONTS, FW, LAYOUT, S } from "./design";

const ORANGE = "#ff6600";

export const CoverCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();

  const headline = p(elementProps, "headline", "HNTech 每日技术速览");
  const subtitle = p(elementProps, "subtitle", "");
  const coverImage = p(elementProps, "cover_image", "");
  const keywords = (elementProps.keywords as string[]) ?? [];
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
  const tagsProgress = interpolate(frame, [30, 50], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  // Decorative orb animation
  const orb1Pulse = interpolate(frame % 120, [0, 60, 120], [1, 1.15, 1]);
  const orb2Pulse = interpolate((frame + 40) % 120, [0, 60, 120], [0.85, 1, 0.85]);

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
        background: "radial-gradient(ellipse 70% 55% at 50% 40%, #1a1a3e 0%, #0a0a1a 55%, #050510 100%)",
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
                "linear-gradient(135deg, rgba(10,10,26,0.82) 0%, rgba(10,10,26,0.55) 40%, rgba(10,10,26,0.78) 100%)",
            }}
          />
        </>
      )}

      {/* Decorative geometric elements — abstract tech feel */}
      {/* Top-right accent line */}
      <div
        style={{
          ...S,
          right: -20,
          top: "8%",
          width: 280,
          height: 1,
          background: `linear-gradient(to left, ${ORANGE}, transparent)`,
          opacity: 0.5 * brandProgress,
          transform: `rotate(-18deg)`,
        }}
      />
      {/* Bottom-left accent line */}
      <div
        style={{
          ...S,
          left: -20,
          bottom: "22%",
          width: 240,
          height: 1,
          background: `linear-gradient(to right, ${COLORS.accentLight}, transparent)`,
          opacity: 0.35 * brandProgress,
          transform: `rotate(-18deg)`,
        }}
      />

      {/* Orb 1 — warm */}
      <div
        style={{
          ...S,
          right: "12%",
          top: "18%",
          width: 120,
          height: 120,
          borderRadius: "50%",
          background: `radial-gradient(circle at 50% 50%, rgba(255,102,0,0.14) 0%, transparent 70%)`,
          transform: `scale(${orb1Pulse})`,
        }}
      />
      {/* Orb 2 — cool */}
      <div
        style={{
          ...S,
          left: "8%",
          bottom: "28%",
          width: 160,
          height: 160,
          borderRadius: "50%",
          background: `radial-gradient(circle at 50% 50%, rgba(0,122,255,0.10) 0%, transparent 70%)`,
          transform: `scale(${orb2Pulse})`,
        }}
      />

      {/* Geometric diamond accent */}
      <div
        style={{
          ...S,
          right: "18%",
          bottom: "32%",
          width: 18,
          height: 18,
          border: `1px solid rgba(255,102,0,0.25)`,
          transform: `rotate(45deg) scale(${brandProgress})`,
          opacity: 0.6,
        }}
      />
      <div
        style={{
          ...S,
          left: "14%",
          top: "22%",
          width: 10,
          height: 10,
          border: `1px solid rgba(0,122,255,0.3)`,
          transform: `rotate(45deg) scale(${brandProgress})`,
          opacity: 0.5,
        }}
      />

      {/* HN accent dot grid — top right corner */}
      <div
        style={{
          ...S,
          right: 38,
          top: 34,
          display: "grid",
          gridTemplateColumns: "repeat(3, 6px)",
          gap: 8,
          opacity: 0.5 * brandProgress,
        }}
      >
        {Array.from({ length: 9 }).map((_, i) => (
          <div
            key={i}
            style={{
              width: 3,
              height: 3,
              borderRadius: "50%",
              background: i % 2 === 0 ? ORANGE : COLORS.textSecondary,
              opacity: 0.6 - i * 0.04,
            }}
          />
        ))}
      </div>

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
          letterSpacing: -0.5,
          opacity: brandProgress,
          transform: `translateY(${interpolate(brandProgress, [0, 1], [-8, 0])}px)`,
        }}
      >
        <span style={{ color: ORANGE }}>HN</span> TechPulse
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
            letterSpacing: -1.5,
            opacity: headlineProgress,
            transform: `translateY(${interpolate(headlineProgress, [0, 1], [24, 0])}px)`,
            textShadow: "0 0 100px rgba(255,102,0,0.15), 0 0 40px rgba(0,122,255,0.08)",
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
              opacity: tagsProgress,
              transform: `translateY(${interpolate(tagsProgress, [0, 1], [12, 0])}px)`,
            }}
          >
            {keywords.slice(0, 3).map((kw, i) => (
              <div
                key={kw}
                style={{
                  padding: "10px 24px",
                  borderRadius: 999,
                  background: "rgba(255,255,255,0.06)",
                  border: "1px solid rgba(255,255,255,0.10)",
                  fontFamily: FONTS.sans,
                  fontSize: 18,
                  fontWeight: FW.medium,
                  color: COLORS.text,
                  letterSpacing: 0.2,
                  backdropFilter: "blur(8px)",
                }}
              >
                {kw}
              </div>
            ))}
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
          background: `linear-gradient(to right, transparent 0%, ${ORANGE} 20%, ${COLORS.accent} 80%, transparent 100%)`,
          opacity: 0.5 * brandProgress,
        }}
      />
    </div>
  );
};

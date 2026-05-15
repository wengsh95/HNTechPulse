import React from "react";
import { interpolate, Easing } from "remotion";

import { COLORS, FONTS, FW, FS, GRADIENTS } from "./design";

export interface HighlightEntry {
  rank?: number;
  original_title?: string;
  title?: string;
  title_translation?: string;
  title_cn?: string;
  score?: number;
  comment_count?: number;
  editor_angle?: string;
  why_it_matters?: string;
  next_watch?: string;
  category?: string;
  keywords?: string[];
}

export const medalSets = [
  { text: COLORS.yellow, bg: "rgba(255,214,10,0.15)", ring: "rgba(255,214,10,0.35)" },
  { text: COLORS.textDim, bg: "rgba(245,245,247,0.08)", ring: "rgba(245,245,247,0.18)" },
  { text: COLORS.orange, bg: "rgba(255,159,10,0.12)", ring: "rgba(255,159,10,0.28)" },
];

export const MedalBadge: React.FC<{
  rank: number;
  size?: number;
  fontSize?: number;
}> = ({ rank, size = 28, fontSize = FS.label }) => {
  const isMedal = rank <= 3;
  const medal = isMedal ? medalSets[rank - 1] : null;

  if (isMedal) {
    return (
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: medal!.bg,
          border: `1.5px solid ${medal!.ring}`,
          fontFamily: FONTS.mono,
          fontSize,
          fontWeight: FW.bold,
          color: medal!.text,
          lineHeight: 1,
        }}
      >
        {rank}
      </span>
    );
  }

  return (
    <span
      style={{
        fontFamily: FONTS.mono,
        fontSize: fontSize + 3,
        fontWeight: FW.medium,
        color: COLORS.textTertiary,
      }}
    >
      {rank}
    </span>
  );
};

export const PageIndicator: React.FC<{
  pages: unknown[][];
  currentPage: number;
}> = ({ pages, currentPage }) => (
  <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 16 }}>
    {pages.map((_, pi) => (
      <div
        key={pi}
        style={{
          width: pi === currentPage ? 24 : 8,
          height: 8,
          borderRadius: 4,
          backgroundColor: pi === currentPage ? COLORS.accent : COLORS.surfaceMed,
        }}
      />
    ))}
  </div>
);

export const CategoryBadge: React.FC<{
  category: string;
  maxWidth?: number;
}> = ({ category, maxWidth = 120 }) => (
  <div
    style={{
      fontFamily: FONTS.sans,
      fontSize: FS.caption,
      fontWeight: 700,
      color: COLORS.accentLight,
      backgroundColor: COLORS.accentBg,
      borderRadius: 6,
      padding: "5px 10px",
      maxWidth,
      overflow: "hidden",
      whiteSpace: "nowrap",
      textOverflow: "ellipsis",
    }}
  >
    {category}
  </div>
);

export const KeywordTags: React.FC<{
  keywords: string[];
  max?: number;
  maxWidth?: number;
}> = ({ keywords, max = 2, maxWidth = 46 }) => (
  <div style={{ display: "flex", gap: 5 }}>
    {keywords.slice(0, max).map((kw) => (
      <span
        key={kw}
        style={{
          fontFamily: FONTS.sans,
          fontSize: FS.micro,
          color: COLORS.textTertiary,
          maxWidth,
          overflow: "hidden",
          whiteSpace: "nowrap",
          textOverflow: "ellipsis",
        }}
      >
        {kw}
      </span>
    ))}
  </div>
);

export const rowEntryAnimation = (frame: number, rowStart: number, duration: number = 20) =>
  interpolate(frame, [rowStart, rowStart + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

// ── Shared sub-components (extracted from EventCard for reuse) ──

export function lineClamp(lines: number): React.CSSProperties {
  return {
    overflow: "hidden",
    display: "-webkit-box",
    WebkitLineClamp: lines,
    WebkitBoxOrient: "vertical" as const,
  };
}

// ── Rolling number animation ──

export const RollingNumber: React.FC<{
  value: number;
  delay: number;
  frame: number;
  fontSize?: number;
  fontWeight?: number;
  color?: string;
  lineHeight?: number;
}> = ({ value, delay, frame, fontSize, fontWeight, color, lineHeight }) => {
  const rolled = Math.round(
    interpolate(frame, [delay, delay + 20], [0, value], {
      easing: Easing.out(Easing.cubic),
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }),
  );

  return (
    <span
      style={{
        fontSize,
        fontWeight,
        color,
        lineHeight,
      }}
    >
      {Math.max(0, rolled).toLocaleString("en-US")}
    </span>
  );
};

export function highlightKeywords(
  text: string,
  keywords: string[],
  frame?: number,
  delay?: number,
): React.ReactNode {
  if (!text || keywords.length === 0) return text;
  const escaped = keywords
    .filter((k) => k.length > 1)
    .map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .sort((a, b) => b.length - a.length);
  if (escaped.length === 0) return text;
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(pattern);
  if (parts.length <= 1) return text;
  return parts.map((part, i) => {
    const isMatch = keywords.some((k) => k.toLowerCase() === part.toLowerCase());
    if (isMatch) {
      const animatedBg =
        frame !== undefined && delay !== undefined
          ? `rgba(0, 122, 255, ${interpolate(frame, [delay, delay + 16], [0, 0.15], {
              easing: Easing.bezier(0.16, 1, 0.3, 1),
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })})`
          : undefined;
      return (
        <span
          key={i}
          style={{
            color: COLORS.accentLight,
            fontWeight: FW.semibold,
            ...(animatedBg !== undefined
              ? { backgroundColor: animatedBg, borderRadius: 3, padding: "0 2px" }
              : {}),
          }}
        >
          {part}
        </span>
      );
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}

export const SectionLabel: React.FC<{
  text: string;
  delay: number;
  frame: number;
}> = ({ text, delay, frame }) => {
  const progress = interpolate(frame, [delay, delay + 14], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        marginBottom: 8,
        opacity: progress,
        transform: `translateX(${interpolate(progress, [0, 1], [-6, 0])}px)`,
      }}
    >
      <div
        style={{
          width: 3,
          height: 12,
          borderRadius: 2,
          background: COLORS.accent,
          flexShrink: 0,
        }}
      />
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: FS.caption,
          fontWeight: FW.semibold,
          color: COLORS.textTertiary,
          letterSpacing: 0.6,
        }}
      >
        {text}
      </span>
    </div>
  );
};

export const MetricPill: React.FC<{
  icon: string;
  value: number;
  delay: number;
  frame: number;
}> = ({ icon, value, delay, frame }) => {
  const progress = interpolate(frame, [delay, delay + 14], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const pulse = audioPulse(frame);

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        height: 28,
        padding: "0 12px",
        borderRadius: 14,
        backgroundColor: COLORS.surfaceFaint,
        border: `1px solid ${COLORS.borderSubtle}`,
        boxSizing: "border-box",
        fontFamily: FONTS.mono,
        whiteSpace: "nowrap",
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [4, 0])}px) scale(${1 + pulse * 0.03})`,
      }}
    >
      <span style={{ fontSize: FS.label, lineHeight: 1 }}>{icon}</span>
      <RollingNumber
        value={value}
        delay={delay}
        frame={frame}
        fontSize={FS.label}
        fontWeight={FW.heavy}
        color={COLORS.textSecondary}
        lineHeight={1}
      />
    </div>
  );
};

export const KeywordTag: React.FC<{
  keyword: string;
  delay: number;
  frame: number;
}> = ({ keyword, delay, frame }) => {
  const tagProgress = interpolate(frame, [delay, delay + 16], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const pulse = audioPulse(frame);

  return (
    <span
      style={{
        fontFamily: FONTS.sans,
        fontSize: FS.caption,
        fontWeight: FW.semibold,
        color: COLORS.accentLight,
        backgroundColor: COLORS.accentSurface,
        border: `1px solid ${COLORS.accentBorderSubtle}`,
        borderRadius: 999,
        padding: "5px 14px",
        letterSpacing: 0.2,
        opacity: tagProgress * (0.95 + pulse * 0.05),
        transform: `scale(${interpolate(tagProgress, [0, 1], [0.85, 1])})`,
      }}
    >
      {keyword}
    </span>
  );
};

// ── Elastic overshoot for card entrance ──

/**
 * Computes a translateY value with subtle elastic overshoot for card entrance.
 * The card slides from `fromY` to 0, overshooting by `overshootPx` at ~85%
 * progress, then settling back to 0 at 100% progress.
 */
export function overshootTranslateY(
  progress: number,
  fromY: number,
  overshootPx: number = 2,
): number {
  return interpolate(progress, [0, 0.85, 1], [fromY, -overshootPx, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

// ── Simulated audio-reactive pulse ──

/**
 * Returns a 0-1 value simulating a bass pulse using multiple sine frequencies.
 * Creates an organic, music-like rhythm without requiring actual audio data.
 * Use for subtle scale/opacity effects that make badges feel "alive".
 */
export function audioPulse(frame: number): number {
  const raw =
    0.5 +
    0.3 * Math.sin(frame * 0.15) +
    0.2 * Math.sin(frame * 0.37) +
    0.1 * Math.sin(frame * 0.73);
  // Normalize from [-0.1, 1.1] to [0, 1]
  return (raw + 0.1) / 1.2;
}

// ── Breathing glow helper ──

/**
 * Oscillates opacity between 0.02 and 0.06 (centered on 0.04)
 * with a period of ~3 seconds (90 frames at 30fps).
 * Use for watermark numbers that should feel "alive" not "pulsing".
 */
export function breathingOpacity(frame: number): number {
  const speed = (2 * Math.PI) / 90; // ~3 second period at 30fps
  return 0.04 + 0.02 * Math.sin(frame * speed);
}

// ── Glass shimmer sweep ──

export const GlassShimmer: React.FC<{
  frame: number;
  /** Frame when shimmer sweep starts (default 10) */
  startFrame?: number;
  /** Frame when shimmer sweep ends (default 40) */
  endFrame?: number;
}> = ({ frame, startFrame = 10, endFrame = 40 }) => {
  const progress = interpolate(frame, [startFrame, endFrame], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Fade in quickly at start, fade out quickly at end
  const opacity = interpolate(progress, [0, 0.1, 0.9, 1], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Translate from left (-100%) to right (+100%)
  const translateX = interpolate(progress, [0, 1], [-100, 100]);

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        overflow: "hidden",
        pointerEvents: "none",
        zIndex: 0,
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          transform: `translateX(${translateX}%)`,
          background: GRADIENTS.shimmerSweep,
          opacity,
        }}
      />
    </div>
  );
};

export const CapsuleBadge: React.FC<{
  text: string;
}> = ({ text }) => (
  <span
    style={{
      fontFamily: FONTS.sans,
      fontSize: FS.caption,
      fontWeight: FW.heavy,
      color: COLORS.brand,
      backgroundColor: COLORS.brandBg,
      border: "1px solid " + COLORS.brandBorderSubtle,
      borderRadius: 999,
      padding: "3px 10px",
      letterSpacing: 0.3,
    }}
  >
    {text}
  </span>
);

export const dividerStyle: React.CSSProperties = {
  width: "100%",
  height: 1,
  background: GRADIENTS.divider,
  marginTop: 12,
  marginBottom: 14,
};

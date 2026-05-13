import React from "react";

/** Apple Keynote-inspired Dark Design System */
export const GRID_UNIT = 8;
export const grid = (units: number) => units * GRID_UNIT;
export const snapToGrid = (value: number) => Math.round(value / GRID_UNIT) * GRID_UNIT;

export const FONTS = {
  mono: '"SF Mono", "Menlo", "Source Code Pro", monospace',
  sans: '-apple-system, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif',
  bold: '-apple-system, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif',
};

/** Standard font weights — use only these values for predictable rendering. */
export const FW = {
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
  heavy: 800,
} as const;

export const COLORS = {
  // Dark Keynote-inspired theme
  bg: "#0d0d0f",
  surface: "rgba(255,255,255,0.06)",
  surfaceHover: "rgba(255,255,255,0.10)",
  surfaceBorder: "transparent",

  // Text hierarchy — white on dark
  text: "#f5f5f7",
  textSecondary: "rgba(245,245,247,0.60)",
  textTertiary: "rgba(245,245,247,0.38)",

  // Primary accent — Apple blue
  accent: "#007AFF",
  accentLight: "#4DA6FF",
  accentBg: "rgba(0, 122, 255, 0.12)",
  accentBorder: "rgba(0, 122, 255, 0.35)",

  // Brand accent — HN orange (secondary)
  brand: "#ff6600",
  brandLight: "#ff8b36",
  brandBg: "rgba(255, 102, 0, 0.10)",
  brandBorder: "rgba(255, 102, 0, 0.30)",

  // Semantic — Apple system colors for dark bg
  green: "#34C759",
  yellow: "#FFD60A",
  red: "#FF453A",
  purple: "#BF5AF2",
  orange: "#FF9F0A",

  // Legacy (kept for minimal diff; some may still be referenced)
  dim: "rgba(245,245,247,0.60)",
  cardBg: "rgba(255,255,255,0.06)",
  background: "#0d0d0f",
  border: "transparent",
  borderLight: "rgba(255,255,255,0.06)",
  textLight: "rgba(245,245,247,0.60)",
};

export const LAYOUT = {
  pageInset: grid(10),
  topInset: grid(10),
  bottomSafe: grid(15),
  chromeInsetX: grid(5),
  chromeTop: grid(4),
  chromeHeight: grid(4),
  progressInsetX: grid(3),
  progressBottom: grid(1),
  subtitleBottom: grid(7),
  subtitleBottomMinimal: grid(6),
  cardRadius: 14,
  cardPaddingX: grid(4),
  cardPaddingY: grid(3),
  contentMaxWidth: grid(102),
  subtitleMaxWidth: grid(130),
};

export const GRID_DEBUG = {
  unit: GRID_UNIT,
  major: grid(4),
};

/** Frosted glass card style (Keynote-inspired) */
export const glassCard: React.CSSProperties = {
  background: "rgba(255,255,255,0.06)",
  border: "none",
  borderRadius: LAYOUT.cardRadius,
  backdropFilter: "blur(40px) saturate(1.4)",
  WebkitBackdropFilter: "blur(40px) saturate(1.4)",
};

export const glassCardShadow = "0 4px 24px rgba(0,0,0,0.40), 0 1px 6px rgba(0,0,0,0.25)";

export const SHADOWS = {
  card: glassCardShadow,
  cardHover: "0 8px 32px rgba(0,0,0,0.50), 0 2px 10px rgba(0,0,0,0.30)",
};

export const sectionLabel: React.CSSProperties = {
  fontFamily: FONTS.sans,
  fontSize: 13,
  fontWeight: 600,
  color: COLORS.textTertiary,
  marginBottom: 14,
  textTransform: "none",
  letterSpacing: 0.4,
};

export const S: React.CSSProperties = { position: "absolute" as const };

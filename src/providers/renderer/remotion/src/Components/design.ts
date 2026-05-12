import React from "react";

/** Apple Keynote-inspired Dark Design System */
export const GRID_UNIT = 8;
export const grid = (units: number) => units * GRID_UNIT;
export const snapToGrid = (value: number) => Math.round(value / GRID_UNIT) * GRID_UNIT;

export const FONTS = {
  mono: '"SF Mono", "Monaco", "Courier New", monospace',
  sans: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif',
  bold: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif',
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
  // Dark theme surface colors
  bg: "#0a0a1a",
  surface: "rgba(255, 255, 255, 0.06)",
  surfaceHover: "rgba(255, 255, 255, 0.09)",
  surfaceBorder: "rgba(255, 255, 255, 0.08)",

  // Text hierarchy
  text: "#ffffff",
  textSecondary: "#98989d",
  textTertiary: "#8e8e93",

  // Accent
  accent: "#007aff",
  accentLight: "#3395ff",
  accentBg: "rgba(0, 122, 255, 0.15)",
  accentBorder: "rgba(51, 149, 255, 0.34)",

  // Semantic
  green: "#34c759",
  yellow: "#ff9f0a",
  red: "#ff3b30",
  purple: "#af52de",
  orange: "#ff9500",

  // Legacy (kept for minimal diff; some may still be referenced)
  dim: "#98989d",
  cardBg: "rgba(255, 255, 255, 0.06)",
  background: "#0a0a1a",
  border: "rgba(255, 255, 255, 0.08)",
  borderLight: "rgba(255, 255, 255, 0.05)",
  textLight: "#98989d",
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
  cardRadius: 18,
  cardPaddingX: grid(6),
  cardPaddingY: grid(5),
  contentMaxWidth: grid(102),
  subtitleMaxWidth: grid(130),
};

export const GRID_DEBUG = {
  unit: GRID_UNIT,
  major: grid(4),
};

/** Glass-morphism card style */
export const glassCard: React.CSSProperties = {
  background: "rgba(23, 24, 43, 0.84)",
  backdropFilter: "blur(18px)",
  WebkitBackdropFilter: "blur(18px)",
  border: "1px solid rgba(255, 255, 255, 0.07)",
  borderRadius: LAYOUT.cardRadius,
};

export const glassCardShadow = "0 0 0 0.5px rgba(255,255,255,0.05), 0 8px 28px rgba(0,0,0,0.22)";

export const SHADOWS = {
  card: glassCardShadow,
  cardHover: "0 0 0 0.5px rgba(255,255,255,0.1), 0 4px 8px rgba(0,0,0,0.16), 0 12px 48px rgba(0,0,0,0.32)",
};

export const sectionLabel: React.CSSProperties = {
  fontFamily: FONTS.sans,
  fontSize: 20,
  fontWeight: 700,
  color: COLORS.textTertiary,
  marginBottom: 16,
  textTransform: "uppercase",
  letterSpacing: 0.7,
};

export const S: React.CSSProperties = { position: "absolute" as const };

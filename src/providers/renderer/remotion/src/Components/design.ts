import React from "react";

/** Apple Keynote-inspired Dark Design System */
export const FONTS = {
  mono: '"SF Mono", "Monaco", "Courier New", monospace',
  sans: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif',
  bold: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif',
};

export const COLORS = {
  // Dark theme surface colors
  bg: "#0a0a1a",
  surface: "rgba(255, 255, 255, 0.06)",
  surfaceHover: "rgba(255, 255, 255, 0.09)",
  surfaceBorder: "rgba(255, 255, 255, 0.08)",

  // Text hierarchy
  text: "#ffffff",
  textSecondary: "#98989d",
  textTertiary: "#6e6e73",

  // Accent
  accent: "#007aff",
  accentLight: "#3395ff",
  accentBg: "rgba(0, 122, 255, 0.15)",

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

/** Glass-morphism card style */
export const glassCard: React.CSSProperties = {
  background: "rgba(255, 255, 255, 0.05)",
  backdropFilter: "blur(24px)",
  WebkitBackdropFilter: "blur(24px)",
  border: "1px solid rgba(255, 255, 255, 0.08)",
  borderRadius: 24,
};

export const glassCardShadow = "0 0 0 0.5px rgba(255,255,255,0.06), 0 2px 4px rgba(0,0,0,0.12), 0 8px 32px rgba(0,0,0,0.24)";

export const SHADOWS = {
  card: glassCardShadow,
  cardHover: "0 0 0 0.5px rgba(255,255,255,0.1), 0 4px 8px rgba(0,0,0,0.16), 0 12px 48px rgba(0,0,0,0.32)",
};

export const LAYOUT = {
  pageInset: 80,
  cardPaddingX: 48,
  cardPaddingY: 40,
  contentMaxWidth: 820,
  subtitleMaxWidth: 1040,
};

export const sectionLabel: React.CSSProperties = {
  fontFamily: FONTS.sans,
  fontSize: 20,
  fontWeight: 700,
  color: COLORS.textTertiary,
  marginBottom: 16,
  textTransform: "uppercase",
  letterSpacing: 0.9,
};

export const S: React.CSSProperties = { position: "absolute" as const };

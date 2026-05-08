import React from "react";

/** Apple-inspired Clean Design System */
export const FONTS = {
  mono: '"SF Mono", "Monaco", "Courier New", monospace',
  sans: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif',
  bold: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif',
};

export const COLORS = {
  bg: "#ffffff",
  text: "#1d1d1f",
  dim: "#86868b",
  accent: "#007aff",
  cardBg: "#ffffff",
  background: "#f5f5f7",
  border: "#e5e5ea",
  borderLight: "#f0f0f5",
  textLight: "#6e6e73",
};

export const SHADOWS = {
  card: "0 1px 2px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.06), 0 8px 40px rgba(0,0,0,0.06)",
  cardHover: "0 2px 4px rgba(0,0,0,0.06), 0 8px 24px rgba(0,0,0,0.10), 0 16px 56px rgba(0,0,0,0.08)",
};

export const S: React.CSSProperties = { position: "absolute" as const };

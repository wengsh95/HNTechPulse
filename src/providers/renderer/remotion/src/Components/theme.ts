/* ================================================================
   Warm Paper Theme — Design Tokens
   Ported from react/content with Remotion responsive scaling.
   ================================================================ */

import { useMemo } from "react";
import { useVideoConfig } from "remotion";

// ---- Reference dimensions (1080p landscape) ----
const REF_WIDTH = 1920;
const REF_HEIGHT = 1080;

// ---- Static color tokens ----
export const COLORS = {
  // Canvas
  bg: "#fefcf8",
  surface: "#fff9f0",
  surface2: "#f0e8d8",
  fg: "#2c2416",
  muted: "#8b8070",
  dim: "#b0a595",
  border: "#e5ddd0",

  // Accent colors
  warmBrown: "#c17d4b",
  warmGold: "#d4a854",
  sage: "#5a8a6a",

  // Accent backgrounds
  brownBg: "#faf0e5",
  goldBg: "#faf3e0",
  sageBg: "#e8f0e5",

  // Decorative stripe
  stripeBrown: "#c17d4b",
  stripeGold: "#d4a854",
  stripeBase: "#e5ddd0",

  // Special
  purple: "#9b7ec4",
  shell: "#faf5ee",
} as const;

// ---- Typography ----
export const TYPOGRAPHY = {
  fontDisplay:
    "'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', system-ui, -apple-system, sans-serif",
  fontMono:
    "'JetBrains Mono', 'SF Mono', 'Cascadia Code', ui-monospace, monospace",
} as const;

// ---- Card dimensions (reference, scaled at runtime) ----
export const CARD_REF = {
  width: 1920,
  height: 1080,
} as const;

// ---- Decorative stripe gradient ----
export const DECORATIVE_STRIPE = `repeating-linear-gradient(
  -45deg,
  ${COLORS.stripeGold} 0px,
  ${COLORS.stripeGold} 14px,
  ${COLORS.stripeBrown} 14px,
  ${COLORS.stripeBrown} 28px
)` as const;

// ---- Shared card padding (reference px, scaled at runtime) ----
export const CARD_PAD = {
  x: 100,
  y: 80,
} as const;

// ---- Shared fonts (re-export for convenience) ----
export const FONTS = {
  display: TYPOGRAPHY.fontDisplay,
  mono: TYPOGRAPHY.fontMono,
};

// ---- Standard font weights ----
export const FW = {
  regular: 400 as const,
  medium: 500 as const,
  semibold: 600 as const,
  bold: 700 as const,
  heavy: 900 as const,
};

// ---- Design tokens context ----
export interface DesignTokens {
  scaled: (px: number) => number;
  width: number;
  height: number;
  cardWidth: number;
  cardHeight: number;
}

function createTokens(w: number, h: number): DesignTokens {
  const scale = Math.min(w / REF_WIDTH, h / REF_HEIGHT);
  return {
    scaled: (px: number) => Math.round(px * scale),
    width: w,
    height: h,
    cardWidth: Math.round(CARD_REF.width * scale),
    cardHeight: Math.round(CARD_REF.height * scale),
  };
}

export function useTheme(): DesignTokens {
  const config = useVideoConfig();
  return useMemo(
    () => createTokens(config.width, config.height),
    [config.width, config.height],
  );
}

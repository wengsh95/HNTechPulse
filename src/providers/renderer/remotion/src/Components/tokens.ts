import { useMemo } from "react";
import { useVideoConfig } from "remotion";

const REF_WIDTH = 1920;
const REF_HEIGHT = 1080;

const TEMPLATE_TO_1080P_SCALE = 1.5;

export const VIDEO_DEFAULTS = {
  width: REF_WIDTH,
  height: REF_HEIGHT,
  fps: 24,
  durationInFrames: 240,
  fallbackDurationSeconds: 10,
  stillDurationInFrames: 1,
  bgColor: "#fbf4e8",
} as const;

export const FONTS = {
  mono: '"JetBrains Mono", "SF Mono", "Menlo", "Source Code Pro", monospace',
  sans: '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", "Source Han Sans SC", sans-serif',
  bold: '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", "Source Han Sans SC", sans-serif',
  serif:
    '"Fraunces", "Noto Serif SC", "Source Han Serif SC", "Songti SC", "STSong", Georgia, "Times New Roman", serif',
  serifBold:
    '"Fraunces", "Noto Serif SC", "Source Han Serif SC", "Songti SC", "STSong", Georgia, "Times New Roman", serif',
};

export const FW = {
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
  heavy: 800,
} as const;

export const COLORS = {
  bg: "#fbf4e8",
  surface: "rgba(32,25,20,0.04)",
  surfaceHover: "rgba(32,25,20,0.07)",
  surfaceBorder: "rgba(32,25,20,0.10)",
  surface2: "#f5eadb",

  text: "#201914",
  fg: "#201914",
  textSecondary: "rgba(32,25,20,0.65)",
  textTertiary: "rgba(32,25,20,0.42)",
  textBody: "rgba(32,25,20,0.88)",
  textDim: "rgba(32,25,20,0.72)",
  textFaint: "rgba(32,25,20,0.28)",
  muted: "#7d7062",
  dim: "rgba(32,25,20,0.55)",
  inkSoft: "#4d4238",
  inkFaint: "#a39482",

  accent: "#ff6600",
  accentLight: "#b64a12",
  accentBg: "rgba(255,102,0,0.10)",
  accentBorder: "rgba(255,102,0,0.28)",

  brand: "#ff6600",
  brandLight: "#b64a12",
  brandBg: "rgba(255,102,0,0.08)",
  brandBorder: "rgba(255,102,0,0.25)",
  brandDeep: "#b64a12",
  brandSoft: "#ffe0c7",

  warmBrown: "#ff6600",
  warmGold: "#b64a12",
  sage: "#4f8761",

  brownBg: "#ffe0c7",
  goldBg: "#faf3e0",
  sageBg: "#e8f0e5",

  green: "#4f8761",
  yellow: "#c69230",
  red: "#ff6600",
  orangeRed: "#ff6600",
  purple: "#9b7ec4",
  orange: "#ff6600",
  gray: "#8a8075",
  white: "#ffffff",

  surfaceSubtle: "rgba(32,25,20,0.03)",
  surfaceFaint: "rgba(32,25,20,0.04)",
  surfaceLow: "rgba(32,25,20,0.06)",
  surfaceMid: "rgba(32,25,20,0.08)",
  surfaceMed: "rgba(32,25,20,0.10)",

  borderSubtle: "rgba(32,25,20,0.06)",
  borderLow: "rgba(32,25,20,0.08)",
  borderMid: "rgba(32,25,20,0.15)",

  accentSurface: "rgba(255,102,0,0.08)",
  accentBorderSubtle: "rgba(255,102,0,0.15)",
  accentBorderMid: "rgba(255,102,0,0.22)",

  brandBorderSubtle: "rgba(255,102,0,0.22)",

  bgTint75: "rgba(251,244,232,0.75)",
  bgTint88: "rgba(251,244,232,0.88)",
  bgStroke: "rgba(251,244,232,0.6)",
  cardBg: "rgba(32,25,20,0.04)",
  background: "#fbf4e8",
  border: "rgba(32,25,20,0.10)",
  borderStrong: "rgba(32,25,20,0.18)",
  borderLight: "rgba(32,25,20,0.06)",
  textLight: "rgba(32,25,20,0.55)",

  paper: "#fffaf2",
  panel: "#fffdf8",
};

export const SHADOWS = {
  card: "0 24px 60px rgba(32,25,20,0.16)",
  panel: "0 4px 12px rgba(32,25,20,0.04)",
  brandBadge: "0 4px 12px rgba(255,102,0,0.24)",
} as const;

export const SURFACES = {
  panel: "rgba(255,253,248,0.82)",
  tag: "rgba(255,255,255,0.48)",
  subtitle: "rgba(254,252,248,0.88)",
  cardBorder: "1px solid rgba(32,25,20,0.08)",
} as const;

const LAYOUT = {
  pageInset: 96,
  topInset: 96,
  bottomSafe: 144,
  chromeInsetX: 48,
  chromeTop: 40,
  chromeHeight: 40,
  progressInsetX: 32,
  progressBottom: 16,
  subtitleBottom: 100,
  subtitleBottomMinimal: 72,
  cardRadius: 20,
  panelRadius: 14,
  chipRadius: 10,
  cardPaddingX: 40,
  cardPaddingY: 32,
  contentMaxWidth: 960,
  contentWideMaxWidth: 1200,
  subtitleMaxWidth: 1216,
};

export const COMMON_LAYOUT = {
  circleRadius: "50%",
  pillRadius: 999,
  smallRadius: 6,
  hairlineRadius: 2,
  dividerRadius: 3,
  panelRadius: 21,
  sectionMarkerWidth: 6,
  sectionMarkerHeight: 27,
  sectionRuleWidth: 5,
  numDiscSize: 57,
  metricGap: 12,
  metricPaddingY: 12,
  metricPaddingX: 24,
  panelPaddingY: 24,
  panelPaddingX: 30,
  panelGap: 24,
  itemGap: 18,
  contentGap: 30,
  riseSmall: 6,
  riseMedium: 10,
  riseLarge: 16,
} as const;

const FS = {
  text6xl: 64 * TEMPLATE_TO_1080P_SCALE,
  text5xl: 54 * TEMPLATE_TO_1080P_SCALE,
  text4xl: 44 * TEMPLATE_TO_1080P_SCALE,
  text3xl: 34 * TEMPLATE_TO_1080P_SCALE,
  text2xl: 30 * TEMPLATE_TO_1080P_SCALE,
  textXl: 25.5 * TEMPLATE_TO_1080P_SCALE,
  textLg: 23 * TEMPLATE_TO_1080P_SCALE,
  textBase: 22 * TEMPLATE_TO_1080P_SCALE,
  textSm: 18 * TEMPLATE_TO_1080P_SCALE,
  textXs: 15.5 * TEMPLATE_TO_1080P_SCALE,
  subtitle: 48,
};

interface DesignTokens {
  scaled: (px: number) => number;
  layout: typeof LAYOUT;
  fs: typeof FS;
  isCompactHeight: boolean;
  isPortrait: boolean;
  getCardMaxHeight: number;
}

function createDesignTokens(width: number, height: number): DesignTokens {
  const scale = Math.min(width / REF_WIDTH, height / REF_HEIGHT);
  const scaled = (px: number) => Math.round(px * scale);

  const isPortrait = height > width;
  const isCompactHeight = scale < 0.8;

  const getCardMaxHeight = isPortrait ? Math.round(height * 0.55) : Math.round(height * 0.78);

  const layout: typeof LAYOUT = {
    pageInset: scaled(LAYOUT.pageInset),
    topInset: scaled(LAYOUT.topInset),
    bottomSafe: scaled(LAYOUT.bottomSafe),
    chromeInsetX: scaled(LAYOUT.chromeInsetX),
    chromeTop: scaled(LAYOUT.chromeTop),
    chromeHeight: scaled(LAYOUT.chromeHeight),
    progressInsetX: scaled(LAYOUT.progressInsetX),
    progressBottom: scaled(LAYOUT.progressBottom),
    subtitleBottom: scaled(LAYOUT.subtitleBottom),
    subtitleBottomMinimal: scaled(LAYOUT.subtitleBottomMinimal),
    cardRadius: scaled(LAYOUT.cardRadius),
    panelRadius: scaled(LAYOUT.panelRadius),
    chipRadius: scaled(LAYOUT.chipRadius),
    cardPaddingX: scaled(LAYOUT.cardPaddingX),
    cardPaddingY: scaled(LAYOUT.cardPaddingY),
    contentMaxWidth: scaled(LAYOUT.contentMaxWidth),
    contentWideMaxWidth: scaled(LAYOUT.contentWideMaxWidth),
    subtitleMaxWidth: scaled(LAYOUT.subtitleMaxWidth),
  };

  const fs: typeof FS = {
    text6xl: scaled(FS.text6xl),
    text5xl: scaled(FS.text5xl),
    text4xl: scaled(FS.text4xl),
    text3xl: scaled(FS.text3xl),
    text2xl: scaled(FS.text2xl),
    textXl: scaled(FS.textXl),
    textLg: scaled(FS.textLg),
    textBase: scaled(FS.textBase),
    textSm: scaled(FS.textSm),
    textXs: scaled(FS.textXs),
    subtitle: scaled(FS.subtitle),
  };

  return {
    scaled,
    layout,
    fs,
    isCompactHeight,
    isPortrait,
    getCardMaxHeight,
  };
}

export function useDesign(): DesignTokens {
  const config = useVideoConfig();
  return useMemo(
    () => createDesignTokens(config.width, config.height),
    [config.width, config.height],
  );
}

export const GRADIENTS = {
  brandBar: `linear-gradient(90deg, ${COLORS.brand}, ${COLORS.brand})`,
  accentFill: `linear-gradient(90deg, ${COLORS.accent}, ${COLORS.accentLight})`,
  accentSoft: `linear-gradient(90deg, ${COLORS.brand}, ${COLORS.brandSoft}, transparent)`,
  shimmerSweep: `linear-gradient(105deg, transparent 40%, ${COLORS.surfaceLow} 48%, ${COLORS.surfaceLow} 52%, transparent 60%)`,
  divider: `linear-gradient(90deg, ${COLORS.brand}, transparent)`,
  subtitleMinimal: `linear-gradient(90deg, rgba(251,244,232,0), ${COLORS.bgTint75} 16%, ${COLORS.bgTint75} 84%, rgba(251,244,232,0))`,
  subtitleStandard: `linear-gradient(90deg, rgba(251,244,232,0), ${COLORS.bgTint88} 14%, ${COLORS.bgTint88} 86%, rgba(251,244,232,0))`,
  keywordTagBg: `rgba(255,102,0,0.08)`,
  dotGrid: `radial-gradient(circle, rgba(32,25,20,0.04) 1px, transparent 1px)`,
} as const;

export const S: React.CSSProperties = { position: "absolute" as const };

export const CARD_REF = {
  width: 1920,
  height: 1080,
} as const;

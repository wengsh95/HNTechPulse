import React, { createContext, useContext } from "react";
import { Easing } from "remotion";

/** 硬编码 1080p 输出，不做分辨率缩放 */

/** Keynote 风格暗色设计系统（1080p 固定值） */
export const GRID_UNIT = 8;
export const grid = (units: number) => units * GRID_UNIT;
export const snapToGrid = (value: number) => Math.round(value / GRID_UNIT) * GRID_UNIT;

export const FONTS = {
  mono: '"SF Mono", "Menlo", "Source Code Pro", monospace',
  sans: '"Inter", "Noto Sans SC", -apple-system, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif',
  bold: '"Inter", "Noto Sans SC", -apple-system, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif',
};

/** 标准字重 */
export const FW = {
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
  heavy: 800,
} as const;

export const COLORS = {
  bg: "#0d0d0f",
  surface: "rgba(255,255,255,0.06)",
  surfaceHover: "rgba(255,255,255,0.10)",
  surfaceBorder: "transparent",

  text: "#f5f5f7",
  textSecondary: "rgba(245,245,247,0.60)",
  textTertiary: "rgba(245,245,247,0.38)",

  accent: "#007AFF",
  accentLight: "#4DA6FF",
  accentBg: "rgba(0, 122, 255, 0.12)",
  accentBorder: "rgba(0, 122, 255, 0.35)",

  brand: "#ff6600",
  brandLight: "#ff8b36",
  brandBg: "rgba(255, 102, 0, 0.10)",
  brandBorder: "rgba(255, 102, 0, 0.30)",

  green: "#34C759",
  yellow: "#FFD60A",
  red: "#FF453A",
  orangeRed: "#FF5A5F",
  purple: "#BF5AF2",
  orange: "#FF9F0A",
  gray: "#8E8E93",
  white: "#ffffff",

  textBody: "rgba(245,245,247,0.85)",
  textDim: "rgba(245,245,247,0.70)",
  textFaint: "rgba(255,255,255,0.22)",

  surfaceSubtle: "rgba(255,255,255,0.03)",
  surfaceFaint: "rgba(255,255,255,0.04)",
  surfaceLow: "rgba(255,255,255,0.08)",
  surfaceMid: "rgba(255,255,255,0.10)",
  surfaceMed: "rgba(255,255,255,0.12)",

  borderSubtle: "rgba(255,255,255,0.07)",
  borderLow: "rgba(255,255,255,0.08)",
  borderMid: "rgba(255,255,255,0.18)",

  accentSurface: "rgba(0,122,255,0.10)",
  accentBorderSubtle: "rgba(0,122,255,0.18)",
  accentBorderMid: "rgba(0,122,255,0.25)",

  brandBorderSubtle: "rgba(255,102,0,0.25)",

  bgTint75: "rgba(13,13,15,0.75)",
  bgTint88: "rgba(13,13,15,0.88)",
  bgStroke: "rgba(13,13,15,0.6)",

  dim: "rgba(245,245,247,0.60)",
  cardBg: "rgba(255,255,255,0.06)",
  background: "#0d0d0f",
  border: "transparent",
  borderLight: "rgba(255,255,255,0.06)",
  textLight: "rgba(245,245,247,0.60)",
};

/** 1080p 固定布局值 */
export const LAYOUT = {
  pageInset: 96,
  topInset: 96,
  bottomSafe: 144,
  chromeInsetX: 48,
  chromeTop: 40,
  chromeHeight: 40,
  progressInsetX: 32,
  progressBottom: 16,
  subtitleBottom: 80,
  subtitleBottomMinimal: 72,
  cardRadius: 16,
  panelRadius: 12,
  chipRadius: 8,
  cardPaddingX: 40,
  cardPaddingY: 32,
  contentMaxWidth: 960,
  contentWideMaxWidth: 1200,
  subtitleMaxWidth: 1216,
};

/** 1080p 固定字号（基准值 × 1.18 高度增强） */
export const FS = {
  hero: 66,
  headline: 50,
  subhead: 35,
  closing: 61,

  body: 26,
  bodySmall: 21,
  bodyLg: 24,
  subtitle2: 21,

  label: 21,
  caption: 18,
  pill: 14,
  micro: 13,

  watermark: 85,
  watermarkLg: 113,
  subtitle: 33,
};

export interface DesignTokens {
  /** Scale a pixel value (1080p 固定：等价于 Math.round) */
  scaled: (px: number) => number;
  layout: typeof LAYOUT;
  fs: typeof FS;
  grid: (units: number) => number;
  isCompactHeight: boolean;
  getCardMaxHeight: number;
}

/** 1080p 预计算的设计令牌 */
const _tokens: DesignTokens = {
  scaled: Math.round,
  layout: LAYOUT,
  fs: FS,
  grid: (units: number) => units * GRID_UNIT,
  isCompactHeight: false,
  getCardMaxHeight: 840,
};

/** 获取设计令牌（1080p 固定值） */
export function useDesign(): DesignTokens {
  return _tokens;
}

// ── Chapter token map ──
//
// 每张卡所属的"章节"决定了它的 accent 配色（强调条、tag、轻量装饰）。
// 共性骨架（卡壳 / 字号 / 间距 / 进场动画）保持一致；只通过 chapter 注入差异。
//
// motion / viz 是为后续 Layer B/C 预留的字段，目前仅 accent 被消费。

export type ChapterName = "cover" | "focus" | "atmosphere" | "closing";

export interface ChapterTone {
  /** 主 accent 色 —— SectionLabel 的强调条 / KeywordTag 文本色 / chrome pill 文本色 */
  accent: string;
  /** Accent 的浅色变体 */
  accentLight: string;
  /** 弱化背景（用于 KeywordTag / chrome pill 背景） */
  accentBg: string;
  /** 边框 */
  accentBorder: string;
  /** SectionLabel 副文本色（标题旁的章节名） */
  labelText: string;
  /** 后续 Layer B 用 */
  motion: "heroFadeUp" | "highlightPen" | "countUp" | "wordCascade" | "typewriter";
  /** 后续 Layer C 用 */
  viz: "miniBars" | "imageHero" | "pieChart" | "imageSide" | "barList" | "tally";
}

export const CHAPTERS: Record<ChapterName, ChapterTone> = {
  cover: {
    accent: COLORS.brand,
    accentLight: COLORS.brandLight,
    accentBg: COLORS.brandBg,
    accentBorder: COLORS.brandBorderSubtle,
    labelText: COLORS.brandLight,
    motion: "heroFadeUp",
    viz: "miniBars",
  },
  focus: {
    accent: COLORS.brand,
    accentLight: COLORS.brandLight,
    accentBg: COLORS.brandBg,
    accentBorder: COLORS.brandBorderSubtle,
    labelText: COLORS.brandLight,
    motion: "highlightPen",
    viz: "imageHero",
  },
  atmosphere: {
    accent: COLORS.purple,
    accentLight: COLORS.purple,
    accentBg: "rgba(191,90,242,0.10)",
    accentBorder: "rgba(191,90,242,0.30)",
    labelText: COLORS.purple,
    motion: "countUp",
    viz: "pieChart",
  },
  closing: {
    accent: COLORS.accent,
    accentLight: COLORS.accentLight,
    accentBg: COLORS.accentBg,
    accentBorder: COLORS.accentBorder,
    labelText: COLORS.accentLight,
    motion: "heroFadeUp",
    viz: "tally",
  },
};

const ChapterContext = createContext<ChapterName>("focus");

/** 当前章节 */
export function useChapter(): ChapterName {
  return useContext(ChapterContext);
}

/** 当前章节的配色令牌 */
export function useChapterTone(): ChapterTone {
  return CHAPTERS[useContext(ChapterContext)];
}

export const ChapterProvider: React.FC<{
  chapter: ChapterName;
  children: React.ReactNode;
}> = ({ chapter, children }) =>
  React.createElement(ChapterContext.Provider, { value: chapter }, children);

/** element_type → chapter 的标准映射（GlobalChrome / 卡片均可用） */
export const ELEMENT_TYPE_TO_CHAPTER: Record<string, ChapterName> = {
  cover_card: "cover",
  event_card: "focus",
  atmosphere_card: "atmosphere",
  closing_card: "closing",
};

/** 毛玻璃卡片样式（Keynote 风格） */
export const glassCard: React.CSSProperties = {
  background: COLORS.surface,
  border: "none",
  borderRadius: LAYOUT.cardRadius,
  backdropFilter: "blur(40px) saturate(1.4)",
  WebkitBackdropFilter: "blur(40px) saturate(1.4)",
};

export const glassCardShadow = `0 4px 24px rgba(0,0,0,0.40), 0 1px 6px rgba(0,0,0,0.25)`;

export const innerPanel: React.CSSProperties = {
  background: COLORS.surfaceFaint,
  border: `1px solid ${COLORS.borderLow}`,
  borderRadius: LAYOUT.panelRadius,
};

export const glassGlow = `0 0 48px rgba(0,122,255,0.12), 0 8px 32px rgba(0,0,0,0.50), 0 2px 8px rgba(0,0,0,0.30)`;

export const SHADOWS = {
  card: glassCardShadow,
  cardHover: "0 8px 32px rgba(0,0,0,0.50), 0 2px 10px rgba(0,0,0,0.30)",
};

/** 命名渐变 */
export const GRADIENTS = {
  brandBar: `linear-gradient(90deg, ${COLORS.brand}, ${COLORS.orange})`,
  accentFill: `linear-gradient(90deg, ${COLORS.accent}, ${COLORS.accentLight})`,
  shimmerSweep: `linear-gradient(105deg, transparent 40%, ${COLORS.surfaceLow} 48%, ${COLORS.surfaceLow} 52%, transparent 60%)`,
  divider: `linear-gradient(90deg, ${COLORS.surfaceMid} 0%, ${COLORS.surfaceFaint} 100%)`,
  subtitleMinimal: `linear-gradient(90deg, rgba(13,13,15,0), ${COLORS.bgTint75} 16%, ${COLORS.bgTint75} 84%, rgba(13,13,15,0))`,
  subtitleStandard: `linear-gradient(90deg, rgba(13,13,15,0), ${COLORS.bgTint88} 14%, ${COLORS.bgTint88} 86%, rgba(13,13,15,0))`,
  keywordTagBg: `rgba(0,122,255,0.10)`,
  dotGrid: `radial-gradient(circle, ${COLORS.surfaceSubtle} 1px, transparent 1px)`,
} as const;

export const sectionLabel: React.CSSProperties = {
  fontFamily: FONTS.sans,
  fontSize: FS.label,
  fontWeight: 600,
  color: COLORS.textTertiary,
  marginBottom: 14,
  textTransform: "none",
  letterSpacing: 0.4,
};

export const S: React.CSSProperties = { position: "absolute" as const };

// ── Shared card layout constants ──

/** Standard card padding (px values, scaled at runtime via d.scaled) */
export const CARD_PAD = {
  xNormal: 56,
  xCompact: 40,
  yNormal: 56,
  yCompact: 36,
} as const;

/** Standard animation timing (frames at 30fps) */
export const ANIM = {
  cardStart: 4,
  cardEnd: 22,
  titleStart: 8,
  titleEnd: 26,
  bodyStart: 14,
  bodyEnd: 32,
  imageStart: 6,
  imageEnd: 26,
  footerStart: 20,
  footerEnd: 36,
  rowDuration: 20,
  sectionLabelDuration: 14,
  rowStagger: 5,
} as const;

/** Standard easing curve used across all cards */
export const EASE_CARD = Easing.bezier(0.16, 1, 0.3, 1);

/** Standard header margin-bottom */
export const HEADER_MARGIN = {
  normal: 28,
  compact: 20,
} as const;

/** Standard title → body gap (margin-bottom after title) */
export const TITLE_BODY_GAP = {
  normal: 24,
  compact: 16,
} as const;

/** Standard body section gap */
export const BODY_SECTION_GAP = {
  normal: 24,
  compact: 18,
} as const;

/** Standard divider margin */
export const DIVIDER_MARGIN = {
  top: 14,
  bottom: 16,
} as const;

/** Standard keyword gap */
export const KEYWORD_GAP = 8;

/** Standard card entrance translateY */
export const CARD_ENTRANCE_Y = 32;

/** Standard title entrance translateY */
export const TITLE_ENTRANCE_Y = 12;

/** Standard body entrance translateY */
export const BODY_ENTRANCE_Y = 12;

/** Standard header entrance translateY */
export const HEADER_ENTRANCE_Y = 8;

/** Standard footer entrance translateY */
export const FOOTER_ENTRANCE_Y = 6;

/** Standard image panel translateX */
export const IMAGE_ENTRANCE_X = 28;

/** Standard chapter watermark offset from top padding */
export const WATERMARK_TOP_OFFSET = 6;

/** Standard item sub-component animation duration (frames) */
export const ITEM_DURATION = 18;

/** Standard pill/badge animation duration (frames) */
export const PILL_DURATION = 14;

/** Standard SectionLabel accent bar dimensions */
export const SECTION_BAR = {
  width: 3,
  height: 14,
  borderRadius: 2,
} as const;

/** Standard pill border radius (fully rounded) */
export const PILL_RADIUS = 999;

/** Standard metric pill height */
export const METRIC_PILL_HEIGHT = 32;

/** Standard metric pill padding horizontal */
export const METRIC_PILL_PAD_X = 14;

/** Standard hero entrance translateY (CoverCard headline) */
export const HERO_ENTRANCE_Y = 28;

/** Standard closing question entrance translateY */
export const CLOSING_QUESTION_ENTRANCE_Y = 24;

/** Standard closing brand entrance translateY */
export const CLOSING_BRAND_ENTRANCE_Y = 18;

/** Standard image panel border radius */
export const IMAGE_PANEL_RADIUS = 14;

/** Standard image panel box shadow */
export const IMAGE_PANEL_SHADOW = glassGlow;

/** Standard image panel border */
export const IMAGE_PANEL_BORDER = `1px solid ${COLORS.borderLow}`;

/** Standard image panel background */
export const IMAGE_PANEL_BG = COLORS.surfaceSubtle;

/** Standard row entry stagger (frames between items) */
export const ROW_STAGGER = 5;

/** Standard keyword tag padding */
export const KEYWORD_TAG_PAD = {
  y: 6,
  x: 16,
} as const;

/** Standard capsule badge padding */
export const CAPSULE_PAD = {
  y: 4,
  x: 12,
} as const;

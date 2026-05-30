import React, { createContext, useContext, useMemo } from "react";
import { Easing, useVideoConfig } from "remotion";

/** Reference design dimensions (1080p landscape) — all pixel values below are relative to this */
const REF_WIDTH = 1920;
const REF_HEIGHT = 1080;

/** Keynote 风格暗色设计系统（基于 1080p 参考值，运行时按实际分辨率缩放） */
export const GRID_UNIT = 8;
export const grid = (units: number) => units * GRID_UNIT;
export const snapToGrid = (value: number) => Math.round(value / GRID_UNIT) * GRID_UNIT;

export const FONTS = {
  mono: '"JetBrains Mono", "SF Mono", "Menlo", "Source Code Pro", monospace',
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
  // ── Warm paper canvas ──
  bg: "#fefcf8",
  surface: "rgba(44,36,22,0.04)",
  surfaceHover: "rgba(44,36,22,0.07)",
  surfaceBorder: "#e5ddd0",

  text: "#2c2416",
  fg: "#2c2416", // warm paper primary text — use over text
  textSecondary: "rgba(44,36,22,0.65)",
  textTertiary: "rgba(44,36,22,0.42)",
  textBody: "rgba(44,36,22,0.88)",
  textDim: "rgba(44,36,22,0.72)",
  textFaint: "rgba(44,36,22,0.28)",
  muted: "#8b8070", // warm paper secondary — use over textSecondary
  dim: "rgba(44,36,22,0.55)", // warm paper tertiary — use over textTertiary

  // ── Warm accents ──
  accent: "#c17d4b",
  accentLight: "#d4a854",
  accentBg: "rgba(193,125,75,0.10)",
  accentBorder: "rgba(193,125,75,0.28)",

  brand: "#c17d4b",
  brandLight: "#d4a854",
  brandBg: "rgba(193,125,75,0.08)",
  brandBorder: "rgba(193,125,75,0.25)",

  green: "#5a8a6a",
  yellow: "#d4a854",
  red: "#c17d4b",
  orangeRed: "#c17d4b",
  purple: "#9b7ec4",
  orange: "#d4a854",
  gray: "#b0a595",
  white: "#ffffff",

  surfaceSubtle: "rgba(44,36,22,0.03)",
  surfaceFaint: "rgba(44,36,22,0.04)",
  surfaceLow: "rgba(44,36,22,0.06)",
  surfaceMid: "rgba(44,36,22,0.08)",
  surfaceMed: "rgba(44,36,22,0.10)",

  borderSubtle: "rgba(44,36,22,0.06)",
  borderLow: "rgba(44,36,22,0.08)",
  borderMid: "rgba(44,36,22,0.15)",

  accentSurface: "rgba(193,125,75,0.08)",
  accentBorderSubtle: "rgba(193,125,75,0.15)",
  accentBorderMid: "rgba(193,125,75,0.22)",

  brandBorderSubtle: "rgba(193,125,75,0.22)",

  bgTint75: "rgba(254,252,248,0.75)",
  bgTint88: "rgba(254,252,248,0.88)",
  bgStroke: "rgba(254,252,248,0.6)",
  cardBg: "rgba(44,36,22,0.04)",
  background: "#fefcf8",
  border: "#e5ddd0",
  borderLight: "rgba(44,36,22,0.06)",
  textLight: "rgba(44,36,22,0.55)",
};

/** 1080p 参考布局值（运行时按实际尺寸缩放） */
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
  cardRadius: 20,
  panelRadius: 14,
  chipRadius: 10,
  cardPaddingX: 40,
  cardPaddingY: 32,
  contentMaxWidth: 960,
  contentWideMaxWidth: 1200,
  subtitleMaxWidth: 1216,
};

/** 1080p 参考字号（运行时按实际尺寸缩放） */
export const FS = {
  hero: 80,
  headline: 58,
  subhead: 40,
  closing: 72,

  body: 32,
  bodySmall: 26,
  bodyLg: 30,
  subtitle2: 26,

  label: 26,
  caption: 22,
  pill: 17,
  micro: 15,

  watermark: 85,
  watermarkLg: 113,
  subtitle: 40,
};

export interface DesignTokens {
  /** Scale a pixel value relative to current composition size (reference: 1920×1080) */
  scaled: (px: number) => number;
  layout: typeof LAYOUT;
  fs: typeof FS;
  grid: (units: number) => number;
  isCompactHeight: boolean;
  /** True when canvas height > width (e.g. 9:16 portrait) */
  isPortrait: boolean;
  getCardMaxHeight: number;
}

/** Build design tokens for a specific composition size */
function createDesignTokens(width: number, height: number): DesignTokens {
  const scale = Math.min(width / REF_WIDTH, height / REF_HEIGHT);
  const scaled = (px: number) => Math.round(px * scale);

  const isPortrait = height > width;
  const isCompactHeight = scale < 0.8;

  const getCardMaxHeight = isPortrait
    ? Math.round(height * 0.55)
    : Math.round(height * 0.78);

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
    hero: scaled(FS.hero),
    headline: scaled(FS.headline),
    subhead: scaled(FS.subhead),
    closing: scaled(FS.closing),
    body: scaled(FS.body),
    bodySmall: scaled(FS.bodySmall),
    bodyLg: scaled(FS.bodyLg),
    subtitle2: scaled(FS.subtitle2),
    label: scaled(FS.label),
    caption: scaled(FS.caption),
    pill: scaled(FS.pill),
    micro: scaled(FS.micro),
    watermark: scaled(FS.watermark),
    watermarkLg: scaled(FS.watermarkLg),
    subtitle: scaled(FS.subtitle),
  };

  return {
    scaled,
    layout,
    fs,
    grid: (units: number) => scaled(units * GRID_UNIT),
    isCompactHeight,
    isPortrait,
    getCardMaxHeight,
  };
}

/** 1080p fallback tokens (for non-Remotion contexts like tests) */
const _fallbackTokens: DesignTokens = createDesignTokens(REF_WIDTH, REF_HEIGHT);

/** 获取设计令牌 — 动态适配当前合成尺寸 */
export function useDesign(): DesignTokens {
  const config = useVideoConfig();
  return useMemo(
    () => createDesignTokens(config.width, config.height),
    [config.width, config.height],
  );
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
    accentBg: "rgba(155,126,196,0.10)",
    accentBorder: "rgba(155,126,196,0.28)",
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

/** 暖纸卡片样式 */
export const glassCard: React.CSSProperties = {
  background: COLORS.surface,
  border: `1px solid ${COLORS.borderLow}`,
  borderRadius: LAYOUT.cardRadius,
  backdropFilter: "blur(24px) saturate(1.2)",
  WebkitBackdropFilter: "blur(24px) saturate(1.2)",
};

export const glassCardShadow = `0 2px 16px rgba(44,36,22,0.08), 0 1px 3px rgba(44,36,22,0.04)`;

export const innerPanel: React.CSSProperties = {
  background: COLORS.surfaceFaint,
  border: `1px solid ${COLORS.borderLow}`,
  borderRadius: LAYOUT.panelRadius,
};

export const glassGlow = `0 0 32px rgba(193,125,75,0.06), 0 4px 16px rgba(44,36,22,0.08), 0 1px 4px rgba(44,36,22,0.04)`;

export const SHADOWS = {
  card: glassCardShadow,
  cardHover: "0 4px 20px rgba(44,36,22,0.10), 0 1px 6px rgba(44,36,22,0.06)",
};

/** 命名渐变 */
export const GRADIENTS = {
  brandBar: `linear-gradient(90deg, ${COLORS.brand}, ${COLORS.orange})`,
  accentFill: `linear-gradient(90deg, ${COLORS.accent}, ${COLORS.accentLight})`,
  shimmerSweep: `linear-gradient(105deg, transparent 40%, ${COLORS.surfaceLow} 48%, ${COLORS.surfaceLow} 52%, transparent 60%)`,
  divider: `linear-gradient(90deg, ${COLORS.brand}, ${COLORS.orange}99, transparent)`,
  subtitleMinimal: `linear-gradient(90deg, rgba(254,252,248,0), ${COLORS.bgTint75} 16%, ${COLORS.bgTint75} 84%, rgba(254,252,248,0))`,
  subtitleStandard: `linear-gradient(90deg, rgba(254,252,248,0), ${COLORS.bgTint88} 14%, ${COLORS.bgTint88} 86%, rgba(254,252,248,0))`,
  keywordTagBg: `rgba(193,125,75,0.08)`,
  dotGrid: `radial-gradient(circle, rgba(44,36,22,0.04) 1px, transparent 1px)`,
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
  width: 4,
  height: 18,
  borderRadius: 3,
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

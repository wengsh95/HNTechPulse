import React, { createContext, useContext, useMemo } from "react";
import { Easing, useVideoConfig } from "remotion";

/** Reference design dimensions (1080p landscape) — all pixel values below are relative to this */
const REF_WIDTH = 1920;
const REF_HEIGHT = 1080;

/**
 * 手机端字号放大系数 (B 站主战场)
 *
 * 视频输出 1920×1080,在 B 站手机端(竖屏)实际显示宽度约 380-420pt,
 * 缩放因子 ≈ 0.21。原始 FS.body=32 在手机端实际只有 ~6.7pt,
 * 远低于 iOS 11pt 的可读阈值,导致副文本(pill/caption/micro)几乎看不清。
 *
 * 把所有 fs 字段统一乘这个 boost,等价于"在视频里就把字做大",
 * 让手机端最终显示的字号回到可读区间。桌面端(全屏 1920×1080)
 * 字号会略大,密度下降,但在 1080p 全屏下仍可接受。
 *
 * 调这个常量即可全局调整;不要在卡片里单独硬编码。
 */
const MOBILE_FONT_BOOST = 1.3;

/** 文字上下文间距放大系数(比字号 boost 小,避免过度稀释密度) */
const MOBILE_GAP_BOOST = 1.15;

/** Keynote 风格暗色设计系统（基于 1080p 参考值，运行时按实际分辨率缩放） */

export const FONTS = {
  mono: '"JetBrains Mono", "SF Mono", "Menlo", "Source Code Pro", monospace',
  sans: '"PingFang SC", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", "Source Han Sans SC", sans-serif',
  bold: '"PingFang SC", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", "Source Han Sans SC", sans-serif',
  /** 衬线字体 (品牌名/章节标签/大标题), 与模板对齐：Fraunces 优先，中文回退思源宋体 */
  serif:
    '"Fraunces", "Source Han Serif SC", "Noto Serif SC", "Songti SC", "STSong", Georgia, "Times New Roman", serif',
  /** 装饰字体 (大字), 衬线加粗，与模板对齐 */
  serifBold:
    '"Fraunces", "Source Han Serif SC", "Noto Serif SC", "Songti SC", "STSong", Georgia, "Times New Roman", serif',
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
  // ── Warm paper canvas (aligned to template tokens.css) ──
  bg: "#fbf4e8",
  surface: "rgba(32,25,20,0.04)",
  surfaceHover: "rgba(32,25,20,0.07)",
  surfaceBorder: "rgba(32,25,20,0.10)",
  surface2: "#f5eadb", // --color-panel-warm

  text: "#201914", // --color-ink
  fg: "#201914",
  textSecondary: "rgba(32,25,20,0.65)",
  textTertiary: "rgba(32,25,20,0.42)",
  textBody: "rgba(32,25,20,0.88)",
  textDim: "rgba(32,25,20,0.72)",
  textFaint: "rgba(32,25,20,0.28)",
  muted: "#7d7062", // --color-ink-muted
  dim: "rgba(32,25,20,0.55)",
  inkSoft: "#4d4238", // --color-ink-soft
  inkFaint: "#a39482", // --color-ink-faint

  // ── HN Orange accents (aligned to template) ──
  accent: "#ff6600",
  accentLight: "#b64a12", // --color-brand-deep
  accentBg: "rgba(255,102,0,0.10)",
  accentBorder: "rgba(255,102,0,0.28)",

  brand: "#ff6600", // --color-brand
  brandLight: "#b64a12",
  brandBg: "rgba(255,102,0,0.08)",
  brandBorder: "rgba(255,102,0,0.25)",
  brandDeep: "#b64a12",
  brandSoft: "#ffe0c7", // --color-brand-soft

  warmBrown: "#ff6600",
  warmGold: "#b64a12",
  sage: "#4f8761",

  brownBg: "#ffe0c7", // brand-soft light bg for pills
  goldBg: "#faf3e0",
  sageBg: "#e8f0e5",

  green: "#4f8761", // --color-green (stance support)
  yellow: "#c69230", // --color-amber (stance skeptical)
  red: "#ff6600",
  orangeRed: "#ff6600",
  purple: "#9b7ec4",
  orange: "#ff6600",
  gray: "#8a8075", // --color-gray (stance neutral)
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
  border: "rgba(32,25,20,0.10)", // --color-border
  borderStrong: "rgba(32,25,20,0.18)", // --color-border-strong
  borderLight: "rgba(32,25,20,0.06)",
  textLight: "rgba(32,25,20,0.55)",

  // ── Panel colors ──
  paper: "#fffaf2", // --color-paper
  panel: "#fffdf8", // --color-panel
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
  isCompactHeight: boolean;
  /** True when canvas height > width (e.g. 9:16 portrait) */
  isPortrait: boolean;
  getCardMaxHeight: number;
}

/** Build design tokens for a specific composition size */
function createDesignTokens(width: number, height: number): DesignTokens {
  const scale = Math.min(width / REF_WIDTH, height / REF_HEIGHT);
  const scaled = (px: number) => Math.round(px * scale);
  // 字号专用:全量乘 MOBILE_FONT_BOOST 解决 B 站手机端字号过小
  const fsScaled = (px: number) => Math.round(px * scale * MOBILE_FONT_BOOST);
  // 间距专用:同步放大(系数小于字号,避免内容布局过度稀释)
  const gapScaled = (px: number) => Math.round(px * scale * MOBILE_GAP_BOOST);

  const isPortrait = height > width;
  const isCompactHeight = scale < 0.8;

  const getCardMaxHeight = isPortrait ? Math.round(height * 0.55) : Math.round(height * 0.78);

  const layout: typeof LAYOUT = {
    pageInset: gapScaled(LAYOUT.pageInset),
    topInset: gapScaled(LAYOUT.topInset),
    bottomSafe: gapScaled(LAYOUT.bottomSafe),
    chromeInsetX: gapScaled(LAYOUT.chromeInsetX),
    chromeTop: gapScaled(LAYOUT.chromeTop),
    chromeHeight: gapScaled(LAYOUT.chromeHeight),
    progressInsetX: gapScaled(LAYOUT.progressInsetX),
    progressBottom: gapScaled(LAYOUT.progressBottom),
    subtitleBottom: gapScaled(LAYOUT.subtitleBottom),
    subtitleBottomMinimal: gapScaled(LAYOUT.subtitleBottomMinimal),
    cardRadius: scaled(LAYOUT.cardRadius),
    panelRadius: scaled(LAYOUT.panelRadius),
    chipRadius: scaled(LAYOUT.chipRadius),
    cardPaddingX: gapScaled(LAYOUT.cardPaddingX),
    cardPaddingY: gapScaled(LAYOUT.cardPaddingY),
    contentMaxWidth: gapScaled(LAYOUT.contentMaxWidth),
    contentWideMaxWidth: gapScaled(LAYOUT.contentWideMaxWidth),
    subtitleMaxWidth: gapScaled(LAYOUT.subtitleMaxWidth),
  };

  const fs: typeof FS = {
    hero: fsScaled(FS.hero),
    headline: fsScaled(FS.headline),
    subhead: fsScaled(FS.subhead),
    closing: fsScaled(FS.closing),
    body: fsScaled(FS.body),
    bodySmall: fsScaled(FS.bodySmall),
    bodyLg: fsScaled(FS.bodyLg),
    subtitle2: fsScaled(FS.subtitle2),
    label: fsScaled(FS.label),
    caption: fsScaled(FS.caption),
    pill: fsScaled(FS.pill),
    micro: fsScaled(FS.micro),
    watermark: fsScaled(FS.watermark),
    watermarkLg: fsScaled(FS.watermarkLg),
    subtitle: fsScaled(FS.subtitle),
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

/** 1080p fallback tokens (for non-Remotion contexts like tests) */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
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
    accent: "#9b7ec4",
    accentLight: "#9b7ec4",
    accentBg: "rgba(155,126,196,0.10)",
    accentBorder: "rgba(155,126,196,0.28)",
    labelText: "#9b7ec4",
    motion: "countUp",
    viz: "pieChart",
  },
  closing: {
    accent: COLORS.brand,
    accentLight: COLORS.brandLight,
    accentBg: COLORS.brandBg,
    accentBorder: COLORS.brandBorderSubtle,
    labelText: COLORS.brandLight,
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
export const glassCardShadow = `0 2px 16px rgba(32,25,20,0.08), 0 1px 3px rgba(32,25,20,0.04)`;

export const glassGlow = `0 0 32px rgba(255,102,0,0.06), 0 4px 16px rgba(32,25,20,0.08), 0 1px 4px rgba(32,25,20,0.04)`;

/** 命名渐变 */
export const GRADIENTS = {
  brandBar: `linear-gradient(90deg, ${COLORS.brand}, ${COLORS.brand})`,
  accentFill: `linear-gradient(90deg, ${COLORS.accent}, ${COLORS.accentLight})`,
  shimmerSweep: `linear-gradient(105deg, transparent 40%, ${COLORS.surfaceLow} 48%, ${COLORS.surfaceLow} 52%, transparent 60%)`,
  divider: `linear-gradient(90deg, ${COLORS.brand}, transparent)`,
  subtitleMinimal: `linear-gradient(90deg, rgba(251,244,232,0), ${COLORS.bgTint75} 16%, ${COLORS.bgTint75} 84%, rgba(251,244,232,0))`,
  subtitleStandard: `linear-gradient(90deg, rgba(251,244,232,0), ${COLORS.bgTint88} 14%, ${COLORS.bgTint88} 86%, rgba(251,244,232,0))`,
  keywordTagBg: `rgba(255,102,0,0.08)`,
  dotGrid: `radial-gradient(circle, rgba(32,25,20,0.04) 1px, transparent 1px)`,
} as const;

export const S: React.CSSProperties = { position: "absolute" as const };

/** Card reference dimensions (1080p) */
export const CARD_REF = {
  width: 1920,
  height: 1080,
} as const;

/** Standard card padding (px values, scaled at runtime via d.scaled) */
export const CARD_PAD = {
  xNormal: 56,
  xCompact: 40,
  yNormal: 56,
  yCompact: 36,
} as const;

/**
 * 统一卡片布局令牌 (Unified Card Layout Tokens)
 *
 * 所有卡片共用的布局参数，确保视觉一致性。
 * 所有值均为 1080p 参考值，运行时通过 d.scaled() 缩放。
 */
export const CARD_LAYOUT = {
  /** 卡片内边距 (对齐模板: 1280→1920, 1.5×) */
  padding: {
    top: 64,
    bottom: 160, // 对齐模板 --card-safe-bottom: 112px → 168px
    left: 70, // 对齐模板 --card-padding-x: 46px → 69px
    right: 70,
  },

  /** Header 区域（品牌名 + live-dot + 日期） */
  header: {
    height: 48,
    marginBottom: 16,
    fontSize: 18,
    color: COLORS.dim,
  },

  /** 页码水印 */
  watermark: {
    top: 64,
    right: 70,
    fontSize: 113,
  },

  /** 音频波形 */
  waveform: {
    bottom: 20,
  },

  /** 渐变分隔线 (对齐模板 card::after: bottom = safe-bottom - 34px) */
  divider: {
    height: 2,
    maxWidth: 900,
    borderRadius: 1,
  },

  /** 内容区最大宽度 */
  content: {
    maxWidth: 1400,
    wideMaxWidth: 1600,
  },
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

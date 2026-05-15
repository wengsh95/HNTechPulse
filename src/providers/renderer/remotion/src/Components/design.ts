import React from "react";

/** Keynote 风格暗色设计系统 */
export const GRID_UNIT = 8;
export const grid = (units: number) => units * GRID_UNIT;
export const snapToGrid = (value: number) => Math.round(value / GRID_UNIT) * GRID_UNIT;

export const FONTS = {
  mono: '"SF Mono", "Menlo", "Source Code Pro", monospace',
  sans: '"Inter", "Noto Sans SC", -apple-system, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif',
  bold: '"Inter", "Noto Sans SC", -apple-system, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif',
};

/** 标准字重 — 仅使用这些值以保证渲染一致性 */
export const FW = {
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
  heavy: 800,
} as const;

export const COLORS = {
  // 暗色主题背景
  bg: "#0d0d0f",
  surface: "rgba(255,255,255,0.06)",
  surfaceHover: "rgba(255,255,255,0.10)",
  surfaceBorder: "transparent",

  // 文字层级 — 暗底白字
  text: "#f5f5f7",
  textSecondary: "rgba(245,245,247,0.60)",
  textTertiary: "rgba(245,245,247,0.38)",

  // 主强调色 — Apple 蓝
  accent: "#007AFF",
  accentLight: "#4DA6FF",
  accentBg: "rgba(0, 122, 255, 0.12)",
  accentBorder: "rgba(0, 122, 255, 0.35)",

  // 品牌色 — HN 橙（辅助）
  brand: "#ff6600",
  brandLight: "#ff8b36",
  brandBg: "rgba(255, 102, 0, 0.10)",
  brandBorder: "rgba(255, 102, 0, 0.30)",

  // 语义色 — Apple 暗底系统色
  green: "#34C759",
  yellow: "#FFD60A",
  red: "#FF453A",
  orangeRed: "#FF5A5F",
  purple: "#BF5AF2",
  orange: "#FF9F0A",
  gray: "#8E8E93",
  white: "#ffffff",

  // 文字变体 — text/secondary/tertiary 之间的中间透明度
  textBody: "rgba(245,245,247,0.85)", // 摘要、要点正文
  textDim: "rgba(245,245,247,0.70)", // 次级文字
  textFaint: "rgba(255,255,255,0.22)", // 微弱文字（如投票数）

  // 表面变体 — 内面板、图片容器等
  surfaceSubtle: "rgba(255,255,255,0.03)", // 最淡表面
  surfaceFaint: "rgba(255,255,255,0.04)", // 淡表面
  surfaceLow: "rgba(255,255,255,0.08)", // 低透明度表面
  surfaceMid: "rgba(255,255,255,0.10)", // 中透明度表面
  surfaceMed: "rgba(255,255,255,0.12)", // 中高透明度表面

  // 边框变体
  borderSubtle: "rgba(255,255,255,0.07)", // 极淡边框
  borderLow: "rgba(255,255,255,0.08)", // 淡边框
  borderMid: "rgba(255,255,255,0.18)", // 中等边框

  // 强调色表面/边框（非标准透明度）
  accentSurface: "rgba(0,122,255,0.10)", // 关键词标签背景
  accentBorderSubtle: "rgba(0,122,255,0.18)", // 关键词标签边框
  accentBorderMid: "rgba(0,122,255,0.25)", // 章节指示器边框

  // 品牌色边框（非标准透明度）
  brandBorderSubtle: "rgba(255,102,0,0.25)", // 胶囊边框

  // 背景色变体 — 字幕条等
  bgTint75: "rgba(13,13,15,0.75)", // 字幕条 minimal 模式
  bgTint88: "rgba(13,13,15,0.88)", // 字幕条 standard 模式
  bgStroke: "rgba(13,13,15,0.6)", // 饼图描边

  // 遗留色（保留以减少 diff；部分可能仍被引用）
  dim: "rgba(245,245,247,0.60)",
  cardBg: "rgba(255,255,255,0.06)",
  background: "#0d0d0f",
  border: "transparent",
  borderLight: "rgba(255,255,255,0.06)",
  textLight: "rgba(245,245,247,0.60)",
};

export const LAYOUT = {
  pageInset: grid(10), // 页面左右内边距
  topInset: grid(10), // 顶部内边距
  bottomSafe: grid(15), // 底部安全区
  chromeInsetX: grid(5), // 顶栏左右内边距
  chromeTop: grid(4), // 顶栏顶部偏移
  chromeHeight: grid(4), // 顶栏高度
  progressInsetX: grid(3), // 进度条左右内边距
  progressBottom: grid(1), // 进度条底部偏移
  subtitleBottom: grid(7), // 字幕底部偏移（标准）
  subtitleBottomMinimal: grid(6), // 字幕底部偏移（精简）
  cardRadius: 14, // 卡片圆角
  panelRadius: 10, // 面板圆角
  chipRadius: 6, // 标签圆角
  cardPaddingX: grid(4), // 卡片水平内边距
  cardPaddingY: grid(3), // 卡片垂直内边距
  contentMaxWidth: grid(102), // 内容最大宽度
  contentWideMaxWidth: grid(128), // 宽内容最大宽度
  subtitleMaxWidth: grid(130), // 字幕最大宽度
};

export const getCardMaxHeight = (height: number) =>
  Math.max(grid(40), height - LAYOUT.topInset - LAYOUT.bottomSafe);

export const isCompactHeight = (height: number) => height <= 760;

export const GRID_DEBUG = {
  unit: GRID_UNIT,
  major: grid(4),
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

/** 命名渐变 — 所有渐变字符串的唯一来源 */
export const GRADIENTS = {
  brandBar: `linear-gradient(90deg, ${COLORS.brand}, ${COLORS.orange})`, // 品牌底条
  accentFill: `linear-gradient(90deg, ${COLORS.accent}, ${COLORS.accentLight})`, // 进度条填充
  // 扫光效果
  shimmerSweep: `linear-gradient(105deg, transparent 40%, ${COLORS.surfaceLow} 48%, ${COLORS.surfaceLow} 52%, transparent 60%)`,
  divider: `linear-gradient(90deg, ${COLORS.surfaceMid} 0%, ${COLORS.surfaceFaint} 100%)`, // 分隔线
  subtitleMinimal: `linear-gradient(90deg, rgba(13,13,15,0), ${COLORS.bgTint75} 16%, ${COLORS.bgTint75} 84%, rgba(13,13,15,0))`, // 字幕条精简模式
  subtitleStandard: `linear-gradient(90deg, rgba(13,13,15,0), ${COLORS.bgTint88} 14%, ${COLORS.bgTint88} 86%, rgba(13,13,15,0))`, // 字幕条标准模式
  keywordTagBg: `rgba(0,122,255,0.10)`, // 关键词标签背景
  dotGrid: `radial-gradient(circle, ${COLORS.surfaceSubtle} 1px, transparent 1px)`, // 微网格背景
} as const;

/** 语义字号 — 仅使用这些值以保证排版一致性 */
export const FS = {
  // 标题层级
  hero: 52, // CoverCard 主标题
  headline: 38, // EventCard / AtmosphereCard 主标题
  subhead: 28, // CoverCard 条目标题
  closing: 56, // ClosingCard 品牌名

  // 正文
  body: 20, // 摘要、引言正文
  bodySmall: 16, // 紧凑模式正文
  bodyLg: 18, // CoverCard "为何重要" 行
  subtitle2: 16, // 英文副标题、辅助信息

  // 辅助
  label: 16, // SectionLabel、InfoPoint 标签、FocusPoint 序号
  caption: 16, // 徽章、标签、顶栏文字、分类胶囊
  pill: 11, // 小胶囊文字（EventCard 分类）
  micro: 10, // 最小文字（投票数、KeywordTags）

  // 特殊
  watermark: 64, // 章节水印（EventCard）
  watermarkLg: 84, // 大水印（CoverCard）
  subtitle: 22, // 底部字幕条
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

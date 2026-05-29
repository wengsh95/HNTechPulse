import React from "react";
import { interpolate, Easing } from "remotion";

import {
  COLORS,
  FONTS,
  FW,
  useDesign,
  useChapterTone,
  GRADIENTS,
  ANIM,
  EASE_CARD,
  CARD_PAD,
  HEADER_MARGIN,
  TITLE_BODY_GAP,
  BODY_SECTION_GAP,
  DIVIDER_MARGIN,
  KEYWORD_GAP,
  CARD_ENTRANCE_Y,
  TITLE_ENTRANCE_Y,
  BODY_ENTRANCE_Y,
  HEADER_ENTRANCE_Y,
  FOOTER_ENTRANCE_Y,
  IMAGE_ENTRANCE_X,
  WATERMARK_TOP_OFFSET,
  ITEM_DURATION,
  PILL_DURATION,
  SECTION_BAR,
  PILL_RADIUS,
  METRIC_PILL_HEIGHT,
  METRIC_PILL_PAD_X,
  HERO_ENTRANCE_Y,
  CLOSING_QUESTION_ENTRANCE_Y,
  CLOSING_BRAND_ENTRANCE_Y,
  IMAGE_PANEL_RADIUS,
  IMAGE_PANEL_SHADOW,
  IMAGE_PANEL_BORDER,
  IMAGE_PANEL_BG,
  ROW_STAGGER,
  KEYWORD_TAG_PAD,
  CAPSULE_PAD,
} from "./design";

// Re-export design constants so cards can import them from HighlightShared
export {
  CARD_ENTRANCE_Y,
  TITLE_ENTRANCE_Y,
  BODY_ENTRANCE_Y,
  HEADER_ENTRANCE_Y,
  FOOTER_ENTRANCE_Y,
  IMAGE_ENTRANCE_X,
  ITEM_DURATION,
  PILL_DURATION,
  SECTION_BAR,
  PILL_RADIUS,
  METRIC_PILL_HEIGHT,
  METRIC_PILL_PAD_X,
  HERO_ENTRANCE_Y,
  CLOSING_QUESTION_ENTRANCE_Y,
  CLOSING_BRAND_ENTRANCE_Y,
  IMAGE_PANEL_RADIUS,
  IMAGE_PANEL_SHADOW,
  IMAGE_PANEL_BORDER,
  IMAGE_PANEL_BG,
  ROW_STAGGER,
  KEYWORD_TAG_PAD,
  CAPSULE_PAD,
} from "./design";

export interface HighlightEntry {
  original_title?: string;
  score?: number;
  comment_count?: number;
  editor_angle?: string;
}

export const medalSets = [
  { text: "#B8A03A", bg: "rgba(184,160,58,0.12)", ring: "rgba(184,160,58,0.30)" },
  { text: "#9A9AA3", bg: "rgba(154,154,163,0.10)", ring: "rgba(154,154,163,0.22)" },
  { text: "#B87A3A", bg: "rgba(184,122,58,0.10)", ring: "rgba(184,122,58,0.25)" },
];

export const MedalBadge: React.FC<{
  rank: number;
  size?: number;
  fontSize?: number;
}> = ({ rank, size = 28, fontSize }) => {
  const { fs, scaled } = useDesign();
  const resolvedFontSize = fontSize ?? fs.label;
  const isTop3 = rank <= 3;
  const medal = isTop3 ? medalSets[rank - 1] : null;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: scaled(6),
        width: size,
      }}
    >
      {/* Rank badge */}
      <div
        style={{
          width: size,
          height: size,
          borderRadius: size * 0.25,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: isTop3 ? medal!.bg : COLORS.surfaceFaint,
          border: `1.5px solid ${isTop3 ? medal!.ring : COLORS.borderLow}`,
        }}
      >
        <span
          style={{
            fontFamily: FONTS.mono,
            fontSize: resolvedFontSize,
            fontWeight: isTop3 ? FW.bold : FW.medium,
            color: isTop3 ? medal!.text : COLORS.textTertiary,
            lineHeight: 1,
            letterSpacing: -0.5,
          }}
        >
          {String(rank).padStart(2, "0")}
        </span>
      </div>
    </div>
  );
};

export const PageIndicator: React.FC<{
  pages: unknown[][];
  currentPage: number;
}> = ({ pages, currentPage }) => {
  const { scaled } = useDesign();
  return (
    <div
      style={{ display: "flex", justifyContent: "center", gap: scaled(8), marginTop: scaled(16) }}
    >
      {pages.map((_, pi) => (
        <div
          key={pi}
          style={{
            width: pi === currentPage ? scaled(24) : scaled(8),
            height: scaled(8),
            borderRadius: scaled(4),
            backgroundColor: pi === currentPage ? COLORS.accent : COLORS.surfaceMed,
          }}
        />
      ))}
    </div>
  );
};

export const CategoryBadge: React.FC<{
  category: string;
  maxWidth?: number;
}> = ({ category, maxWidth = 120 }) => {
  const { fs, scaled } = useDesign();
  return (
    <div
      style={{
        fontFamily: FONTS.sans,
        fontSize: fs.caption,
        fontWeight: 700,
        color: COLORS.accentLight,
        backgroundColor: COLORS.accentBg,
        borderRadius: scaled(6),
        padding: `${scaled(5)}px ${scaled(10)}px`,
        maxWidth,
        overflow: "hidden",
        whiteSpace: "nowrap",
        textOverflow: "ellipsis",
      }}
    >
      {category}
    </div>
  );
};

export const KeywordTags: React.FC<{
  keywords: string[];
  max?: number;
  maxWidth?: number;
}> = ({ keywords, max = 2, maxWidth = 46 }) => {
  const { fs, scaled } = useDesign();
  return (
    <div style={{ display: "flex", gap: scaled(5) }}>
      {keywords.slice(0, max).map((kw) => (
        <span
          key={kw}
          style={{
            fontFamily: FONTS.sans,
            fontSize: fs.micro,
            color: COLORS.textTertiary,
            maxWidth,
            overflow: "hidden",
            whiteSpace: "nowrap",
            textOverflow: "ellipsis",
          }}
        >
          {kw}
        </span>
      ))}
    </div>
  );
};

export const rowEntryAnimation = (
  frame: number,
  rowStart: number,
  duration: number = ANIM.rowDuration,
) =>
  interpolate(frame, [rowStart, rowStart + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_CARD,
  });

// ── Shared sub-components (extracted from EventCard for reuse) ──

export function lineClamp(lines: number): React.CSSProperties {
  return {
    overflow: "hidden",
    display: "-webkit-box",
    WebkitLineClamp: lines,
    WebkitBoxOrient: "vertical" as const,
  };
}

// ── Rolling number animation ──

export const RollingNumber: React.FC<{
  value: number;
  delay: number;
  frame: number;
  fontSize?: number;
  fontWeight?: number;
  color?: string;
  lineHeight?: number;
}> = ({ value, delay, frame, fontSize, fontWeight, color, lineHeight }) => {
  const rolled = Math.round(
    interpolate(frame, [delay, delay + 20], [0, value], {
      easing: Easing.out(Easing.cubic),
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }),
  );

  return (
    <span
      style={{
        fontSize,
        fontWeight,
        color,
        lineHeight,
      }}
    >
      {Math.max(0, rolled).toLocaleString("en-US")}
    </span>
  );
};

export function highlightKeywords(
  text: string,
  keywords: string[],
  frame?: number,
  delay?: number,
): React.ReactNode {
  if (!text || keywords.length === 0) return text;
  const escaped = keywords
    .filter((k) => k.length > 1)
    .map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .sort((a, b) => b.length - a.length);
  if (escaped.length === 0) return text;
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(pattern);
  if (parts.length <= 1) return text;
  return parts.map((part, i) => {
    const isMatch = keywords.some((k) => k.toLowerCase() === part.toLowerCase());
    if (isMatch) {
      const animatedBg =
        frame !== undefined && delay !== undefined
          ? `rgba(0, 122, 255, ${interpolate(frame, [delay, delay + 16], [0, 0.15], {
              easing: EASE_CARD,
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            })})`
          : undefined;
      return (
        <span
          key={i}
          style={{
            color: COLORS.accentLight,
            fontWeight: FW.semibold,
            ...(animatedBg !== undefined
              ? { backgroundColor: animatedBg, borderRadius: 3, padding: "0 2px" }
              : {}),
          }}
        >
          {part}
        </span>
      );
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}

const SECTION_VARIANTS = {
  default: { bar: COLORS.accent, text: COLORS.textSecondary },
  brand: { bar: COLORS.brand, text: COLORS.brandLight },
  success: { bar: COLORS.green, text: COLORS.green },
} as const;

export const SectionLabel: React.FC<{
  text: string;
  delay: number;
  frame: number;
  /** 显式指定配色变体；未指定时使用 ChapterProvider 注入的章节色 */
  variant?: keyof typeof SECTION_VARIANTS;
}> = ({ text, delay, frame, variant }) => {
  const progress = interpolate(frame, [delay, delay + ANIM.sectionLabelDuration], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const { fs, scaled } = useDesign();
  const tone = useChapterTone();
  const theme = variant ? SECTION_VARIANTS[variant] : { bar: tone.accent, text: tone.labelText };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: scaled(8),
        marginBottom: scaled(12),
        opacity: progress,
        transform: `translateX(${interpolate(progress, [0, 1], [-scaled(6), 0])}px)`,
      }}
    >
      <div
        style={{
          width: SECTION_BAR.width,
          height: SECTION_BAR.height,
          borderRadius: SECTION_BAR.borderRadius,
          background: theme.bar,
          flexShrink: 0,
        }}
      />
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: fs.bodySmall,
          fontWeight: FW.semibold,
          color: theme.text,
          letterSpacing: 0.4,
        }}
      >
        {text}
      </span>
    </div>
  );
};

export const MetricPill: React.FC<{
  icon: string;
  value: number;
  delay: number;
  frame: number;
}> = ({ icon, value, delay, frame }) => {
  const progress = interpolate(frame, [delay, delay + ANIM.sectionLabelDuration], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const pulse = audioPulse(frame);
  const { fs, scaled } = useDesign();

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: scaled(5),
        height: scaled(METRIC_PILL_HEIGHT),
        padding: `0 ${scaled(METRIC_PILL_PAD_X)}px`,
        borderRadius: scaled(METRIC_PILL_HEIGHT / 2),
        backgroundColor: COLORS.surfaceFaint,
        border: `1px solid ${COLORS.borderSubtle}`,
        boxSizing: "border-box",
        fontFamily: FONTS.mono,
        whiteSpace: "nowrap",
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [FOOTER_ENTRANCE_Y, 0])}px) scale(${1 + pulse * 0.03})`,
      }}
    >
      <span
        style={{ fontSize: fs.label, lineHeight: 1, display: "inline-flex", alignItems: "center" }}
      >
        {icon}
      </span>
      <RollingNumber
        value={value}
        delay={delay}
        frame={frame}
        fontSize={fs.label}
        fontWeight={FW.heavy}
        color={COLORS.textSecondary}
        lineHeight={1}
      />
    </div>
  );
};

export const KeywordTag: React.FC<{
  keyword: string;
  delay: number;
  frame: number;
}> = ({ keyword, delay, frame }) => {
  const tagProgress = interpolate(frame, [delay, delay + 16], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const pulse = audioPulse(frame);
  const { fs } = useDesign();
  const tone = useChapterTone();

  return (
    <span
      style={{
        fontFamily: FONTS.sans,
        fontSize: fs.caption,
        fontWeight: FW.semibold,
        color: tone.accentLight,
        backgroundColor: tone.accentBg,
        border: `1px solid ${tone.accentBorder}`,
        borderRadius: PILL_RADIUS,
        padding: `${KEYWORD_TAG_PAD.y}px ${KEYWORD_TAG_PAD.x}px`,
        letterSpacing: 0.2,
        opacity: tagProgress * (0.95 + pulse * 0.05),
        transform: `scale(${interpolate(tagProgress, [0, 1], [0.85, 1])})`,
      }}
    >
      {keyword}
    </span>
  );
};

// ── Elastic overshoot for card entrance ──

/**
 * Computes a translateY value with subtle elastic overshoot for card entrance.
 * The card slides from `fromY` to 0, overshooting by `overshootPx` at ~85%
 * progress, then settling back to 0 at 100% progress.
 */
export function overshootTranslateY(
  progress: number,
  fromY: number,
  overshootPx: number = 2,
): number {
  return interpolate(progress, [0, 0.85, 1], [fromY, -overshootPx, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

// ── Simulated audio-reactive pulse ──

/**
 * Returns a 0-1 value simulating a bass pulse using multiple sine frequencies.
 * Creates an organic, music-like rhythm without requiring actual audio data.
 * Use for subtle scale/opacity effects that make badges feel "alive".
 */
export function audioPulse(frame: number): number {
  const raw =
    0.5 +
    0.3 * Math.sin(frame * 0.15) +
    0.2 * Math.sin(frame * 0.37) +
    0.1 * Math.sin(frame * 0.73);
  // Normalize from [-0.1, 1.1] to [0, 1]
  return (raw + 0.1) / 1.2;
}

// ── Breathing glow helper ──

/**
 * Oscillates opacity between 0.02 and 0.06 (centered on 0.04)
 * with a period of ~3 seconds (90 frames at 30fps).
 * Use for watermark numbers that should feel "alive" not "pulsing".
 */
export function breathingOpacity(frame: number): number {
  const speed = (2 * Math.PI) / 90; // ~3 second period at 30fps
  return 0.04 + 0.02 * Math.sin(frame * speed);
}

// ── Glass shimmer sweep ──

export const GlassShimmer: React.FC<{
  frame: number;
  /** Frame when shimmer sweep starts (default 10) */
  startFrame?: number;
  /** Frame when shimmer sweep ends (default 40) */
  endFrame?: number;
}> = ({ frame, startFrame = 10, endFrame = 40 }) => {
  const progress = interpolate(frame, [startFrame, endFrame], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Fade in quickly at start, fade out quickly at end
  const opacity = interpolate(progress, [0, 0.1, 0.9, 1], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Translate from left (-100%) to right (+100%)
  const translateX = interpolate(progress, [0, 1], [-100, 100]);

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        overflow: "hidden",
        pointerEvents: "none",
        zIndex: 0,
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          transform: `translateX(${translateX}%)`,
          background: GRADIENTS.shimmerSweep,
          opacity,
        }}
      />
    </div>
  );
};

export const CapsuleBadge: React.FC<{
  text: string;
}> = ({ text }) => {
  const { fs } = useDesign();
  const tone = useChapterTone();
  return (
    <span
      style={{
        fontFamily: FONTS.sans,
        fontSize: fs.caption,
        fontWeight: FW.heavy,
        color: tone.accent,
        backgroundColor: tone.accentBg,
        border: "1px solid " + tone.accentBorder,
        borderRadius: PILL_RADIUS,
        padding: `${CAPSULE_PAD.y}px ${CAPSULE_PAD.x}px`,
        letterSpacing: 0.3,
      }}
    >
      {text}
    </span>
  );
};

export const dividerStyle: React.CSSProperties = {
  width: "100%",
  height: 1,
  background: GRADIENTS.divider,
  marginTop: DIVIDER_MARGIN.top,
  marginBottom: DIVIDER_MARGIN.bottom,
};

// ── Unified card shell helpers ──

/** Compute standard card padding based on compact mode */
export function useCardPad(compact: boolean) {
  const d = useDesign();
  return {
    padX: d.scaled(compact ? CARD_PAD.xCompact : CARD_PAD.xNormal),
    padY: d.scaled(compact ? CARD_PAD.yCompact : CARD_PAD.yNormal),
  };
}

/** Standard card animation progress hooks */
export function useCardAnimations(frame: number) {
  const cardProgress = interpolate(frame, [ANIM.cardStart, ANIM.cardEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleProgress = interpolate(frame, [ANIM.titleStart, ANIM.titleEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyProgress = interpolate(frame, [ANIM.bodyStart, ANIM.bodyEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const imageProgress = interpolate(frame, [ANIM.imageStart, ANIM.imageEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const footerProgress = interpolate(frame, [ANIM.footerStart, ANIM.footerEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return { cardProgress, titleProgress, bodyProgress, imageProgress, footerProgress };
}

/** Standard header margin-bottom */
export function headerMargin(compact: boolean): number {
  return compact ? HEADER_MARGIN.compact : HEADER_MARGIN.normal;
}

/** Standard title → body gap */
export function titleBodyGap(compact: boolean): number {
  return compact ? TITLE_BODY_GAP.compact : TITLE_BODY_GAP.normal;
}

/** Standard body section gap */
export function bodySectionGap(compact: boolean): number {
  return compact ? BODY_SECTION_GAP.compact : BODY_SECTION_GAP.normal;
}

/** Resolve title font size */
export function titleFontSize(d: ReturnType<typeof useDesign>): number {
  return d.fs.headline;
}

/** Resolve hero font size */
export function heroFontSize(d: ReturnType<typeof useDesign>): number {
  return d.fs.hero;
}

/** Resolve subhead font size */
export function subheadFontSize(d: ReturnType<typeof useDesign>): number {
  return d.fs.subhead;
}

/** Resolve focus card title font size */
export function focusTitleFontSize(d: ReturnType<typeof useDesign>): number {
  return d.fs.headline;
}

/** Shared chapter watermark component */
export const ChapterWatermark: React.FC<{
  displayIndex: number;
  storyCount: number;
  padX: number;
  padY: number;
  frame: number;
}> = ({ displayIndex, storyCount, padX, padY, frame }) => {
  const d = useDesign();
  return (
    <div
      style={{
        position: "absolute",
        right: padX,
        top: padY - d.scaled(WATERMARK_TOP_OFFSET),
        fontFamily: FONTS.mono,
        fontSize: d.fs.watermark,
        fontWeight: FW.heavy,
        color: `rgba(255,255,255,${breathingOpacity(frame)})`,
        lineHeight: 1,
        pointerEvents: "none",
        letterSpacing: -4,
        zIndex: 0,
      }}
    >
      {String(displayIndex).padStart(2, "0")}/{String(storyCount).padStart(2, "0")}
    </div>
  );
};

/** Shared card header row with CapsuleBadge */
export const CardHeader: React.FC<{
  badgeText: string;
  compact: boolean;
  maxWidth: number;
  progress: number;
}> = ({ badgeText, compact, maxWidth, progress }) => {
  const { scaled } = useDesign();
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: scaled(8),
        marginBottom: headerMargin(compact),
        maxWidth,
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [HEADER_ENTRANCE_Y, 0])}px)`,
      }}
    >
      <CapsuleBadge text={badgeText} />
    </div>
  );
};

/** Shared keywords footer row */
export const CardKeywordsFooter: React.FC<{
  keywords: string[];
  progress: number;
  frame: number;
  delayBase?: number;
}> = ({ keywords, progress, frame, delayBase = 20 }) => (
  <div
    style={{
      display: "flex",
      flexWrap: "wrap",
      justifyContent: "flex-start",
      gap: KEYWORD_GAP,
      opacity: progress,
    }}
  >
    {keywords.map((kw, i) => (
      <KeywordTag key={kw} keyword={kw} delay={delayBase + i * 4} frame={frame} />
    ))}
  </div>
);

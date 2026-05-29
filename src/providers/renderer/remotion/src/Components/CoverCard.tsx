import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { ElementProps, p } from "./utils";
import {
  CHAPTERS,
  COLORS,
  FONTS,
  FW,
  useDesign,
  glassCard,
  glassCardShadow,
  S,
  GRADIENTS,
} from "./design";
import {
  GlassShimmer,
  HighlightEntry,
  MedalBadge,
  MetricPill,
  overshootTranslateY,
  rowEntryAnimation,
  SectionLabel,
  useCardPad,
  useCardAnimations,
  heroFontSize,
  subheadFontSize,
  CARD_ENTRANCE_Y,
  HERO_ENTRANCE_Y,
  ROW_STAGGER,
} from "./HighlightShared";

const COVER_SUBTITLE_COLOR = COLORS.textSecondary;

type SectionCounts = {
  focus?: number;
  standard?: number;
  quick?: number;
};

const SectionCountsStrip: React.FC<{
  counts: SectionCounts;
  frame: number;
  delay: number;
}> = ({ counts, frame, delay }) => {
  const d = useDesign();
  const focus = Number(counts.focus || 0);
  const standard = Number(counts.standard || 0);
  const quick = Number(counts.quick || 0);
  const total = focus + standard + quick;
  if (total <= 0) return null;
  const grow = interpolate(frame, [delay, delay + 22], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = interpolate(frame, [delay, delay + 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const segments: { count: number; color: string; label: string; key: string }[] = [
    { count: focus, color: CHAPTERS.focus.accent, label: "重点", key: "focus" },
    { count: standard, color: CHAPTERS.compact.accent, label: "速读", key: "standard" },
    { count: quick, color: CHAPTERS.quick.accent, label: "快扫", key: "quick" },
  ].filter((s) => s.count > 0);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: d.scaled(10),
        marginTop: d.scaled(20),
        opacity,
      }}
    >
      <div
        style={{
          display: "flex",
          height: d.scaled(10),
          width: "100%",
          borderRadius: 999,
          backgroundColor: COLORS.surfaceLow,
          overflow: "hidden",
        }}
      >
        {segments.map((seg, i) => {
          const ratio = seg.count / total;
          const segGrow = interpolate(grow, [i * 0.18, i * 0.18 + 0.5], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          return (
            <div
              key={seg.key}
              style={{
                width: `${ratio * 100 * segGrow}%`,
                height: "100%",
                backgroundColor: seg.color,
                marginRight: i < segments.length - 1 ? d.scaled(2) : 0,
              }}
            />
          );
        })}
      </div>
      <div
        style={{
          display: "flex",
          gap: d.scaled(20),
          flexWrap: "wrap",
        }}
      >
        {segments.map((seg) => (
          <div
            key={`${seg.key}-label`}
            style={{
              display: "flex",
              alignItems: "center",
              gap: d.scaled(6),
              fontFamily: FONTS.sans,
              fontSize: d.fs.bodySmall,
              fontWeight: FW.semibold,
              color: COLORS.textSecondary,
            }}
          >
            <span
              style={{
                width: d.scaled(8),
                height: d.scaled(8),
                borderRadius: 2,
                backgroundColor: seg.color,
                display: "inline-block",
              }}
            />
            <span>{seg.label}</span>
            <span
              style={{
                fontFamily: FONTS.mono,
                fontWeight: FW.heavy,
                color: COLORS.text,
              }}
            >
              {seg.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export const CoverCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();

  const headline = p(elementProps, "headline", "HN每日观察");
  const sectionCounts = (elementProps.section_counts as SectionCounts | undefined) ?? {};
  const highlightEntries = Array.isArray(elementProps.highlight_entries)
    ? (elementProps.highlight_entries as HighlightEntry[]).slice(0, 3)
    : [];
  const hasHighlights = highlightEntries.length > 0;

  const d = useDesign();
  const compact = d.isCompactHeight;
  const cardW = width - d.layout.pageInset * 2;
  const cardH = d.getCardMaxHeight;

  const { padX, padY } = useCardPad(compact);
  const { cardProgress, titleProgress, bodyProgress } = useCardAnimations(frame);

  return (
    <div
      style={{
        ...S,
        left: d.layout.pageInset,
        top: d.layout.topInset,
        width: cardW,
        minHeight: cardH,
        maxHeight: cardH,
        ...glassCard,
        boxShadow: glassCardShadow,
        padding: `${padY}px ${padX}px`,
        boxSizing: "border-box",
        opacity: cardProgress,
        transform: `translateY(${overshootTranslateY(cardProgress, d.scaled(CARD_ENTRANCE_Y))}px)`,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <GlassShimmer frame={frame} />

      {/* Header row */}
      <SectionLabel text="今日速递" delay={8} frame={frame} />

      {/* Headline */}
      <div
        style={{
          opacity: titleProgress,
          transform: `translateY(${interpolate(titleProgress, [0, 1], [HERO_ENTRANCE_Y, 0])}px)`,
        }}
      >
        <div
          style={{
            fontFamily: FONTS.bold,
            fontWeight: FW.bold,
            fontSize: heroFontSize(d, compact),
            color: COLORS.text,
            lineHeight: 1.1,
            letterSpacing: -0.5,
          }}
        >
          {headline}
        </div>
        <SectionCountsStrip counts={sectionCounts} frame={frame} delay={12} />
      </div>

      {/* Highlight entries */}
      {hasHighlights && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            marginTop: d.scaled(compact ? 24 : 36),
            flex: 1,
            opacity: bodyProgress,
            transform: `translateY(${interpolate(bodyProgress, [0, 1], [10, 0])}px)`,
          }}
        >
          <SectionLabel text="今日亮点" delay={14} frame={frame} />
          {highlightEntries.map((entry, i) => {
            const rowProgress = rowEntryAnimation(frame, 16 + i * ROW_STAGGER, 20);
            const angle = entry.editor_angle || "";
            const why = entry.original_title || "";
            const showMetrics =
              typeof entry.score === "number" || typeof entry.comment_count === "number";

            return (
              <div
                key={`${i}-${angle}`}
                style={{
                  position: "relative",
                  display: "flex",
                  alignItems: "flex-start",
                  gap: d.scaled(14),
                  padding: `${d.scaled(compact ? 14 : 18)}px 0`,
                  opacity: rowProgress,
                  transform: `translateY(${interpolate(rowProgress, [0, 1], [10, 0])}px)`,
                  borderBottom:
                    i < highlightEntries.length - 1 ? `1px solid ${COLORS.borderLow}` : undefined,
                }}
              >
                {/* Left medal */}
                <div
                  style={{
                    flexShrink: 0,
                    alignSelf: "flex-start",
                  }}
                >
                  <MedalBadge rank={i + 1} size={d.scaled(32)} fontSize={d.fs.bodySmall} />
                </div>

                {/* Content */}
                <div style={{ minWidth: 0, flex: 1, position: "relative", zIndex: 1 }}>
                  {/* Title row: angle + metrics pills on the right */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "baseline",
                      justifyContent: "space-between",
                      gap: d.scaled(12),
                    }}
                  >
                    <div
                      style={{
                        fontFamily: FONTS.bold,
                        fontSize: subheadFontSize(d, compact),
                        lineHeight: 1.35,
                        fontWeight: FW.bold,
                        color: COLORS.text,
                        overflow: "hidden",
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical" as const,
                        flex: 1,
                        minWidth: 0,
                      }}
                    >
                      {angle}
                    </div>
                    {showMetrics && (
                      <div
                        style={{
                          display: "flex",
                          gap: d.scaled(8),
                          flexShrink: 0,
                          alignItems: "center",
                        }}
                      >
                        {typeof entry.score === "number" && (
                          <MetricPill
                            icon="🔥"
                            value={entry.score}
                            delay={18 + i * ROW_STAGGER}
                            frame={frame}
                          />
                        )}
                        {typeof entry.comment_count === "number" && (
                          <MetricPill
                            icon="💬"
                            value={entry.comment_count}
                            delay={20 + i * ROW_STAGGER}
                            frame={frame}
                          />
                        )}
                      </div>
                    )}
                  </div>

                  {why && (
                    <div
                      style={{
                        fontFamily: FONTS.sans,
                        fontSize: d.fs.bodyLg,
                        lineHeight: 1.5,
                        fontWeight: FW.regular,
                        color: COVER_SUBTITLE_COLOR,
                        marginTop: d.scaled(compact ? 5 : 8),
                        overflow: "hidden",
                        display: "-webkit-box",
                        WebkitLineClamp: 1,
                        WebkitBoxOrient: "vertical" as const,
                      }}
                    >
                      {why}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

    </div>
  );
};

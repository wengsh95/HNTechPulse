import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { ElementProps, p } from "./utils";
import { COLORS, FONTS, FW, useDesign, glassCard, glassCardShadow, S, GRADIENTS } from "./design";
import {
  dividerStyle,
  GlassShimmer,
  HighlightEntry,
  MedalBadge,
  MetricPill,
  overshootTranslateY,
  rowEntryAnimation,
  SectionLabel,
  useCardPad,
  useCardAnimations,
  bodySectionGap,
  heroFontSize,
  subheadFontSize,
  CardKeywordsFooter,
  CARD_ENTRANCE_Y,
  HERO_ENTRANCE_Y,
  ROW_STAGGER,
} from "./HighlightShared";

const COVER_SUBTITLE_COLOR = "rgba(245,245,247,0.50)";

export const CoverCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();

  const headline = p(elementProps, "headline", "HNTech 每日技术速递");
  const keywords = Array.isArray(elementProps.keywords)
    ? elementProps.keywords.filter((k): k is string => typeof k === "string")
    : [];
  const highlightEntries = Array.isArray(elementProps.highlight_entries)
    ? (elementProps.highlight_entries as HighlightEntry[]).slice(0, 3)
    : [];
  const hasHighlights = highlightEntries.length > 0;

  const d = useDesign();
  const compact = d.isCompactHeight;
  const cardW = width - d.layout.pageInset * 2;
  const cardH = d.getCardMaxHeight;

  const { padX, padY } = useCardPad(compact);
  const { cardProgress, titleProgress, bodyProgress, footerProgress } = useCardAnimations(frame);

  return (
    <div
      style={{
        ...S,
        left: d.layout.pageInset,
        top: d.layout.topInset,
        width: cardW,
        height: cardH,
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
            const showMetrics = typeof entry.score === "number" || typeof entry.comment_count === "number";

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
                  borderBottom: i < highlightEntries.length - 1 ? `1px solid ${COLORS.borderLow}` : undefined,
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

      {/* Keywords */}
      {keywords.length > 0 && (
        <>
          <div style={dividerStyle} />
          <CardKeywordsFooter keywords={keywords.slice(0, 3)} progress={footerProgress} frame={frame} delayBase={20} />
        </>
      )}
    </div>
  );
};

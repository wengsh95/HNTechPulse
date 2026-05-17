import React from "react";
import { interpolate, useCurrentFrame } from "remotion";

import { COLORS, FONTS, FW, useDesign, glassCard, glassCardShadow, S } from "./design";
import {
  dividerStyle,
  GlassShimmer,
  lineClamp,
  MetricPill,
  overshootTranslateY,
  useCardPad,
  useCardAnimations,
  headerMargin,
  titleBodyGap,
  bodySectionGap,
  titleFontSize,
  ChapterWatermark,
  CardKeywordsFooter,
  CARD_ENTRANCE_Y,
  TITLE_ENTRANCE_Y,
  BODY_ENTRANCE_Y,
  HEADER_ENTRANCE_Y,
} from "./HighlightShared";
import { cleanText, ElementProps, limitList, p } from "./utils";

export const QuickItemCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();

  const displayTitle = cleanText(
    p(elementProps, "display_title", "") ||
      p(elementProps, "title_cn", "") ||
      p(elementProps, "source_title", ""),
  );
  const quickLabel = cleanText(p(elementProps, "quick_label", p(elementProps, "category", "快扫")));
  const microTakeaway = cleanText(p(elementProps, "micro_takeaway", ""));
  const sourceTitle = cleanText(p(elementProps, "source_title", ""));
  const showOriginalTitle = Boolean(sourceTitle && displayTitle !== sourceTitle);
  const keywords = limitList(
    Array.isArray(elementProps.keywords)
      ? elementProps.keywords.filter((k): k is string => typeof k === "string")
      : [],
    4,
    16,
  );
  const displayIndex = Number(p(elementProps, "display_index", 0)) || 0;
  const storyCount = Number(p(elementProps, "story_count", 0)) || 0;
  const showChapterWatermark = displayIndex >= 0 && storyCount > 0;
  const displayOrdinal = displayIndex + 1;

  const heatScore = Number(p(elementProps, "score", 0)) || 0;
  const commentCount = Number(p(elementProps, "comment_count", 0)) || 0;
  const showMetrics = heatScore > 0 || commentCount > 0;

  const d = useDesign();
  const compact = d.isCompactHeight;
  const cardW = width - d.layout.pageInset * 2;
  const cardMaxH = d.getCardMaxHeight;

  const { padX, padY } = useCardPad(compact);
  const { cardProgress, titleProgress, bodyProgress, footerProgress } = useCardAnimations(frame);

  const resolvedTitleFontSize = titleFontSize(d, compact);
  const hasBody = Boolean(microTakeaway);

  return (
    <div
      style={{
        ...S,
        left: d.layout.pageInset,
        top: d.layout.topInset,
        width: cardW,
        minHeight: cardMaxH,
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
      {showChapterWatermark && (
        <ChapterWatermark
          displayIndex={displayOrdinal}
          storyCount={storyCount}
          padX={padX}
          padY={padY}
          frame={frame}
        />
      )}

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          position: "relative",
          zIndex: 1,
          flex: 1,
        }}
      >
        {/* Header row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: d.scaled(12),
            marginBottom: headerMargin(compact),
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [HEADER_ENTRANCE_Y, 0])}px)`,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: d.scaled(10) }}>
            <div
              style={{
                width: d.scaled(3),
                height: d.scaled(14),
                borderRadius: 2,
                background: COLORS.brand,
                flexShrink: 0,
              }}
            />
            <span
              style={{
                fontFamily: FONTS.sans,
                fontSize: d.fs.bodySmall,
                fontWeight: FW.semibold,
                color: COLORS.textSecondary,
                letterSpacing: 0.4,
              }}
            >
              {quickLabel || "快扫"}
            </span>
          </div>
        </div>

        {/* Main title */}
        <div
          style={{
            fontFamily: FONTS.bold,
            fontWeight: FW.heavy,
            fontSize: resolvedTitleFontSize,
            color: COLORS.text,
            lineHeight: 1.15,
            letterSpacing: -0.4,
            marginBottom: showOriginalTitle ? titleBodyGap(compact) * 0.5 : titleBodyGap(compact),
            overflowWrap: "anywhere",
            wordBreak: "break-word",
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [TITLE_ENTRANCE_Y, 0])}px)`,
            ...lineClamp(2),
          }}
        >
          {displayTitle}
        </div>

        {/* English subtitle */}
        {showOriginalTitle && (
          <div
            style={{
              fontFamily: FONTS.sans,
              fontWeight: FW.regular,
              fontSize: d.fs.bodyLg,
              color: COLORS.textTertiary,
              marginBottom: titleBodyGap(compact),
              lineHeight: 1.4,
              overflowWrap: "anywhere",
              wordBreak: "break-word",
              opacity: titleProgress,
              transform: `translateY(${interpolate(titleProgress, [0, 1], [6, 0])}px)`,
              ...lineClamp(1),
            }}
          >
            {sourceTitle}
          </div>
        )}

        {/* Metrics row */}
        {showMetrics && (
          <div
            style={{
              display: "flex",
              gap: d.scaled(10),
              marginBottom: hasBody ? bodySectionGap(compact) : 0,
              opacity: titleProgress,
            }}
          >
            {heatScore > 0 && <MetricPill icon="🔥" value={heatScore} delay={12} frame={frame} />}
            {commentCount > 0 && (
              <MetricPill icon="💬" value={commentCount} delay={14} frame={frame} />
            )}
          </div>
        )}

        {/* Body: micro takeaway */}
        {hasBody && (
          <div
            style={{
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [BODY_ENTRANCE_Y, 0])}px)`,
            }}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr",
                gap: compact ? 8 : 12,
                marginBottom: keywords.length > 0 ? bodySectionGap(compact) : 0,
              }}
            >
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 4,
                  backgroundColor: COLORS.surfaceFaint,
                  borderRadius: 8,
                  padding: "10px 14px",
                  borderLeft: `3px solid ${COLORS.brand}`,
                }}
              >
                <span
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: d.fs.caption,
                    fontWeight: FW.bold,
                    color: COLORS.brandLight,
                    lineHeight: 1.4,
                    letterSpacing: 0.2,
                  }}
                >
                  要点
                </span>
                <span
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: d.fs.body,
                    fontWeight: FW.medium,
                    color: COLORS.textBody,
                    lineHeight: 1.7,
                    overflowWrap: "anywhere",
                    wordBreak: "break-word",
                    ...lineClamp(2),
                  }}
                >
                  {microTakeaway}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Keywords row */}
        {keywords.length > 0 && (
          <>
            <div style={dividerStyle} />
            <CardKeywordsFooter keywords={keywords} progress={footerProgress} frame={frame} delayBase={20} />
          </>
        )}

        {/* Spacer when no body, no metrics, no keywords */}
        {!hasBody && !showMetrics && keywords.length === 0 && <div style={{ flex: 1 }} />}
      </div>
    </div>
  );
};

import React from "react";
import { useCurrentFrame, interpolate } from "remotion";

import { ElementProps, p } from "./utils";
import { COLORS, FONTS, FW, useDesign, glassCard, glassCardShadow, S } from "./design";
import {
  GlassShimmer,
  overshootTranslateY,
  useCardPad,
  useCardAnimations,
  CARD_ENTRANCE_Y,
  HERO_ENTRANCE_Y,
  BODY_ENTRANCE_Y,
  lineClamp,
} from "./HighlightShared";

type SummaryItem = {
  category?: string;
  title?: string;
  note?: string;
};

const asNumber = (value: unknown): number => {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
};

export const ClosingCard: React.FC<ElementProps> = ({ elementProps, width }) => {
  const frame = useCurrentFrame();
  const d = useDesign();
  const compact = d.isCompactHeight;

  const signalLabel = p(elementProps, "signal_label", "今日信号");
  const signal = p(elementProps, "signal", "");
  const keywordsLabel = p(elementProps, "keywords_label", "今日关键词");
  const question = p(elementProps, "question", "");
  const visualMood = p(elementProps, "visual_mood", "");
  const mainSignal = signal || question;
  const keywords = Array.isArray(elementProps.keywords)
    ? elementProps.keywords.filter((k): k is string => typeof k === "string")
    : [];
  const summaryLabel = p(elementProps, "summary_label", "今日脉络");
  const summaryItems = Array.isArray(elementProps.summary_items)
    ? (elementProps.summary_items as SummaryItem[])
        .filter((item) => item && (item.title || item.note))
        .slice(0, 3)
    : [];
  const totals =
    elementProps.totals && typeof elementProps.totals === "object"
      ? (elementProps.totals as Record<string, unknown>)
      : {};
  const storyCount = asNumber(totals.story_count);
  const scoreTotal = asNumber(totals.score_total);
  const commentTotal = asNumber(totals.comment_total);
  const hasTotals = storyCount > 0 || scoreTotal > 0 || commentTotal > 0;

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

      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          justifyContent: "flex-start",
          position: "relative",
          zIndex: 1,
          minHeight: 0,
          paddingTop: d.scaled(compact ? 12 : 20),
        }}
      >
        {mainSignal && (
          <div
            style={{
              opacity: titleProgress,
              transform: `translateY(${interpolate(titleProgress, [0, 1], [HERO_ENTRANCE_Y, 0])}px)`,
              textAlign: "left",
              maxWidth: "100%",
            }}
          >
            <div
              style={{
                fontFamily: FONTS.sans,
                fontSize: d.fs.label,
                color: COLORS.brandLight,
                lineHeight: 1.2,
                fontWeight: FW.semibold,
                letterSpacing: 0,
                marginBottom: d.scaled(compact ? 14 : 18),
              }}
            >
              {signalLabel}
            </div>
            <div
              style={{
                fontFamily: FONTS.bold,
                fontSize: compact ? d.fs.subhead : d.fs.headline,
                color: COLORS.text,
                lineHeight: 1.28,
                fontWeight: FW.bold,
                letterSpacing: 0,
                maxWidth: d.scaled(1100),
              }}
            >
              {mainSignal}
            </div>
          </div>
        )}

        {keywords.length > 0 && (
          <div
            style={{
              marginTop: d.scaled(compact ? 20 : 28),
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [BODY_ENTRANCE_Y, 0])}px)`,
              textAlign: "left",
            }}
          >
            <div
              style={{
                fontFamily: FONTS.sans,
                fontSize: d.fs.bodySmall,
                color: COLORS.textTertiary,
                fontWeight: FW.semibold,
                letterSpacing: 0,
                marginBottom: d.scaled(compact ? 8 : 10),
              }}
            >
              {keywordsLabel}
            </div>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: d.scaled(8),
              }}
            >
              {keywords.slice(0, 5).map((keyword) => (
                <span
                  key={keyword}
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: d.fs.caption,
                    color: COLORS.accentLight,
                    fontWeight: FW.semibold,
                    background: COLORS.accentSurface,
                    border: `1px solid ${COLORS.accentBorderSubtle}`,
                    borderRadius: 999,
                    padding: `${d.scaled(5)}px ${d.scaled(12)}px`,
                    letterSpacing: 0,
                  }}
                >
                  {keyword}
                </span>
              ))}
            </div>
          </div>
        )}

        {summaryItems.length > 0 && (
          <div
            style={{
              marginTop: d.scaled(compact ? 22 : 32),
              width: "100%",
              maxWidth: d.scaled(1160),
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [BODY_ENTRANCE_Y, 0])}px)`,
            }}
          >
            <div
              style={{
                fontFamily: FONTS.sans,
                fontSize: d.fs.bodySmall,
                color: COLORS.textTertiary,
                fontWeight: FW.semibold,
                letterSpacing: 0,
                marginBottom: d.scaled(compact ? 10 : 14),
              }}
            >
              {summaryLabel}
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateRows: `repeat(${summaryItems.length}, minmax(0, auto))`,
                gap: d.scaled(compact ? 10 : 12),
              }}
            >
              {summaryItems.map((item, index) => (
                <div
                  key={`${item.category ?? "item"}-${index}`}
                  style={{
                    display: "grid",
                    gridTemplateColumns: `${d.scaled(96)}px minmax(0, 1fr)`,
                    gap: d.scaled(16),
                    alignItems: "start",
                    padding: `${d.scaled(compact ? 10 : 12)}px ${d.scaled(14)}px`,
                    background: COLORS.surfaceSubtle,
                    border: `1px solid ${COLORS.borderLow}`,
                    borderRadius: d.scaled(8),
                    boxSizing: "border-box",
                  }}
                >
                  <div
                    style={{
                      fontFamily: FONTS.sans,
                      fontSize: d.fs.caption,
                      color: COLORS.brandLight,
                      fontWeight: FW.heavy,
                      lineHeight: 1.35,
                      letterSpacing: 0,
                      overflow: "hidden",
                      whiteSpace: "nowrap",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {item.category || "观察"}
                  </div>
                  <div style={{ minWidth: 0 }}>
                    {item.title && (
                      <div
                        style={{
                          fontFamily: FONTS.sans,
                          fontSize: d.fs.bodyLg,
                          color: COLORS.text,
                          fontWeight: FW.bold,
                          lineHeight: 1.35,
                          letterSpacing: 0,
                          ...lineClamp(1),
                        }}
                      >
                        {item.title}
                      </div>
                    )}
                    {item.note && (
                      <div
                        style={{
                          marginTop: item.title ? d.scaled(4) : 0,
                          fontFamily: FONTS.sans,
                          fontSize: d.fs.bodySmall,
                          color: COLORS.textSecondary,
                          fontWeight: FW.medium,
                          lineHeight: 1.45,
                          letterSpacing: 0,
                          ...lineClamp(1),
                        }}
                      >
                        {item.note}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {hasTotals && (
          <div
            style={{
              display: "flex",
              gap: d.scaled(20),
              marginTop: d.scaled(compact ? 18 : 24),
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [BODY_ENTRANCE_Y, 0])}px)`,
              fontFamily: FONTS.mono,
              color: COLORS.textTertiary,
              fontSize: d.fs.caption,
              fontWeight: FW.semibold,
              letterSpacing: 0,
            }}
          >
            {storyCount > 0 && <span>{storyCount} 条主线</span>}
            {scoreTotal > 0 && <span>{scoreTotal.toLocaleString("en-US")} points</span>}
            {commentTotal > 0 && <span>{commentTotal.toLocaleString("en-US")} comments</span>}
          </div>
        )}

        {visualMood && (
          <div
            style={{
              marginTop: d.scaled(compact ? 18 : 24),
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [BODY_ENTRANCE_Y, 0])}px)`,
              textAlign: "left",
              fontFamily: FONTS.mono,
              fontSize: d.fs.bodySmall,
              color: COLORS.textTertiary,
              fontWeight: FW.medium,
              letterSpacing: 0,
              textTransform: "uppercase",
            }}
          >
            {visualMood}
          </div>
        )}
      </div>
    </div>
  );
};

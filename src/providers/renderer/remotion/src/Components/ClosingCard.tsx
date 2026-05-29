import React from "react";
import { useCurrentFrame, interpolate } from "remotion";

import { ElementProps, p } from "./utils";
import { CHAPTERS, COLORS, FONTS, FW, useDesign, glassCard, glassCardShadow, S } from "./design";
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
};

const asNumber = (value: unknown): number => {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
};

/** Three-segment completion bar in chapter colors, animates from 0% to 100%. */
const CompletionStrip: React.FC<{ frame: number; delay: number }> = ({ frame, delay }) => {
  const d = useDesign();
  const grow = interpolate(frame, [delay, delay + 24], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const segments = [
    { color: CHAPTERS.focus.accent, key: "focus" },
    { color: CHAPTERS.compact.accent, key: "compact" },
    { color: CHAPTERS.quick.accent, key: "quick" },
  ];
  return (
    <div
      style={{
        display: "flex",
        height: d.scaled(8),
        width: "100%",
        borderRadius: 999,
        backgroundColor: COLORS.surfaceLow,
        overflow: "hidden",
      }}
    >
      {segments.map((seg, i) => {
        const segGrow = interpolate(grow, [i * 0.18, i * 0.18 + 0.5], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        return (
          <div
            key={seg.key}
            style={{
              flex: 1,
              height: "100%",
              backgroundColor: seg.color,
              opacity: 0.85 * segGrow,
              transform: `scaleX(${segGrow})`,
              transformOrigin: "left",
              marginRight: i < segments.length - 1 ? d.scaled(2) : 0,
            }}
          />
        );
      })}
    </div>
  );
};

const CATEGORY_ACCENT: Record<string, string> = {
  开源生态: COLORS.green,
  其他: COLORS.gray,
};

const AchievementRow: React.FC<{
  item: SummaryItem;
  index: number;
  frame: number;
}> = ({ item, index, frame }) => {
  const d = useDesign();
  const delay = 22 + index * 4;
  const progress = interpolate(frame, [delay, delay + 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const accent = CATEGORY_ACCENT[item.category ?? ""] ?? COLORS.accentLight;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: d.scaled(10),
        opacity: progress,
        transform: `translateX(${interpolate(progress, [0, 1], [-8, 0])}px)`,
        minWidth: 0,
      }}
    >
      <span
        style={{
          width: d.scaled(16),
          height: d.scaled(16),
          borderRadius: "50%",
          backgroundColor: accent,
          color: COLORS.bg,
          fontFamily: FONTS.sans,
          fontSize: d.fs.micro,
          fontWeight: FW.heavy,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          lineHeight: 1,
        }}
      >
        ✓
      </span>
      {item.category && (
        <span
          style={{
            fontFamily: FONTS.sans,
            fontSize: d.fs.caption,
            color: accent,
            fontWeight: FW.heavy,
            backgroundColor: `${accent}1A`,
            border: `1px solid ${accent}40`,
            borderRadius: d.scaled(4),
            padding: `${d.scaled(2)}px ${d.scaled(8)}px`,
            lineHeight: 1.3,
            flexShrink: 0,
            letterSpacing: 0.2,
          }}
        >
          {item.category}
        </span>
      )}
      {item.title && (
        <span
          style={{
            fontFamily: FONTS.sans,
            fontSize: d.fs.bodyLg,
            color: COLORS.text,
            fontWeight: FW.semibold,
            lineHeight: 1.35,
            flex: 1,
            minWidth: 0,
            ...lineClamp(1),
          }}
        >
          {item.title}
        </span>
      )}
    </div>
  );
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
    ? (elementProps.summary_items as SummaryItem[]).filter((item) => item && item.title).slice(0, 3)
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

      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "flex-start",
          justifyContent: "center",
          position: "relative",
          zIndex: 1,
          minHeight: 0,
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
                fontSize: compact ? d.fs.headline : d.fs.closing,
                color: COLORS.text,
                lineHeight: 1.28,
                fontWeight: FW.bold,
                letterSpacing: 0,
                maxWidth: d.layout.contentWideMaxWidth,
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
              maxWidth: d.layout.contentWideMaxWidth,
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [BODY_ENTRANCE_Y, 0])}px)`,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "baseline",
                justifyContent: "space-between",
                marginBottom: d.scaled(compact ? 8 : 10),
              }}
            >
              <span
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: d.fs.bodySmall,
                  color: COLORS.textTertiary,
                  fontWeight: FW.semibold,
                  letterSpacing: 0,
                }}
              >
                {summaryLabel}
              </span>
              {storyCount > 0 && (
                <span
                  style={{
                    fontFamily: FONTS.mono,
                    fontSize: d.fs.caption,
                    color: COLORS.textSecondary,
                    fontWeight: FW.bold,
                  }}
                >
                  {storyCount} / {storyCount} 已完成
                </span>
              )}
            </div>
            {/* Completion strip — chapter-accent color, full-width, animates in */}
            <CompletionStrip frame={frame} delay={18} />
            {/* Compact achievement list — checkmark + category + title, no boxes */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: d.scaled(compact ? 6 : 8),
                marginTop: d.scaled(compact ? 12 : 14),
              }}
            >
              {summaryItems.map((item, index) => (
                <AchievementRow
                  key={`${item.category ?? "item"}-${index}`}
                  item={item}
                  index={index}
                  frame={frame}
                />
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

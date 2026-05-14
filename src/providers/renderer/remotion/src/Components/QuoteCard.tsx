import React from "react";
import { interpolate, Easing, useCurrentFrame } from "remotion";

import { STANCE_COLORS } from "./StancePie";
import {
  COLORS,
  FONTS,
  FW,
  getCardMaxHeight,
  glassCard,
  glassCardShadow,
  isCompactHeight,
  LAYOUT,
  S,
  sectionLabel,
} from "./design";
import { cleanText, ElementProps, stanceLabel, UI_TEXT } from "./utils";

interface Quote {
  author: string;
  text: string;
  text_cn?: string;
  stance: string;
}

function getQuoteText(quote: Quote) {
  const hasChinese = Boolean(quote.text_cn?.trim());

  return {
    primaryText: hasChinese ? cleanText(quote.text_cn!.trim()) : cleanText(quote.text),
  };
}

const QuoteMeta: React.FC<{ quote: Quote; featured?: boolean }> = ({ quote, featured = false }) => {
  const stanceColor = STANCE_COLORS[quote.stance] || COLORS.textSecondary;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: featured ? 12 : 8,
        marginBottom: featured ? 20 : 10,
        flexWrap: "wrap",
      }}
    >
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: featured ? 12 : 10,
          fontWeight: FW.heavy,
          color: stanceColor,
          backgroundColor: stanceColor + (featured ? "22" : "18"),
          border: `1px solid ${stanceColor}${featured ? "38" : "24"}`,
          borderRadius: LAYOUT.chipRadius,
          padding: featured ? "5px 12px" : "4px 9px",
          letterSpacing: 0,
        }}
      >
        {stanceLabel(quote.stance)}
      </span>
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: featured ? 14 : 12,
          fontWeight: featured ? FW.semibold : FW.medium,
          color: featured ? COLORS.text : COLORS.textSecondary,
        }}
      >
        {quote.author}
      </span>
    </div>
  );
};

function lineClamp(lines: number): React.CSSProperties {
  return {
    overflow: "hidden",
    display: "-webkit-box",
    WebkitLineClamp: lines,
    WebkitBoxOrient: "vertical" as const,
  };
}

const QuoteEntry: React.FC<{
  quote: Quote;
  index: number;
  frame: number;
  featuredProgress: number;
  compact: boolean;
}> = ({ quote, index, frame, featuredProgress, compact }) => {
  const quoteProgress =
    index === 0
      ? featuredProgress
      : interpolate(frame, [14 + index * 9, 14 + index * 9 + 18], [0, 1], {
          easing: Easing.bezier(0.16, 1, 0.3, 1),
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
  const stanceColor = STANCE_COLORS[quote.stance] || COLORS.textSecondary;
  const { primaryText } = getQuoteText(quote);
  const isFeatured = index === 0;
  const borderReveal = interpolate(quoteProgress, [0, 1], [0, isFeatured ? 5 : 4]);

  return (
    <div
      key={`${quote.author}-${index}`}
      style={{
        opacity: quoteProgress,
        transform: `translateY(${interpolate(quoteProgress, [0, 1], [16, 0])}px)`,
        position: "relative",
        overflow: "hidden",
        borderRadius: LAYOUT.panelRadius,
        background: isFeatured ? `${stanceColor}0A` : "rgba(255,255,255,0.04)",
        border: `1px solid ${isFeatured ? stanceColor + "25" : "rgba(255,255,255,0.08)"}`,
        borderLeft: `${borderReveal}px solid ${stanceColor}`,
        padding: compact ? "12px 20px" : isFeatured ? "18px 24px" : "14px 22px",
        boxSizing: "border-box",
      }}
    >
      <QuoteMeta quote={quote} featured={isFeatured} />
      <div
        style={{
          fontFamily: FONTS.sans,
          fontSize: compact ? 16 : 18,
          color: COLORS.text,
          lineHeight: compact ? 1.42 : 1.5,
          fontWeight: FW.semibold,
          letterSpacing: 0,
          maxWidth: "100%",
          overflowWrap: "anywhere",
          wordBreak: "break-word",
          ...lineClamp(isFeatured ? (compact ? 2 : 3) : 2),
        }}
      >
        &ldquo;{primaryText}&rdquo;
      </div>
    </div>
  );
};

export const QuoteCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();

  const quotes = ((elementProps.quotes as Quote[]) ?? []).slice(0, 3);
  const compact = isCompactHeight(height);
  const cardW = width - LAYOUT.pageInset * 2;
  const cardMaxH = getCardMaxHeight(height);
  const topY = LAYOUT.topInset;

  const cardProgress = interpolate(frame, [4, 22], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (quotes.length === 0) {
    return null;
  }

  const featuredProgress = interpolate(frame, [10, 28], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        ...S,
        left: LAYOUT.pageInset,
        top: topY,
        width: cardW,
        maxHeight: cardMaxH,
        ...glassCard,
        padding: compact ? "24px 32px" : "28px 36px",
        boxShadow: glassCardShadow,
        boxSizing: "border-box",
        overflow: "hidden",
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [28, 0])}px)`,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: compact ? 14 : 18,
          gap: 24,
        }}
      >
        <div style={{ ...sectionLabel, marginBottom: 0 }}>{UI_TEXT.keyVoices}</div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            minWidth: 0,
          }}
        >
          {quotes.map((quote, i) => {
            const stanceColor = STANCE_COLORS[quote.stance] || COLORS.textSecondary;

            return (
              <span
                key={`${quote.author}-${i}`}
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: 11,
                  fontWeight: FW.bold,
                  color: i === 0 ? COLORS.text : COLORS.textSecondary,
                  backgroundColor: i === 0 ? stanceColor + "15" : "rgba(255,255,255,0.06)",
                  border: `1px solid ${i === 0 ? stanceColor + "25" : "rgba(255,255,255,0.10)"}`,
                  borderRadius: LAYOUT.chipRadius,
                  padding: "5px 10px",
                  whiteSpace: "nowrap",
                }}
              >
                {stanceLabel(quote.stance)}
              </span>
            );
          })}
        </div>
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: compact ? 12 : 14,
        }}
      >
        {quotes.map((quote, i) => (
          <QuoteEntry
            key={`${quote.author}-${i}`}
            quote={quote}
            index={i}
            frame={frame}
            featuredProgress={featuredProgress}
            compact={compact}
          />
        ))}
      </div>
    </div>
  );
};

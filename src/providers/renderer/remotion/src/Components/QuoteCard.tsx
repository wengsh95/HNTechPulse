import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

import { STANCE_COLORS } from "./StancePie";
import { COLORS, FONTS, glassCard, glassCardShadow, LAYOUT, S, sectionLabel } from "./design";
import { ElementProps, stanceLabel, stripHtml, UI_TEXT } from "./utils";

interface Quote {
  author: string;
  text: string;
  text_cn?: string;
  stance: string;
}

function cleanQuote(text: string): string {
  return stripHtml(text)
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&gt;/g, ">")
    .replace(/&lt;/g, "<")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .replace(/^\s*>+\s*/, "")
    .trim();
}

function lineClamp(lines: number): React.CSSProperties {
  return {
    overflow: "hidden",
    display: "-webkit-box",
    WebkitLineClamp: lines,
    WebkitBoxOrient: "vertical" as const,
  };
}

function getQuoteText(quote: Quote) {
  const hasChinese = Boolean(quote.text_cn?.trim());

  return {
    primaryText: hasChinese ? cleanQuote(quote.text_cn!.trim()) : cleanQuote(quote.text),
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
          fontWeight: 780,
          color: stanceColor,
          backgroundColor: stanceColor + (featured ? "22" : "18"),
          border: `1px solid ${stanceColor}${featured ? "38" : "24"}`,
          borderRadius: 999,
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
          fontWeight: featured ? 640 : 560,
          color: featured ? "rgba(255,255,255,0.72)" : COLORS.textSecondary,
        }}
      >
        {quote.author}
      </span>
    </div>
  );
};

export const QuoteCard: React.FC<ElementProps> = ({ elementProps, width }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const quotes = ((elementProps.quotes as Quote[]) ?? []).slice(0, 3);
  const featuredQuote = quotes[0];
  const cardW = width - LAYOUT.pageInset * 2;
  const topY = LAYOUT.topInset;

  const cardProgress = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 120 },
  });

  if (quotes.length === 0) {
    return null;
  }

  const featuredProgress = spring({
    frame,
    fps,
    config: { damping: 10, stiffness: 130 },
    delay: 6,
  });

  const featuredColor = STANCE_COLORS[featuredQuote.stance] || COLORS.textSecondary;

  return (
    <div
      style={{
        ...S,
        left: LAYOUT.pageInset,
        top: topY,
        width: cardW,
        ...glassCard,
        padding: "40px 48px",
        boxShadow: glassCardShadow,
        boxSizing: "border-box",
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [28, 0])}px)`,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 20,
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
                  fontWeight: 720,
                  color: i === 0 ? "rgba(255,255,255,0.78)" : COLORS.textSecondary,
                  backgroundColor: i === 0 ? stanceColor + "22" : "rgba(255,255,255,0.045)",
                  border: `1px solid ${i === 0 ? stanceColor + "34" : "rgba(255,255,255,0.06)"}`,
                  borderRadius: 999,
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
          gap: 16,
        }}
      >
        {quotes.map((quote, i) => {
          const quoteProgress = i === 0
            ? featuredProgress
            : spring({
              frame,
              fps,
              config: { damping: 10, stiffness: 130 },
              delay: 10 + i * 7,
            });
          const stanceColor = STANCE_COLORS[quote.stance] || COLORS.textSecondary;
          const { primaryText } = getQuoteText(quote);
          const isFeatured = i === 0;

          return (
          <div
            key={`${quote.author}-${i}`}
            style={{
              opacity: quoteProgress,
              transform: `translateY(${interpolate(quoteProgress, [0, 1], [16, 0])}px)`,
              position: "relative",
              overflow: "hidden",
              borderRadius: 18,
              background: isFeatured
                ? `linear-gradient(135deg, rgba(255,255,255,0.075), rgba(255,255,255,0.038)), ${featuredColor}0D`
                : "rgba(255,255,255,0.032)",
              border: `1px solid ${isFeatured ? stanceColor + "30" : "rgba(255,255,255,0.055)"}`,
              borderLeft: `${isFeatured ? 5 : 4}px solid ${stanceColor}`,
              padding: isFeatured ? "16px 24px" : "16px 24px",
              boxSizing: "border-box",
              filter: isFeatured ? "none" : "saturate(0.88)",
            }}
          >
            <QuoteMeta quote={quote} featured={isFeatured} />
            <div
              style={{
                fontFamily: FONTS.sans,
                fontSize: 18,
                color: COLORS.text,
                lineHeight: 1.4,
                fontWeight: 680,
                letterSpacing: 0,
                maxWidth: "100%",
                overflowWrap: "anywhere",
                wordBreak: "break-word",
                ...lineClamp(3),
              }}
            >
              “{primaryText}”
            </div>

          </div>
          );
        })}
      </div>
    </div>
  );
};

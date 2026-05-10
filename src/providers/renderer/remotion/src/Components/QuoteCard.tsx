import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

import { ElementProps, stanceLabel, stripHtml, UI_TEXT } from "./utils";
import { STANCE_COLORS } from "./StancePie";
import { COLORS, FONTS, glassCard, glassCardShadow, LAYOUT, S, sectionLabel } from "./design";

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
    .trim();
}

export const QuoteCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const quotes = ((elementProps.quotes as Quote[]) ?? []).slice(0, 3);
  const cardW = width - LAYOUT.pageInset * 2;
  const topY = Math.round(height * 0.11);

  const cardProgress = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 120 },
  });

  if (quotes.length === 0) {
    return null;
  }

  return (
    <div
      style={{
        ...S,
        left: LAYOUT.pageInset,
        top: topY,
        width: cardW,
        ...glassCard,
        padding: "28px 36px 32px",
        boxShadow: glassCardShadow,
        boxSizing: "border-box",
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [28, 0])}px)`,
      }}
    >
      <div style={sectionLabel}>{UI_TEXT.keyVoices}</div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {quotes.map((quote, i) => {
          const quoteProgress = spring({
            frame,
            fps,
            config: { damping: 10, stiffness: 130 },
            delay: 6 + i * 7,
          });

          const stanceColor = STANCE_COLORS[quote.stance] || COLORS.textSecondary;
          const primaryText = quote.text_cn?.trim()
            ? cleanQuote(quote.text_cn.trim())
            : cleanQuote(quote.text);
          const originalText = quote.text_cn?.trim() ? cleanQuote(quote.text) : "";
          const isFeatured = i === 0;
          const label = stanceLabel(quote.stance);

          return (
            <div
              key={i}
              style={{
                opacity: quoteProgress,
                transform: `translateY(${interpolate(quoteProgress, [0, 1], [16, 0])}px)`,
                backgroundColor: isFeatured ? "rgba(255,255,255,0.06)" : "rgba(255,255,255,0.035)",
                borderRadius: 18,
                padding: isFeatured ? "16px 20px 18px" : "12px 16px 14px",
                borderLeft: `5px solid ${stanceColor}`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  marginBottom: isFeatured ? 14 : 8,
                  flexWrap: "wrap",
                }}
              >
                <span
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: 11,
                    fontWeight: 600,
                    color: stanceColor,
                    backgroundColor: stanceColor + "20",
                    borderRadius: 999,
                    padding: "4px 10px",
                    letterSpacing: 0.3,
                  }}
                >
                  {label}
                </span>
                <span
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: 13,
                    fontWeight: 500,
                    color: COLORS.textSecondary,
                  }}
                >
                  {quote.author}
                </span>
              </div>

              <div
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: 15,
                  color: COLORS.text,
                  lineHeight: 1.42,
                  fontWeight: 600,
                  letterSpacing: 0.1,
                  marginBottom: originalText ? 10 : 0,
                  maxWidth: "100%",
                  overflowWrap: "anywhere",
                  wordBreak: "break-word",
                }}
              >
                "{primaryText}"
              </div>

              {originalText && (
                <div
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: 14,
                    color: COLORS.textSecondary,
                    lineHeight: 1.45,
                    fontStyle: "italic",
                    maxWidth: "100%",
                    overflowWrap: "anywhere",
                    wordBreak: "break-word",
                  }}
                >
                  {UI_TEXT.original}："{originalText}"
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

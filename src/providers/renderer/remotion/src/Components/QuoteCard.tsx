import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

import { ElementProps } from "./utils";
import { STANCE_COLORS } from "./StancePie";
import { COLORS, FONTS, glassCard, glassCardShadow, LAYOUT, S } from "./design";

interface Quote {
  author: string;
  text: string;
  text_cn?: string;
  stance: string;
}

export const QuoteCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const quotes = (elementProps.quotes as Quote[]) ?? [];

  const cardW = width - LAYOUT.pageInset * 2;
  const topY = Math.round(height * 0.14);

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
        padding: "34px 44px 36px",
        boxShadow: glassCardShadow,
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [28, 0])}px)`,
      }}
    >
      <div
        style={{
          fontFamily: FONTS.sans,
          fontSize: 11,
          fontWeight: 600,
          color: COLORS.textTertiary,
          marginBottom: 20,
          textTransform: "uppercase",
          letterSpacing: 0.8,
        }}
      >
        Key Voices
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {quotes.map((quote, i) => {
          const quoteProgress = spring({
            frame,
            fps,
            config: { damping: 10, stiffness: 130 },
            delay: 6 + i * 7,
          });

          const stanceColor = STANCE_COLORS[quote.stance] || COLORS.textSecondary;

          return (
            <div
              key={i}
              style={{
                opacity: quoteProgress,
                transform: `translateY(${interpolate(quoteProgress, [0, 1], [16, 0])}px)`,
                backgroundColor: "rgba(255,255,255,0.04)",
                borderRadius: 16,
                padding: "18px 22px 20px",
                borderLeft: `4px solid ${stanceColor}`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  marginBottom: 10,
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
                  {quote.stance}
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
                  fontSize: 21,
                  color: COLORS.text,
                  lineHeight: 1.5,
                  fontWeight: 500,
                  letterSpacing: 0.1,
                  marginBottom: quote.text_cn ? 8 : 0,
                  maxWidth: LAYOUT.contentMaxWidth,
                }}
              >
                "{quote.text_cn || quote.text}"
              </div>

              {quote.text_cn && (
                <div
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: 13,
                    color: COLORS.textSecondary,
                    lineHeight: 1.5,
                    fontStyle: "italic",
                    maxWidth: LAYOUT.contentMaxWidth,
                  }}
                >
                  "{quote.text}"
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

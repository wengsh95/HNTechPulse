import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

import { ElementProps } from "./utils";
import { StancePie } from "./StancePie";
import { COLORS, FONTS, glassCard, glassCardShadow, LAYOUT, S } from "./design";

export const AtmosphereCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const stanceDistribution = (elementProps.stance_distribution as Record<string, number>) ?? {};
  const keywordTags = (elementProps.keyword_tags as Array<{ word: string; weight: number }>) ?? [];

  const hasPie = Object.keys(stanceDistribution).length > 0;
  const hasTags = keywordTags.length > 0;

  const cardW = width - LAYOUT.pageInset * 2;
  const topY = Math.round(height * 0.18);

  const cardProgress = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 120 },
  });

  const maxWeight = hasTags ? Math.max(...keywordTags.map((t) => t.weight)) : 1;

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
        Discussion Mood
      </div>

      <div style={{ display: "flex", gap: 40, alignItems: "flex-start" }}>
        {hasPie && <StancePie distribution={stanceDistribution} size={172} />}

        {hasTags && (
          <div style={{ flex: 1, minWidth: 0, maxWidth: LAYOUT.contentMaxWidth }}>
            <div
              style={{
                fontFamily: FONTS.sans,
                fontSize: 12,
                lineHeight: 1.4,
                color: COLORS.textTertiary,
                marginBottom: 16,
                textTransform: "uppercase",
                letterSpacing: 0.8,
              }}
            >
              Keywords
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
              {keywordTags.map((tag, i) => {
                const tagProgress = spring({
                  frame,
                  fps,
                  config: { damping: 10, stiffness: 140 },
                  delay: 6 + i * 3,
                });

                const ratio = tag.weight / maxWeight;
                const fontSize = 16 + ratio * 10;
                const opacity = 0.62 + ratio * 0.38;

                return (
                  <span
                    key={tag.word}
                    style={{
                      fontFamily: FONTS.sans,
                      fontSize,
                      fontWeight: ratio > 0.6 ? 600 : 400,
                      color: COLORS.text,
                      opacity: opacity * tagProgress,
                      backgroundColor: "rgba(255,255,255,0.06)",
                      borderRadius: 999,
                      padding: ratio > 0.7 ? "8px 16px" : "7px 14px",
                      lineHeight: 1.2,
                      transform: `translateY(${interpolate(tagProgress, [0, 1], [8, 0])}px)`,
                    }}
                  >
                    {tag.word}
                  </span>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

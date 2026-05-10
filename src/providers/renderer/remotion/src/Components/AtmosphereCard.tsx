import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

import { ElementProps, limitList, stanceLabel, truncate, UI_TEXT } from "./utils";
import { StancePie } from "./StancePie";
import { COLORS, FONTS, glassCard, glassCardShadow, LAYOUT, S } from "./design";

function getMoodSummary(distribution: Record<string, number>, keywords: Array<{ word: string; weight: number }>) {
  const entries = Object.entries(distribution)
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1]);

  if (entries.length === 0) {
    return {
      title: "社区反应仍在形成",
      detail: keywords.length > 0
        ? `讨论集中在 ${limitList(keywords.map((tag) => tag.word), 3, 14).join(" / ")}。`
        : "评论区还没有形成清晰的观点分布。",
      dominant: "",
      percent: 0,
    };
  }

  const [dominant, value] = entries[0];
  const dominantLabel = stanceLabel(dominant);
  const topKeywords = limitList(keywords.map((tag) => tag.word), 3, 14).join(" / ");

  return {
    title: `${dominantLabel}是当前主调`,
    detail: topKeywords
      ? `争论主要围绕 ${topKeywords} 展开。`
      : "评论区观点已经出现明显倾向。",
    dominant: dominantLabel,
    percent: Math.round(value * 100),
  };
}

export const AtmosphereCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const stanceDistribution = (elementProps.stance_distribution as Record<string, number>) ?? {};
  const keywordTags = ((elementProps.keyword_tags as Array<{ word: string; weight: number }>) ?? [])
    .slice(0, 8)
    .map((tag) => ({ ...tag, word: truncate(tag.word, 14) }))
    .filter((tag) => tag.word);

  const hasPie = Object.keys(stanceDistribution).length > 0;
  const hasTags = keywordTags.length > 0;

  const cardW = width - LAYOUT.pageInset * 2;
  const topY = Math.round(height * 0.13);

  const cardProgress = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 120 },
  });

  const maxWeight = hasTags ? Math.max(...keywordTags.map((t) => t.weight)) : 1;
  const mood = getMoodSummary(stanceDistribution, keywordTags);

  return (
    <div
      style={{
        ...S,
        left: LAYOUT.pageInset,
        top: topY,
        width: cardW,
        ...glassCard,
        padding: "38px 46px 40px",
        boxShadow: glassCardShadow,
        boxSizing: "border-box",
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [28, 0])}px)`,
      }}
    >
      <div style={{ display: "flex", gap: 46, alignItems: "center" }}>
        <div style={{ flex: "0 0 350px", minWidth: 0 }}>
          <div
            style={{
              fontFamily: FONTS.sans,
              fontSize: 11,
              fontWeight: 700,
              color: COLORS.textTertiary,
              marginBottom: 16,
              textTransform: "uppercase",
              letterSpacing: 0.9,
            }}
          >
            {UI_TEXT.discussionMood}
          </div>
          <div
            style={{
              fontFamily: FONTS.bold,
              fontSize: 36,
              lineHeight: 1.16,
              fontWeight: 800,
              color: COLORS.text,
              marginBottom: 14,
            }}
          >
            {mood.title}
          </div>
          <div
            style={{
              fontFamily: FONTS.sans,
              fontSize: 19,
              lineHeight: 1.48,
              color: COLORS.textSecondary,
              marginBottom: mood.percent > 0 ? 18 : 0,
            }}
          >
            {mood.detail}
          </div>
          {mood.percent > 0 && (
            <div
              style={{
                display: "inline-flex",
                alignItems: "baseline",
                gap: 8,
                padding: "8px 14px",
                borderRadius: 14,
                backgroundColor: "rgba(255,255,255,0.06)",
              }}
            >
              <span style={{ fontFamily: FONTS.mono, fontSize: 26, fontWeight: 800, color: COLORS.text }}>
                {mood.percent}%
              </span>
              <span style={{ fontFamily: FONTS.sans, fontSize: 12, color: COLORS.textSecondary }}>
                {mood.dominant}
              </span>
            </div>
          )}
        </div>

        {hasPie && <StancePie distribution={stanceDistribution} size={198} />}

        {hasTags && (
          <div style={{ flex: 1, minWidth: 0, maxWidth: 430 }}>
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
              {UI_TEXT.keywords}
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

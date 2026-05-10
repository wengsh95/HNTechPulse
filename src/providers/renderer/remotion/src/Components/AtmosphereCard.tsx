import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring } from "remotion";

import { ElementProps, p, stanceLabel, UI_TEXT } from "./utils";
import { StancePie } from "./StancePie";
import { COLORS, FONTS, glassCard, glassCardShadow, LAYOUT, S, sectionLabel } from "./design";

const CONTROVERSY_COLORS = {
  green: "#34c759",
  yellow: "#ff9f0a",
  red: "#ff3b30",
};

function getControversyColor(score: number): string {
  if (score <= 3) return CONTROVERSY_COLORS.green;
  if (score <= 7) return CONTROVERSY_COLORS.yellow;
  return CONTROVERSY_COLORS.red;
}

function getControversyLabel(score: number): string {
  if (score <= 3) return "共识较强";
  if (score <= 7) return "存在分歧";
  return "高度争议";
}

function getMoodSummary(distribution: Record<string, number>, debateFocus: string[], communitySentiment: string) {
  const entries = Object.entries(distribution)
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1]);

  if (entries.length === 0) {
    return {
      title: "社区反应仍在形成",
      detail: debateFocus.length > 0
        ? `争议焦点：${debateFocus.join(" · ")}`
        : "评论区还没有形成清晰的观点分布。",
      dominant: "",
      percent: 0,
    };
  }

  const [dominant, value] = entries[0];
  const dominantLabel = stanceLabel(dominant);

  return {
    title: communitySentiment || `${dominantLabel}是当前主调`,
    detail: debateFocus.length > 0
      ? `核心分歧：${debateFocus.join(" · ")}`
      : "评论区观点已经出现明显倾向。",
    dominant: dominantLabel,
    percent: Math.round(value * 100),
  };
}

export const AtmosphereCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const stanceDistribution = (elementProps.stance_distribution as Record<string, number>) ?? {};
  const debateFocus = (elementProps.debate_focus as string[]) ?? [];
  const communitySentiment = (elementProps.community_sentiment as string) ?? "";

  const controversyScore = p(elementProps, "controversy_score", 0);
  const commentCount = Number(p(elementProps, "comment_count", 0)) || 0;
  const heatScore = Number(p(elementProps, "score", 0)) || 0;
  const scoreNum =
    typeof controversyScore === "number" ? controversyScore : Number(controversyScore) || 0;
  const controversyColor = getControversyColor(scoreNum);
  const controversyLabel = getControversyLabel(scoreNum);

  const hasPie = Object.keys(stanceDistribution).length > 0;
  const hasFocus = debateFocus.length > 0;

  const cardW = width - LAYOUT.pageInset * 2;
  const topY = Math.round(height * 0.13);

  const cardProgress = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 120 },
  });

  const badgeProgress = spring({
    frame,
    fps,
    config: { damping: 10, stiffness: 150 },
    delay: 8,
  });

  const mood = getMoodSummary(stanceDistribution, debateFocus, communitySentiment);

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
          <div style={sectionLabel}>{UI_TEXT.discussionMood}</div>
          <div
            style={{
              fontFamily: FONTS.bold,
              fontSize: 20,
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
                marginBottom: 18,
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

          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              flexWrap: "wrap",
              backgroundColor: controversyColor + "15",
              border: `1.5px solid ${controversyColor}40`,
              borderRadius: 16,
              padding: "10px 18px",
              opacity: badgeProgress,
              transform: `scale(${interpolate(badgeProgress, [0, 1], [0.6, 1])})`,
            }}
          >
            <span
              style={{
                fontFamily: FONTS.sans,
                fontSize: 12,
                fontWeight: 600,
                color: controversyColor,
                letterSpacing: 0,
              }}
            >
              {UI_TEXT.controversy}
            </span>
            <span
              style={{
                fontFamily: FONTS.mono,
                fontSize: 24,
                fontWeight: 700,
                color: controversyColor,
              }}
            >
              {scoreNum.toFixed(1)}
            </span>
            <span
              style={{
                fontFamily: FONTS.sans,
                fontSize: 12,
                color: COLORS.textSecondary,
              }}
            >
              {UI_TEXT.scoreSuffix}
            </span>
            {(commentCount > 0 || heatScore > 0) && (
              <span
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: 12,
                  color: COLORS.textSecondary,
                  marginLeft: 4,
                }}
              >
                {commentCount > 0
                  ? `${UI_TEXT.comments} ${commentCount}`
                  : `${UI_TEXT.heat} ${heatScore}`}
              </span>
            )}
            <span
              style={{
                fontFamily: FONTS.sans,
                fontSize: 12,
                color: COLORS.textSecondary,
              }}
            >
              {controversyLabel}
            </span>
          </div>
        </div>

        {hasPie && (
          <StancePie
            distribution={stanceDistribution}
            size={198}
            centerLabel={commentCount > 0 ? `${commentCount}条评论` : undefined}
          />
        )}

        {hasFocus && (
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
              {UI_TEXT.debateFocus}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {debateFocus.map((focus, i) => {
                const tagProgress = spring({
                  frame,
                  fps,
                  config: { damping: 10, stiffness: 140 },
                  delay: 6 + i * 4,
                });

                return (
                  <div
                    key={focus}
                    style={{
                      fontFamily: FONTS.sans,
                      fontSize: 16,
                      fontWeight: 600,
                      color: COLORS.text,
                      opacity: tagProgress,
                      backgroundColor: "rgba(255,255,255,0.06)",
                      borderRadius: 12,
                      padding: "8px 14px",
                      lineHeight: 1.3,
                      transform: `translateY(${interpolate(tagProgress, [0, 1], [8, 0])}px)`,
                    }}
                  >
                    {focus}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

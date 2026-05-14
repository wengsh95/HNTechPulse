import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { ElementProps, p, stanceLabel, UI_TEXT } from "./utils";
import { StancePie, STANCE_COLORS } from "./StancePie";
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

const CONTROVERSY_COLORS = {
  green: "#34C759",
  yellow: "#FFD60A",
  red: "#FF453A",
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

function getMoodSummary(distribution: Record<string, number>, debateFocus: string[]) {
  const entries = Object.entries(distribution)
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1]);

  if (entries.length === 0) {
    return {
      title: "社区反应仍在形成",
      detail:
        debateFocus.length > 0
          ? `争议焦点：${debateFocus.join(" · ")}`
          : "评论区还没有形成清晰的观点分布。",
      dominant: "",
      percent: 0,
    };
  }

  const [dominant, value] = entries[0];
  const dominantLabel = stanceLabel(dominant);

  return {
    title: `${dominantLabel}是当前主调`,
    detail:
      debateFocus.length > 0
        ? `核心分歧：${debateFocus.join(" · ")}`
        : "评论区观点已经出现明显倾向。",
    dominant: dominantLabel,
    percent: Math.round(value * 100),
  };
}

function compactDistribution(distribution: Record<string, number>): Record<string, number> {
  const entries = Object.entries(distribution)
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1]);

  const top = entries.slice(0, 3);
  const rest = entries.slice(3).reduce((sum, [, value]) => sum + value, 0);
  return Object.fromEntries(rest > 0 ? [...top, ["其他", rest]] : top);
}

const MetricBar: React.FC<{
  label: string;
  valueLabel: string;
  helper?: string;
  progress: number;
  color: string;
  animProgress: number;
}> = ({ label, valueLabel, helper, progress, color, animProgress }) => {
  const fillWidth = interpolate(
    animProgress,
    [0, 1],
    [0, Math.max(0, Math.min(1, progress)) * 100],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    },
  );

  return (
    <div style={{ width: "100%" }}>
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: 16,
          marginBottom: 8,
        }}
      >
        <div
          style={{
            fontFamily: FONTS.sans,
            fontSize: 12,
            fontWeight: FW.bold,
            color: COLORS.textTertiary,
            textTransform: "uppercase",
            letterSpacing: 0.6,
          }}
        >
          {label}
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
          <span
            style={{
              fontFamily: FONTS.mono,
              fontSize: 26,
              fontWeight: FW.heavy,
              color: COLORS.text,
            }}
          >
            {valueLabel}
          </span>
          {helper && (
            <span
              style={{
                fontFamily: FONTS.sans,
                fontSize: 13,
                fontWeight: FW.bold,
                color,
              }}
            >
              {helper}
            </span>
          )}
        </div>
      </div>
      <div
        style={{
          position: "relative",
          width: "100%",
          height: 8,
          borderRadius: 4,
          overflow: "hidden",
          background: "rgba(255,255,255,0.08)",
        }}
      >
        <div
          style={{
            width: `${fillWidth}%`,
            height: "100%",
            borderRadius: 4,
            background: color,
          }}
        />
      </div>
    </div>
  );
};

export const AtmosphereCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();

  const stanceDistribution = (elementProps.stance_distribution as Record<string, number>) ?? {};
  const debateFocus = (elementProps.debate_focus as string[]) ?? [];

  const controversyScore = p(elementProps, "controversy_score", 0);
  const commentCount = Number(p(elementProps, "comment_count", 0)) || 0;
  const heatScore = Number(p(elementProps, "score", 0)) || 0;
  const scoreNum =
    typeof controversyScore === "number" ? controversyScore : Number(controversyScore) || 0;
  const controversyColor = getControversyColor(scoreNum);
  const controversyLabel = getControversyLabel(scoreNum);
  const mood = getMoodSummary(stanceDistribution, debateFocus);
  const dominantColor = STANCE_COLORS[mood.dominant] || COLORS.accentLight;
  const compactStances = compactDistribution(stanceDistribution);

  const hasPie = Object.keys(compactStances).length > 0;
  const hasFocus = debateFocus.length > 0;
  const compact = isCompactHeight(height);

  const cardW = width - LAYOUT.pageInset * 2;
  const cardMaxH = getCardMaxHeight(height);
  const topY = LAYOUT.topInset;

  const cardProgress = interpolate(frame, [4, 22], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const metricProgress = interpolate(frame, [14, 32], [0, 1], {
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
          display: "grid",
          gridTemplateColumns: compact ? "minmax(0, 1fr) 260px" : "minmax(0, 1fr) 300px",
          gap: compact ? 28 : 36,
          alignItems: "center",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div style={sectionLabel}>{UI_TEXT.discussionMood}</div>
          {mood.dominant && (
            <div
              style={{
                fontFamily: FONTS.sans,
                fontSize: 14,
                fontWeight: FW.heavy,
                color: COLORS.accentLight,
                marginBottom: 8,
              }}
            >
              社区主情绪：{mood.dominant}
            </div>
          )}
          <div
            style={{
              fontFamily: FONTS.bold,
              fontSize: compact ? 26 : 28,
              lineHeight: 1.18,
              fontWeight: FW.heavy,
              color: COLORS.text,
              marginBottom: compact ? 8 : 12,
            }}
          >
            {mood.title}
          </div>
          <div
            style={{
              fontFamily: FONTS.sans,
              fontSize: compact ? 17 : 18,
              lineHeight: compact ? 1.42 : 1.5,
              fontWeight: FW.regular,
              color: COLORS.textSecondary,
              marginBottom: mood.percent > 0 ? (compact ? 12 : 16) : 0,
            }}
          >
            {mood.detail}
          </div>

          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: compact ? 14 : 18,
              marginTop: compact ? 18 : 24,
              opacity: metricProgress,
              transform: `translateY(${interpolate(metricProgress, [0, 1], [10, 0])}px)`,
            }}
          >
            {mood.percent > 0 && (
              <MetricBar
                label="主导立场"
                valueLabel={`${mood.percent}%`}
                helper={mood.dominant}
                progress={mood.percent / 100}
                color={dominantColor}
                animProgress={metricProgress}
              />
            )}
            <MetricBar
              label={UI_TEXT.controversy}
              valueLabel={`${scoreNum.toFixed(1)} / 10`}
              helper={controversyLabel}
              progress={scoreNum / 10}
              color={controversyColor}
              animProgress={metricProgress}
            />
          </div>

          {hasFocus && (
            <div
              style={{
                marginTop: compact ? 18 : 24,
              }}
            >
              <div
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: 12,
                  fontWeight: FW.bold,
                  color: COLORS.textTertiary,
                  marginBottom: 10,
                  textTransform: "uppercase",
                  letterSpacing: 0.6,
                }}
              >
                {UI_TEXT.debateFocus}
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {debateFocus.slice(0, 3).map((focus, i) => {
                  const tagDelay = 12 + i * 5;
                  const tagProgress = interpolate(frame, [tagDelay, tagDelay + 16], [0, 1], {
                    easing: Easing.bezier(0.16, 1, 0.3, 1),
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                  });

                  return (
                    <div
                      key={focus}
                      style={{
                        fontFamily: FONTS.sans,
                        fontSize: compact ? 13 : 14,
                        fontWeight: FW.bold,
                        color: COLORS.text,
                        opacity: tagProgress,
                        backgroundColor: "rgba(255,255,255,0.06)",
                        border: "1px solid rgba(255,255,255,0.10)",
                        borderRadius: LAYOUT.chipRadius,
                        padding: compact ? "6px 10px" : "7px 12px",
                        lineHeight: 1.25,
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

        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            minWidth: 0,
            gap: compact ? 12 : 16,
          }}
        >
          {hasPie && (
            <StancePie
              distribution={compactStances}
              size={compact ? 142 : 158}
              centerLabel={commentCount > 0 ? `${commentCount}条` : undefined}
            />
          )}
          {commentCount <= 0 && heatScore > 0 && (
            <div
              style={{
                fontFamily: FONTS.sans,
                fontSize: 13,
                fontWeight: FW.bold,
                color: COLORS.textSecondary,
                padding: "7px 12px",
                borderRadius: LAYOUT.chipRadius,
                background: "rgba(255,255,255,0.06)",
                border: "1px solid rgba(255,255,255,0.10)",
              }}
            >
              热度 {heatScore}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

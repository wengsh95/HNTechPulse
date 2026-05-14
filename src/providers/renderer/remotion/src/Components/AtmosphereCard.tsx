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
  innerPanel,
  isCompactHeight,
  LAYOUT,
  S,
  sectionLabel,
} from "./design";

const CONTROVERSY_COLORS = {
  green: "#34C759",
  yellow: "#FFD60A",
  red: "#FF5A5F",
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

function getMoodSummary(distribution: Record<string, number>) {
  const entries = Object.entries(distribution)
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return { dominant: "", percent: 0 };
  const [dominant, value] = entries[0];
  return { dominant: stanceLabel(dominant), percent: Math.round(value * 100) };
}

function compactDistribution(distribution: Record<string, number>): Record<string, number> {
  const entries = Object.entries(distribution)
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1]);
  const top = entries.slice(0, 3);
  const rest = entries.slice(3).reduce((sum, [, value]) => sum + value, 0);
  return Object.fromEntries(rest > 0 ? [...top, ["其他", rest]] : top);
}

/** Small circular progress ring for controversy score. */
const ProgressRing: React.FC<{ score: number; color: string }> = ({ score, color }) => {
  const ringSize = 56;
  const strokeW = 5;
  const r = (ringSize - strokeW) / 2;
  const cx = ringSize / 2;
  const cy = ringSize / 2;
  const circ = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(10, score));
  const offset = circ * (1 - clamped / 10);

  return (
    <svg width={ringSize} height={ringSize} style={{ display: "block", flexShrink: 0 }}>
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke="rgba(255,255,255,0.08)"
        strokeWidth={strokeW}
      />
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={strokeW}
        strokeLinecap="round"
        strokeDasharray={circ}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${cx} ${cy})`}
      />
    </svg>
  );
};

/** Vertical bar chart for stance distribution. */
const StanceColumnChart: React.FC<{
  distribution: Record<string, number>;
}> = ({ distribution }) => {
  const entries = Object.entries(distribution)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);

  if (entries.length === 0) return null;

  const barMaxH = 72;
  const barW = 22;
  const barGap = 28;
  const maxPct = Math.max(...entries.map(([, v]) => v));

  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: barGap, height: barMaxH + 42 }}>
      {entries.map(([label, value]) => {
        const pct = Math.round(value * 100);
        const barH = Math.max(4, (value / maxPct) * barMaxH);
        const color = STANCE_COLORS[label] || COLORS.textSecondary;

        return (
          <div
            key={label}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span
              style={{
                fontFamily: FONTS.mono,
                fontSize: 11,
                fontWeight: FW.heavy,
                color: COLORS.textSecondary,
                lineHeight: 1,
              }}
            >
              {pct}%
            </span>
            <div
              style={{
                width: barW,
                height: barH,
                borderRadius: "4px 4px 0 0",
                background: color,
              }}
            />
            <span
              style={{
                fontFamily: FONTS.sans,
                fontSize: 11,
                fontWeight: FW.medium,
                color: COLORS.textSecondary,
                lineHeight: 1,
                maxWidth: barW + 12,
                textAlign: "center",
                whiteSpace: "nowrap",
              }}
            >
              {label}
            </span>
          </div>
        );
      })}
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
  const mood = getMoodSummary(stanceDistribution);
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

  const pY = compact ? 22 : 28;
  const pX = compact ? 24 : 32;
  const gap = compact ? 16 : 24;

  return (
    <div
      style={{
        ...S,
        left: LAYOUT.pageInset,
        top: topY,
        width: cardW,
        maxHeight: cardMaxH,
        ...glassCard,
        padding: `${pY}px ${pX}px`,
        boxShadow: glassCardShadow,
        boxSizing: "border-box",
        overflow: "hidden",
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [28, 0])}px)`,
      }}
    >
      {/* === Section label === */}
      <div style={sectionLabel}>{UI_TEXT.discussionMood}</div>

      {/* === Row 1: metric cards (left) + large donut (right) === */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: compact
            ? "minmax(0, 0.45fr) minmax(0, 1fr)"
            : "minmax(0, 0.42fr) minmax(0, 1fr)",
          gap,
          alignItems: "stretch",
          opacity: metricProgress,
          transform: `translateY(${interpolate(metricProgress, [0, 1], [12, 0])}px)`,
          marginBottom: gap,
        }}
      >
        {/* Left: metric cards stacked vertically */}
        <div style={{ display: "flex", flexDirection: "column", gap: compact ? 10 : 14 }}>
          {/* Controversy card */}
          <div
            style={{
              ...innerPanel,
              padding: compact ? "14px" : "16px",
              display: "flex",
              alignItems: "center",
              gap: compact ? 12 : 16,
              flex: 1,
            }}
          >
            <ProgressRing score={scoreNum} color={controversyColor} />
            <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
              <div
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: 11,
                  fontWeight: FW.bold,
                  color: COLORS.textTertiary,
                  textTransform: "uppercase",
                  letterSpacing: 0.5,
                }}
              >
                {UI_TEXT.controversy}
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 3 }}>
                <span
                  style={{
                    fontFamily: FONTS.mono,
                    fontSize: compact ? 24 : 28,
                    fontWeight: FW.heavy,
                    color: COLORS.text,
                    lineHeight: 1,
                  }}
                >
                  {scoreNum.toFixed(1)}
                </span>
                <span
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: 13,
                    fontWeight: FW.medium,
                    color: COLORS.textSecondary,
                  }}
                >
                  /10
                </span>
              </div>
              <span
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: 12,
                  fontWeight: FW.bold,
                  color: controversyColor,
                }}
              >
                {controversyLabel}
              </span>
            </div>
          </div>

          {/* Dominant mood card */}
          {mood.dominant && (
            <div
              style={{
                ...innerPanel,
                padding: compact ? "14px" : "16px",
                display: "flex",
                alignItems: "center",
                gap: compact ? 10 : 14,
                flex: 1,
              }}
            >
              <span
                style={{
                  display: "inline-block",
                  width: compact ? 28 : 32,
                  height: compact ? 28 : 32,
                  borderRadius: "50%",
                  backgroundColor: dominantColor,
                  flexShrink: 0,
                }}
              />
              <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
                <div
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: 11,
                    fontWeight: FW.bold,
                    color: COLORS.textTertiary,
                    textTransform: "uppercase",
                    letterSpacing: 0.5,
                  }}
                >
                  主导情绪
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                  <span
                    style={{
                      fontFamily: FONTS.sans,
                      fontSize: compact ? 16 : 18,
                      fontWeight: FW.heavy,
                      color: COLORS.text,
                      lineHeight: 1,
                    }}
                  >
                    {mood.dominant}
                  </span>
                  <span
                    style={{
                      fontFamily: FONTS.mono,
                      fontSize: compact ? 20 : 24,
                      fontWeight: FW.heavy,
                      color: dominantColor,
                      lineHeight: 1,
                    }}
                  >
                    {mood.percent}%
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right: large donut chart */}
        <div
          style={{
            ...innerPanel,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            minWidth: 0,
          }}
        >
          {hasPie ? (
            <StancePie
              distribution={compactStances}
              size={compact ? 180 : 240}
              centerLabel={commentCount > 0 ? `${commentCount}条` : undefined}
            />
          ) : (
            heatScore > 0 && (
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
            )
          )}
        </div>
      </div>

      {/* === Row 2: stance bar chart (left) + debate focus (right) === */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: compact
            ? "minmax(0, 0.45fr) minmax(0, 1fr)"
            : "minmax(0, 0.42fr) minmax(0, 1fr)",
          gap,
          alignItems: "start",
          opacity: metricProgress,
          marginBottom: gap,
        }}
      >
        {/* Left: stance distribution column chart */}
        <div style={{ ...innerPanel, padding: compact ? "14px" : "16px" }}>
          <div
            style={{
              fontFamily: FONTS.sans,
              fontSize: 11,
              fontWeight: FW.bold,
              color: COLORS.textTertiary,
              textTransform: "uppercase",
              letterSpacing: 0.5,
              marginBottom: compact ? 10 : 14,
            }}
          >
            立场分布
          </div>
          <StanceColumnChart distribution={stanceDistribution} />
        </div>

        {/* Right: debate focus */}
        <div style={{ ...innerPanel, padding: compact ? "14px" : "16px" }}>
          <div
            style={{
              fontFamily: FONTS.sans,
              fontSize: 11,
              fontWeight: FW.bold,
              color: COLORS.textTertiary,
              textTransform: "uppercase",
              letterSpacing: 0.5,
              marginBottom: compact ? 10 : 14,
            }}
          >
            {UI_TEXT.debateFocus}
          </div>
          {hasFocus ? (
            <div style={{ display: "flex", flexDirection: "column", gap: compact ? 8 : 10 }}>
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
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      fontFamily: FONTS.sans,
                      fontSize: compact ? 13 : 14,
                      fontWeight: FW.bold,
                      color: COLORS.text,
                      opacity: tagProgress,
                      background: "rgba(255,255,255,0.05)",
                      border: "1px solid rgba(255,255,255,0.10)",
                      borderRadius: 8,
                      padding: compact ? "10px 14px" : "12px 16px",
                      lineHeight: 1.35,
                      transform: `translateY(${interpolate(tagProgress, [0, 1], [8, 0])}px)`,
                    }}
                  >
                    <span
                      style={{
                        fontFamily: FONTS.mono,
                        fontSize: 12,
                        fontWeight: FW.heavy,
                        color: COLORS.accentLight,
                        opacity: 0.7,
                        flexShrink: 0,
                      }}
                    >
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span>{focus}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div
              style={{
                fontFamily: FONTS.sans,
                fontSize: 13,
                fontWeight: FW.medium,
                color: COLORS.textTertiary,
                padding: "24px 0",
                textAlign: "center",
              }}
            >
              暂无数据
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

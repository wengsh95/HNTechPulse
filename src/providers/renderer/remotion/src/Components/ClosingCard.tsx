/* ================================================================
   ClosingCard — 结束卡 (Warm Paper Theme)
   ================================================================

   Layout: single-column centered vertical
     - Signal tag (pill badge)
     - Summary statement (large headline)
     - Keyword tags row
     - Progress section (title + stacked bar)
     - Completed stories list (✓ check + category + title)
     - Stats row (stories / points / comments)
     - Vibe tag

   Adapted for Remotion: accepts ElementProps, uses useTheme() for scaling,
   adds entrance animation via useCurrentFrame/interpolate.
*/

import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import type { ClosingCardProps, CompletedStory } from "./cardTypes";
import { COLORS, TYPOGRAPHY, CARD_REF, useTheme } from "./theme";
import type { ElementProps } from "./utils";
import { extractClosingProps } from "./propsExtractors";

/* ---- inline-styles object ---- */

function buildStyles(scaled: (px: number) => number) {
  return {
    card: {
      width: scaled(CARD_REF.width),
      height: "100%" as const,
      background: COLORS.bg,
      position: "relative" as const,
      overflow: "hidden",
    } as React.CSSProperties,
    inner: {
      padding: `${scaled(80)}px ${scaled(140)}px`,
      height: "100%",
      display: "flex",
      flexDirection: "column" as const,
      justifyContent: "center",
      alignItems: "flex-start",
      textAlign: "left" as const,
      gap: scaled(48),
    } as React.CSSProperties,

    /* ---- signal tag ---- */
    signalTag: {
      display: "inline-flex",
      alignItems: "center",
      gap: scaled(8),
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(15),
      fontWeight: 700,
      letterSpacing: "0.2em",
      textTransform: "uppercase" as const,
      padding: `${scaled(8)}px ${scaled(24)}px`,
      borderRadius: scaled(999),
      background: COLORS.brownBg,
      color: COLORS.warmBrown,
      border: `1px solid #d4b896`,
    } as React.CSSProperties,
    signalDot: {
      width: scaled(8),
      height: scaled(8),
      borderRadius: "50%",
      background: COLORS.warmBrown,
    } as React.CSSProperties,

    /* ---- summary ---- */
    summary: {
      fontSize: scaled(72),
      fontWeight: 900,
      lineHeight: 1.2,
      letterSpacing: "-0.015em",
      color: COLORS.fg,
      maxWidth: scaled(1400),
    } as React.CSSProperties,

    /* ---- keywords ---- */
    keywords: {
      display: "flex",
      gap: scaled(14),
      flexWrap: "wrap" as const,
    } as React.CSSProperties,
    kw: {
      display: "inline-flex",
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(15),
      fontWeight: 700,
      padding: `${scaled(8)}px ${scaled(22)}px`,
      borderRadius: scaled(6),
      border: `1.5px solid ${COLORS.warmBrown}`,
      color: COLORS.warmBrown,
      letterSpacing: "0.06em",
    } as React.CSSProperties,

    /* ---- progress ---- */
    progressSection: {
      width: "100%",
      maxWidth: scaled(800),
      display: "flex",
      flexDirection: "column" as const,
      gap: scaled(14),
    } as React.CSSProperties,
    progressTitle: {
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(16),
      fontWeight: 700,
      letterSpacing: "0.15em",
      textTransform: "uppercase" as const,
      color: COLORS.warmGold,
      display: "flex",
      alignItems: "center",
      justifyContent: "flex-start",
      gap: scaled(10),
    } as React.CSSProperties,
    progressTitleStrong: {
      color: COLORS.fg,
      fontSize: scaled(22),
      fontWeight: 700,
    } as React.CSSProperties,
    progressBar: {
      display: "flex",
      gap: 0,
      height: scaled(14),
      borderRadius: scaled(7),
      overflow: "hidden",
    } as React.CSSProperties,
    progFocus: (pct: number) =>
      ({
        height: "100%",
        width: `${pct}%`,
        background: COLORS.warmBrown,
      }) as React.CSSProperties,
    progAtmo: (pct: number) =>
      ({
        height: "100%",
        width: `${pct}%`,
        background: COLORS.warmGold,
      }) as React.CSSProperties,
    progRemain: (pct: number) =>
      ({
        height: "100%",
        width: `${pct}%`,
        background: COLORS.surface2,
      }) as React.CSSProperties,

    /* ---- completed stories ---- */
    doneList: {
      display: "flex",
      flexDirection: "column" as const,
      gap: scaled(12),
      width: "100%",
      maxWidth: scaled(700),
    } as React.CSSProperties,
    doneItem: {
      display: "flex",
      alignItems: "center",
      gap: scaled(14),
      fontSize: scaled(20),
      color: COLORS.muted,
    } as React.CSSProperties,
    doneCheck: {
      fontFamily: TYPOGRAPHY.fontMono,
      color: COLORS.sage,
      fontWeight: 900,
      fontSize: scaled(18),
    } as React.CSSProperties,
    doneCat: {
      display: "inline-flex",
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(12),
      fontWeight: 700,
      letterSpacing: "0.1em",
      padding: `${scaled(2)}px ${scaled(10)}px`,
      borderRadius: scaled(4),
      border: `1px solid ${COLORS.border}`,
      color: COLORS.dim,
    } as React.CSSProperties,
    doneTitle: {
      color: COLORS.fg,
      fontWeight: 600,
    } as React.CSSProperties,

    /* ---- stats row ---- */
    statsRow: {
      display: "flex",
      alignItems: "center",
      gap: scaled(28),
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(18),
      color: COLORS.dim,
    } as React.CSSProperties,
    statsStrong: {
      color: COLORS.warmGold,
      fontSize: scaled(26),
      fontWeight: 700,
    } as React.CSSProperties,
    statsSep: {
      color: COLORS.border,
    } as React.CSSProperties,

    /* ---- vibe tag ---- */
    vibeTag: {
      display: "inline-flex",
      alignItems: "center",
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(13),
      fontWeight: 600,
      letterSpacing: "0.14em",
      textTransform: "uppercase" as const,
      padding: `${scaled(6)}px ${scaled(20)}px`,
      borderRadius: scaled(999),
      background: COLORS.goldBg,
      color: COLORS.warmGold,
      border: `1px solid #c4a870`,
    } as React.CSSProperties,
  };
}

/* ---- sub-components ---- */

function StoryItem({
  story,
  S,
}: {
  story: CompletedStory;
  S: ReturnType<typeof buildStyles>;
}) {
  return (
    <div style={S.doneItem}>
      <span style={S.doneCheck}>✓</span>
      {story.category && <span style={S.doneCat}>{story.category}</span>}
      <span style={S.doneTitle}>{story.title}</span>
    </div>
  );
}

/* ---- main component ---- */

export const ClosingCard: React.FC<ElementProps> = ({
  elementProps,
  width,
  height,
}) => {
  const frame = useCurrentFrame();
  const d = useTheme();
  const S = buildStyles(d.scaled);

  const typed = extractClosingProps(elementProps);
  const {
    signalLabel,
    summary,
    keywords,
    progressDone,
    progressTotal,
    focusPct,
    atmospherePct,
    completedStories,
    stats,
    vibe,
  } = typed;

  const remainPct = Math.max(0, 100 - focusPct - atmospherePct);

  // Entrance animation
  const cardProgress = interpolate(frame, [4, 22], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleProgress = interpolate(frame, [8, 26], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyProgress = interpolate(frame, [14, 32], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        ...S.card,
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [32, 0])}px)`,
      }}
    >
      <div style={S.inner}>
        {/* Signal tag */}
        <div
          style={{
            ...S.signalTag,
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [24, 0])}px)`,
          }}
        >
          <span style={S.signalDot} />
          {signalLabel}
        </div>

        {/* Summary */}
        {summary && (
          <h1
            style={{
              ...S.summary,
              opacity: titleProgress,
              transform: `translateY(${interpolate(titleProgress, [0, 1], [28, 0])}px)`,
            }}
          >
            {summary}
          </h1>
        )}

        {/* Keywords */}
        {keywords.length > 0 && (
          <div
            style={{
              ...S.keywords,
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [12, 0])}px)`,
            }}
          >
            {keywords.map((k) => (
              <span key={k} style={S.kw}>
                {k}
              </span>
            ))}
          </div>
        )}

        {/* Progress bar */}
        {progressTotal > 0 && (
          <div
            style={{
              ...S.progressSection,
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [12, 0])}px)`,
            }}
          >
            <div style={S.progressTitle}>
              今日脉络
              <strong style={S.progressTitleStrong}>
                {progressDone} / {progressTotal}
              </strong>
              已完成
            </div>
            <div style={S.progressBar}>
              <div style={S.progFocus(focusPct)} />
              <div style={S.progAtmo(atmospherePct)} />
              {remainPct > 0 && <div style={S.progRemain(remainPct)} />}
            </div>
          </div>
        )}

        {/* Completed stories */}
        {completedStories.length > 0 && (
          <div
            style={{
              ...S.doneList,
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [12, 0])}px)`,
            }}
          >
            {completedStories.map((s, i) => (
              <StoryItem key={i} story={s} S={S} />
            ))}
          </div>
        )}

        {/* Stats row */}
        <div
          style={{
            ...S.statsRow,
            opacity: bodyProgress,
            transform: `translateY(${interpolate(bodyProgress, [0, 1], [12, 0])}px)`,
          }}
        >
          <span>
            <strong style={S.statsStrong}>{stats.storyCount}</strong> 条主线
          </span>
          <span style={S.statsSep}>/</span>
          <span>
            <strong style={S.statsStrong}>
              {stats.points.toLocaleString()}
            </strong>{" "}
            points
          </span>
          <span style={S.statsSep}>/</span>
          <span>
            <strong style={S.statsStrong}>
              {stats.comments.toLocaleString()}
            </strong>{" "}
            comments
          </span>
        </div>

        {/* Vibe tag */}
        {vibe && (
          <div
            style={{
              ...S.vibeTag,
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [18, 0])}px)`,
            }}
          >
            {vibe}
          </div>
        )}
      </div>
    </div>
  );
};

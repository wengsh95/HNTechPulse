/* ================================================================
   CoverCard — 封面卡 (Warm Paper Theme)
   ================================================================

   Layout: single-column vertical
     - SectionLabel (mono, amber dot)
     - Headline (display, 96px)
     - Divider
     - Highlights list (rank badge + title + metric pills + subtitle)

   Adapted for Remotion: accepts ElementProps, uses useTheme() for scaling,
   adds subtle entrance animation via useCurrentFrame/interpolate.
*/

import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import type { CoverCardProps, Highlight } from "./cardTypes";
import { COLORS, TYPOGRAPHY, CARD_REF, useTheme } from "./theme";
import type { ElementProps } from "./utils";
import { extractCoverProps } from "./propsExtractors";

/* ---- sub-component styles ---- */

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
      padding: `${scaled(80)}px ${scaled(CARD_REF.width > 0 ? 100 : 0)}px`,
      height: "100%",
      display: "flex",
      flexDirection: "column" as const,
      justifyContent: "center" as const,
      gap: scaled(52),
    } as React.CSSProperties,
    sectionLabel: {
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(14),
      fontWeight: 600,
      letterSpacing: "0.28em",
      textTransform: "uppercase" as const,
      color: COLORS.warmGold,
      paddingLeft: scaled(20),
      position: "relative" as const,
    } as React.CSSProperties,
    dot: {
      position: "absolute" as const,
      left: 0,
      top: "50%",
      transform: "translateY(-50%)",
      width: scaled(8),
      height: scaled(8),
      borderRadius: "50%",
      background: COLORS.warmBrown,
    } as React.CSSProperties,
    headline: {
      fontSize: scaled(96),
      fontWeight: 900,
      lineHeight: 1.1,
      letterSpacing: "-0.02em",
      color: COLORS.fg,
      maxWidth: scaled(1500),
    } as React.CSSProperties,
    divider: {
      width: "100%",
      maxWidth: scaled(900),
      height: scaled(6),
      borderRadius: scaled(3),
      background: `linear-gradient(90deg, ${COLORS.warmBrown}, ${COLORS.warmGold}99, transparent)`,
    } as React.CSSProperties,
    highlights: {
      display: "flex",
      flexDirection: "column" as const,
      gap: scaled(24),
      width: "100%",
    } as React.CSSProperties,
    hlItem: {
      display: "flex",
      alignItems: "center",
      gap: scaled(28),
      padding: `${scaled(20)}px 0`,
    } as React.CSSProperties,
    hlBadge: (rank: number) =>
      ({
        width: scaled(52),
        height: scaled(52),
        borderRadius: scaled(8),
        background:
          rank === 1
            ? COLORS.warmBrown
            : rank === 2
              ? COLORS.warmGold
              : COLORS.dim,
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: scaled(22),
        fontWeight: 900,
        fontFamily: TYPOGRAPHY.fontMono,
        flexShrink: 0,
      }) as React.CSSProperties,
    hlBody: {
      flex: 1,
      display: "flex",
      flexDirection: "column" as const,
      gap: scaled(8),
    } as React.CSSProperties,
    hlTitle: {
      fontSize: scaled(28),
      fontWeight: 700,
      lineHeight: 1.3,
      color: COLORS.fg,
    } as React.CSSProperties,
    hlMeta: {
      display: "flex",
      alignItems: "center",
      gap: scaled(16),
      flexWrap: "wrap" as const,
    } as React.CSSProperties,
    pill: (color: string, bg: string) =>
      ({
        display: "inline-flex",
        alignItems: "center",
        gap: scaled(4),
        fontFamily: TYPOGRAPHY.fontMono,
        fontSize: scaled(14),
        fontWeight: 600,
        padding: `${scaled(4)}px ${scaled(12)}px`,
        borderRadius: scaled(999),
        background: bg,
        color,
      }) as React.CSSProperties,
    originalTitle: {
      fontSize: scaled(16),
      color: COLORS.dim,
      fontFamily: TYPOGRAPHY.fontMono,
    } as React.CSSProperties,
  };
}

/* ---- helpers ---- */

function HighlightRow({
  h,
  S,
}: {
  h: Highlight;
  S: ReturnType<typeof buildStyles>;
}) {
  return (
    <div style={S.hlItem}>
      <div style={S.hlBadge(h.rank)}>{h.rank}</div>
      <div style={S.hlBody}>
        <div style={S.hlTitle}>{h.editorAngle}</div>
        <div style={S.hlMeta}>
          <span style={S.pill(COLORS.warmBrown, COLORS.brownBg)}>
            &#x1F525; {h.hnScore.toLocaleString()}
          </span>
          <span style={S.pill(COLORS.warmGold, COLORS.goldBg)}>
            &#x1F4AC; {h.commentCount.toLocaleString()}
          </span>
          {h.originalTitle && (
            <span style={S.originalTitle}>{h.originalTitle}</span>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---- main component ---- */

export const CoverCard: React.FC<ElementProps> = ({
  elementProps,
  width,
  height,
}) => {
  const frame = useCurrentFrame();
  const d = useTheme();

  const typed = extractCoverProps(elementProps);
  const { headline, dateLabel, categories, highlights } = typed;
  const hasHighlights = highlights.length > 0;
  const S = buildStyles(d.scaled);

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
        {/* Section label */}
        <span style={S.sectionLabel}>
          <span style={S.dot} />
          {dateLabel}
        </span>

        {/* Headline */}
        <h1
          style={{
            ...S.headline,
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [28, 0])}px)`,
          }}
        >
          {headline}
        </h1>

        {/* Category count bar */}
        {categories.length > 0 && (
          <div
            style={{
              opacity: bodyProgress,
              display: "flex",
              gap: d.scaled(4),
              height: d.scaled(6),
              maxWidth: d.scaled(900),
            }}
          >
            {categories.map((c) => (
              <div
                key={c.label}
                style={{
                  flex: c.flex,
                  height: "100%",
                  borderRadius: d.scaled(3),
                  background:
                    c.color === "red"
                      ? COLORS.warmBrown
                      : c.color === "amber"
                        ? COLORS.warmGold
                        : COLORS.dim,
                }}
              />
            ))}
          </div>
        )}

        {/* Highlights */}
        {hasHighlights && (
          <div
            style={{
              ...S.highlights,
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [10, 0])}px)`,
            }}
          >
            {highlights.map((h) => (
              <HighlightRow key={h.rank} h={h} S={S} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

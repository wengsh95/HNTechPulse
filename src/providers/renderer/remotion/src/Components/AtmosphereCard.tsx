/* ================================================================
   AtmosphereCard — 社区回声卡 (Warm Paper Theme)
   ================================================================

   Layout: single-column vertical
     - Controversy score row (score + level tag + total comments)
     - Debate topics (left) + stance distribution bars (right) — two columns
     - Quoted opinions (stripe + quote text + author + likes)

   Adapted for Remotion: accepts ElementProps, uses useTheme() for scaling,
   adds entrance animation via useCurrentFrame/interpolate.
*/

import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import type {
  AtmosphereCardProps,
  ControversyLevel,
  Stance,
  Quote,
} from "./cardTypes";
import { COLORS, TYPOGRAPHY, CARD_REF, useTheme } from "./theme";
import type { ElementProps } from "./utils";
import { extractAtmosphereProps } from "./propsExtractors";

/* ---- label maps ---- */

const CONTROVERSY_LABELS: Record<ControversyLevel, string> = {
  consensus: "共识较强",
  divided: "存在分歧",
  highly_controversial: "高度争议",
};

const STANCE_LABELS: Record<Stance, string> = {
  support: "支持",
  skeptic: "质疑",
  neutral: "中立",
  tease: "调侃",
  worry: "担忧",
};

const STANCE_COLORS: Record<Stance, string> = {
  support: COLORS.sage,
  skeptic: COLORS.warmGold,
  neutral: COLORS.dim,
  tease: COLORS.purple,
  worry: COLORS.warmBrown,
};

const STANCE_ORDER: Stance[] = [
  "support",
  "skeptic",
  "neutral",
  "tease",
  "worry",
];

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
      padding: `${scaled(80)}px ${scaled(100)}px`,
      height: "100%",
      display: "flex",
      flexDirection: "column" as const,
      justifyContent: "center" as const,
      gap: scaled(42),
    } as React.CSSProperties,
    /* ---- score row ---- */
    scoreRow: {
      display: "flex",
      alignItems: "center",
      gap: scaled(24),
    } as React.CSSProperties,
    score: {
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(72),
      fontWeight: 900,
      lineHeight: 1,
      color: COLORS.fg,
    } as React.CSSProperties,
    scoreSlash: {
      fontSize: scaled(42),
      color: COLORS.dim,
      fontWeight: 300,
    } as React.CSSProperties,
    levelTag: {
      display: "inline-flex",
      alignItems: "center",
      gap: scaled(8),
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(15),
      fontWeight: 700,
      letterSpacing: "0.1em",
      padding: `${scaled(8)}px ${scaled(22)}px`,
      borderRadius: scaled(999),
      background: COLORS.brownBg,
      color: COLORS.warmBrown,
      border: `1px solid #d4b896`,
    } as React.CSSProperties,
    levelDot: {
      width: scaled(9),
      height: scaled(9),
      borderRadius: "50%",
      background: COLORS.warmBrown,
    } as React.CSSProperties,
    commentsCount: {
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(17),
      color: COLORS.dim,
      display: "flex",
      alignItems: "center",
      gap: scaled(8),
      marginLeft: "auto",
    } as React.CSSProperties,
    commentsCountStrong: {
      color: COLORS.warmGold,
      fontSize: scaled(28),
      fontWeight: 700,
    } as React.CSSProperties,

    /* ---- two-column section ---- */
    twoCol: {
      display: "flex",
      gap: scaled(80),
    } as React.CSSProperties,
    debateCol: {
      flex: `0 0 ${scaled(540)}px`,
      display: "flex",
      flexDirection: "column" as const,
      gap: scaled(20),
    } as React.CSSProperties,
    sectionTitle: {
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(15),
      fontWeight: 700,
      letterSpacing: "0.15em",
      textTransform: "uppercase" as const,
      color: COLORS.warmGold,
      marginBottom: scaled(6),
    } as React.CSSProperties,
    debateItem: {
      display: "flex",
      gap: scaled(14),
      alignItems: "flex-start" as const,
    } as React.CSSProperties,
    debateNum: {
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(20),
      fontWeight: 800,
      color: COLORS.warmBrown,
      flexShrink: 0,
      width: scaled(36),
      textAlign: "right" as const,
    } as React.CSSProperties,
    debateText: {
      fontSize: scaled(24),
      fontWeight: 600,
      lineHeight: 1.4,
      color: COLORS.fg,
    } as React.CSSProperties,

    /* ---- stance column ---- */
    stanceCol: {
      flex: 1,
      display: "flex",
      flexDirection: "column" as const,
      gap: scaled(18),
    } as React.CSSProperties,
    stanceRow: {
      display: "flex",
      alignItems: "center",
      gap: scaled(14),
    } as React.CSSProperties,
    stanceLabel: {
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(14),
      fontWeight: 600,
      width: scaled(60),
      textAlign: "right" as const,
      color: COLORS.muted,
    } as React.CSSProperties,
    stanceTrack: {
      flex: 1,
      height: scaled(22),
      background: COLORS.surface2,
      borderRadius: scaled(4),
      overflow: "hidden",
      position: "relative" as const,
    } as React.CSSProperties,
    stanceFill: (pct: number, color: string) =>
      ({
        height: "100%",
        borderRadius: scaled(4),
        transition: "width 1.2s ease",
        width: `${pct}%`,
        background: color,
      }) as React.CSSProperties,
    stancePct: {
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(14),
      fontWeight: 700,
      width: scaled(48),
      color: COLORS.fg,
    } as React.CSSProperties,

    /* ---- quotes ---- */
    quotesList: {
      display: "flex",
      flexDirection: "column" as const,
      gap: scaled(18),
      maxWidth: scaled(1400),
    } as React.CSSProperties,
    quoteItem: {
      display: "flex",
      gap: scaled(16),
      padding: `${scaled(18)}px 0`,
      borderBottom: `1px solid ${COLORS.border}`,
    } as React.CSSProperties,
    quoteLast: {
      display: "flex",
      gap: scaled(16),
      padding: `${scaled(18)}px 0`,
    } as React.CSSProperties,
    quoteStripe: (color: string) =>
      ({
        width: scaled(4),
        borderRadius: scaled(2),
        flexShrink: 0,
        background: color,
      }) as React.CSSProperties,
    quoteBody: {
      display: "flex",
      flexDirection: "column" as const,
      gap: scaled(8),
    } as React.CSSProperties,
    quoteText: {
      fontSize: scaled(22),
      lineHeight: 1.5,
      color: COLORS.fg,
      fontStyle: "italic",
    } as React.CSSProperties,
    quoteAuthor: {
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(14),
      color: COLORS.dim,
      display: "flex",
      alignItems: "center",
      gap: scaled(10),
    } as React.CSSProperties,
    quoteLikes: {
      color: COLORS.warmGold,
      fontWeight: 600,
    } as React.CSSProperties,
  };
}

/* ---- sub-components ---- */

function StanceBar({
  stance,
  pct,
  S,
}: {
  stance: Stance;
  pct: number;
  S: ReturnType<typeof buildStyles>;
}) {
  const color = STANCE_COLORS[stance];
  return (
    <div style={S.stanceRow}>
      <span style={S.stanceLabel}>{STANCE_LABELS[stance]}</span>
      <div style={S.stanceTrack}>
        <div style={S.stanceFill(pct, color)} />
      </div>
      <span style={S.stancePct}>{pct}%</span>
    </div>
  );
}

function QuoteBlock({
  q,
  last,
  S,
}: {
  q: Quote;
  last: boolean;
  S: ReturnType<typeof buildStyles>;
}) {
  const color = STANCE_COLORS[q.stance];
  return (
    <div style={last ? S.quoteLast : S.quoteItem}>
      <div style={S.quoteStripe(color)} />
      <div style={S.quoteBody}>
        <div style={S.quoteText}>&ldquo;{q.text}&rdquo;</div>
        <div style={S.quoteAuthor}>
          {q.author}
          <span style={S.quoteLikes}>&#x1F44D; {q.likes}</span>
        </div>
      </div>
    </div>
  );
}

/* ---- main component ---- */

export const AtmosphereCard: React.FC<ElementProps> = ({
  elementProps,
  width,
  height,
}) => {
  const frame = useCurrentFrame();
  const d = useTheme();
  const S = buildStyles(d.scaled);

  const typed = extractAtmosphereProps(elementProps);
  const {
    controversyScore,
    controversyLevel,
    debateTopics,
    stanceDistribution,
    totalComments,
    quotes,
  } = typed;

  // Compute percentages for stance bars
  const totalStance =
    stanceDistribution.support +
    stanceDistribution.skeptic +
    stanceDistribution.neutral +
    stanceDistribution.tease +
    stanceDistribution.worry;

  const stancePcts: Record<Stance, number> = {
    support: totalStance > 0 ? Math.round((stanceDistribution.support / totalStance) * 100) : 0,
    skeptic: totalStance > 0 ? Math.round((stanceDistribution.skeptic / totalStance) * 100) : 0,
    neutral: totalStance > 0 ? Math.round((stanceDistribution.neutral / totalStance) * 100) : 0,
    tease: totalStance > 0 ? Math.round((stanceDistribution.tease / totalStance) * 100) : 0,
    worry: totalStance > 0 ? Math.round((stanceDistribution.worry / totalStance) * 100) : 0,
  };

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
        {/* Score row */}
        <div
          style={{
            ...S.scoreRow,
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [10, 0])}px)`,
          }}
        >
          <span style={S.score}>
            {controversyScore.toFixed(1)}
            <span style={S.scoreSlash}>/10</span>
          </span>
          <span style={S.levelTag}>
            <span style={S.levelDot} />
            {CONTROVERSY_LABELS[controversyLevel]}
          </span>
          <span style={S.commentsCount}>
            评论总数{" "}
            <strong style={S.commentsCountStrong}>
              {totalComments.toLocaleString()}
            </strong>
          </span>
        </div>

        {/* Debate + Stance two-column */}
        <div
          style={{
            ...S.twoCol,
            opacity: bodyProgress,
            transform: `translateY(${interpolate(bodyProgress, [0, 1], [12, 0])}px)`,
          }}
        >
          <div style={S.debateCol}>
            <h3 style={S.sectionTitle}>辩论焦点</h3>
            {debateTopics.map((topic, i) => (
              <div key={i} style={S.debateItem}>
                <span style={S.debateNum}>{i + 1}.</span>
                <span style={S.debateText}>{topic}</span>
              </div>
            ))}
            {debateTopics.length === 0 && (
              <span style={{ color: COLORS.dim, fontSize: d.scaled(20) }}>
                暂无显著辩论焦点
              </span>
            )}
          </div>

          <div style={S.stanceCol}>
            <h3 style={S.sectionTitle}>立场分布</h3>
            {STANCE_ORDER.map((s) => (
              <StanceBar key={s} stance={s} pct={stancePcts[s]} S={S} />
            ))}
          </div>
        </div>

        {/* Quotes */}
        {quotes.length > 0 && (
          <div
            style={{
              ...S.quotesList,
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [12, 0])}px)`,
            }}
          >
            {quotes.map((q, i) => (
              <QuoteBlock
                key={i}
                q={q}
                last={i === quotes.length - 1}
                S={S}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

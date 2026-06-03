/* ================================================================
   AtmosphereCard — 社区回声卡 (Warm Paper Theme)
   ================================================================

   Layout: four sections top-to-bottom
     ① Discussion summary + controversy level tag
     ② Debate topics (left) + stance distribution with concerns (right)
     ③ Quoted opinions (stripe + quote text + author + stance label)

   Adapted for Remotion: accepts ElementProps, uses useDesign() for scaling,
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
import { COLORS } from "./theme";
import type { ElementProps } from "./utils";
import { extractAtmosphereProps } from "./propsExtractors";
import { useDesign, FONTS, FW, ANIM, EASE_CARD, CARD_LAYOUT } from "./design";
import { CardShell, Fill } from "./CardShell";

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

/** Only the 3 core stances rendered on the card. */
const CORE_STANCES: Stance[] = ["support", "skeptic", "neutral"];

/* ---- sub-components ---- */

function StanceBarWithConcern({
  stance,
  pct,
  concern,
  d,
}: {
  stance: Stance;
  pct: number;
  concern: string | undefined;
  d: ReturnType<typeof useDesign>;
}) {
  const color = STANCE_COLORS[stance];
  return (
    <div style={{ display: "flex", flexDirection: "column" as const, gap: d.scaled(6) }}>
      <div style={{ display: "flex", alignItems: "center", gap: d.scaled(14) }}>
        <span
          style={{
            fontFamily: FONTS.mono,
            fontSize: d.fs.caption,
            fontWeight: FW.semibold,
            width: d.scaled(60),
            textAlign: "right" as const,
            color: COLORS.muted,
          }}
        >
          {STANCE_LABELS[stance]}
        </span>
        <div
          style={{
            flex: 1,
            height: d.scaled(28),
            background: COLORS.surface2,
            borderRadius: d.scaled(4),
            overflow: "hidden",
            position: "relative" as const,
          }}
        >
          <div
            style={{
              height: "100%",
              borderRadius: d.scaled(4),
              transition: "width 1.2s ease",
              width: `${pct}%`,
              background: color,
            }}
          />
        </div>
        <span
          style={{
            fontFamily: FONTS.mono,
            fontSize: d.fs.caption,
            fontWeight: FW.bold,
            width: d.scaled(48),
            color: COLORS.fg,
          }}
        >
          {pct}%
        </span>
      </div>
      {concern && (
        <div
          style={{
            paddingLeft: d.scaled(74),
            fontSize: d.fs.caption,
            color: COLORS.dim,
            lineHeight: 1.3,
          }}
        >
          {concern}
        </div>
      )}
    </div>
  );
}

function QuoteBlock({
  q,
  last,
  d,
}: {
  q: Quote;
  last: boolean;
  d: ReturnType<typeof useDesign>;
}) {
  const color = STANCE_COLORS[q.stance];
  const stanceLabel = STANCE_LABELS[q.stance];
  return (
    <div
      style={{
        display: "flex",
        gap: d.scaled(16),
        padding: `${d.scaled(12)}px 0`,
        borderBottom: last ? undefined : `1px solid ${COLORS.border}`,
      }}
    >
      <div
        style={{
          width: d.scaled(4),
          borderRadius: d.scaled(2),
          flexShrink: 0,
          background: color,
        }}
      />
      <div style={{ display: "flex", flexDirection: "column" as const, gap: d.scaled(8) }}>
        <div
          style={{
            fontSize: d.fs.caption,
            lineHeight: 1.5,
            color: COLORS.fg,
            fontStyle: "italic",
          }}
        >
          &ldquo;{q.text}&rdquo;
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: d.scaled(12) }}>
          <span
            style={{
              fontFamily: FONTS.mono,
              fontSize: d.fs.caption,
              color: COLORS.dim,
            }}
          >
            {q.author}
          </span>
          <span
            style={{
              fontFamily: FONTS.mono,
              fontSize: d.fs.caption,
              fontWeight: FW.semibold,
              color,
              background: `${color}18`,
              padding: `${d.scaled(2)}px ${d.scaled(8)}px`,
              borderRadius: d.scaled(3),
            }}
          >
            {stanceLabel}
          </span>
        </div>
      </div>
    </div>
  );
}

/* ---- main component ---- */

export const AtmosphereCard: React.FC<ElementProps> = ({
  elementProps,
  width: _width,
  height: _height,
}) => {
  const frame = useCurrentFrame();
  const d = useDesign();

  const typed = extractAtmosphereProps(elementProps);
  const {
    controversyLevel,
    discussionSummary,
    debateTopics,
    stanceDistribution,
    stanceConcerns,
    quotes,
    displayIndex,
    storyCount,
  } = typed;

  // Compute percentages for stance bars (only core 3)
  const totalStance =
    stanceDistribution.support +
    stanceDistribution.skeptic +
    stanceDistribution.neutral;

  const stancePcts: Record<string, number> = {
    support: totalStance > 0 ? Math.round((stanceDistribution.support / totalStance) * 100) : 0,
    skeptic: totalStance > 0 ? Math.round((stanceDistribution.skeptic / totalStance) * 100) : 0,
    neutral: totalStance > 0 ? Math.round((stanceDistribution.neutral / totalStance) * 100) : 0,
  };

  // Entrance animation
  const titleProgress = interpolate(frame, [ANIM.titleStart, ANIM.titleEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyProgress = interpolate(frame, [ANIM.bodyStart, ANIM.bodyEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <CardShell
      elementProps={elementProps}
      pageIndex={displayIndex}
      totalPages={storyCount}
      justify="start"                  // 内容多, 从顶部开始
      gutter={100}                     // 对称左右内边距
      paddingTop={80}
      paddingBottom={120}
      showTopBar
      showWatermark
      showWaveform
      reserveSubtitle                  // 字幕始终显示, 底部给字幕让位
    >
      <Fill gap={14} maxWidth={CARD_LAYOUT.content.maxWidth}>
        {/* ① Controversy title + discussion summary subtitle */}
        <h1
          style={{
            fontFamily: FONTS.sans,
            fontSize: d.fs.headline,
            fontWeight: FW.heavy,
            lineHeight: 1.15,
            letterSpacing: "-0.015em",
            color: COLORS.warmBrown,
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [10, 0])}px)`,
          }}
        >
          争议指数 {typed.controversyScore.toFixed(1)} · {CONTROVERSY_LABELS[controversyLevel]}
        </h1>
        <p
          style={{
            fontFamily: FONTS.sans,
            fontSize: d.fs.body,
            fontWeight: FW.semibold,
            lineHeight: 1.4,
            color: COLORS.dim,
            marginTop: d.scaled(-8),
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [10, 0])}px)`,
          }}
        >
          {(discussionSummary || "社区讨论").slice(0, 40)}
        </p>

        {/* Divider line */}
        <div
          style={{
            width: "100%",
            maxWidth: d.scaled(CARD_LAYOUT.divider.maxWidth),
            height: d.scaled(CARD_LAYOUT.divider.height),
            borderRadius: d.scaled(CARD_LAYOUT.divider.borderRadius),
            marginTop: d.scaled(4),
            marginBottom: d.scaled(4),
            background: `linear-gradient(90deg, ${COLORS.warmBrown}, ${COLORS.warmGold}99, transparent)`,
          }}
        />

        {/* ②③ Debate topics + Stance distribution two-column */}
        <div
          style={{
            display: "flex",
            gap: d.scaled(60),
            flex: 1,
            minHeight: 0,
            opacity: bodyProgress,
            transform: `translateY(${interpolate(bodyProgress, [0, 1], [12, 0])}px)`,
          }}
        >
          {/* Left: stance distribution with concerns */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column" as const, gap: d.scaled(12) }}>
            <h3
              style={{
                fontFamily: FONTS.mono,
                fontSize: d.fs.caption,
                fontWeight: FW.bold,
                letterSpacing: "0.15em",
                textTransform: "uppercase" as const,
                color: COLORS.warmGold,
                marginBottom: d.scaled(6),
              }}
            >
              立场分布
            </h3>
            {CORE_STANCES.map((s) => (
              <StanceBarWithConcern
                key={s}
                stance={s}
                pct={stancePcts[s]}
                concern={stanceConcerns[s as keyof typeof stanceConcerns]}
                d={d}
              />
            ))}
          </div>

          {/* Right: debate topics + compact stance bar */}
          <div style={{ flex: 1, display: "flex", flexDirection: "column" as const, gap: d.scaled(16) }}>
            <h3
              style={{
                fontFamily: FONTS.mono,
                fontSize: d.fs.caption,
                fontWeight: FW.bold,
                letterSpacing: "0.15em",
                textTransform: "uppercase" as const,
                color: COLORS.warmGold,
                marginBottom: d.scaled(6),
              }}
            >
              辩论焦点
            </h3>
            {debateTopics.map((topic, i) => (
              <div key={i} style={{ display: "flex", gap: d.scaled(8), alignItems: "center" as const }}>
                <span
                  style={{
                    fontFamily: FONTS.mono,
                    fontSize: d.fs.bodySmall,
                    fontWeight: FW.bold,
                    color: COLORS.warmBrown,
                    flexShrink: 0,
                    width: d.scaled(36),
                    textAlign: "right" as const,
                  }}
                >
                  {i + 1}.
                </span>
                <span
                  style={{
                    fontSize: d.fs.body,
                    fontWeight: FW.semibold,
                    lineHeight: 1.4,
                    color: COLORS.fg,
                  }}
                >
                  {topic}
                </span>
              </div>
            ))}
            {debateTopics.length === 0 && (
              <span style={{ color: COLORS.dim, fontSize: d.fs.body }}>
                暂无显著辩论焦点
              </span>
            )}
          </div>
        </div>

        {/* ④ Quotes (max 2 to prevent overflow) */}
        {quotes.length > 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column" as const,
              gap: d.scaled(12),
              maxWidth: d.scaled(CARD_LAYOUT.content.maxWidth),
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [12, 0])}px)`,
              flexShrink: 1,
              minHeight: 0,
              overflow: "hidden",
            }}
          >
            <h3
              style={{
                fontFamily: FONTS.mono,
                fontSize: d.fs.caption,
                fontWeight: FW.semibold,
                color: COLORS.warmGold,
                marginBottom: d.scaled(2),
              }}
            >
              评论金句
            </h3>
            {quotes.slice(0, 2).map((q, i) => (
              <QuoteBlock key={i} q={q} last={i === Math.min(quotes.length, 2) - 1} d={d} />
            ))}
          </div>
        )}
      </Fill>
    </CardShell>
  );
};

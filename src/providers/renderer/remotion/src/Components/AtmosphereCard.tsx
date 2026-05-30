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
import { COLORS, CARD_REF } from "./theme";
import type { ElementProps } from "./utils";
import { extractAtmosphereProps } from "./propsExtractors";
import { CardAudioWaveform } from "./CardAudioWaveform";
import { useDesign, FONTS, FW, CARD_PAD } from "./design";
import { WatermarkCharacter } from "./WatermarkCharacter";

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
            height: d.scaled(22),
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
        width: d.scaled(CARD_REF.width),
        height: "100%" as const,
        background: COLORS.bg,
        position: "relative" as const,
        overflow: "hidden",
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [32, 0])}px)`,
      }}
    >
      {/* Watermark */}
      {storyCount > 0 && (
        <div
          style={{
            position: "absolute" as const,
            top: d.scaled(96),
            right: d.scaled(56),
            fontFamily: FONTS.mono,
            fontSize: d.fs.watermarkLg,
            fontWeight: FW.heavy,
            color: COLORS.dim,
            letterSpacing: "0.1em",
            zIndex: 5,
          }}
        >
          {displayIndex + 1} / {storyCount}
        </div>
      )}

      <div
        style={{
          padding: `${d.scaled(80)}px ${d.scaled(CARD_PAD.xNormal)}px ${d.scaled(180)}px ${d.scaled(100)}px`,
          height: "100%",
          display: "flex",
          flexDirection: "column" as const,
          gap: d.scaled(14),
          position: "relative" as const,
        }}
      >
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
            maxWidth: d.scaled(900),
            height: d.scaled(6),
            borderRadius: d.scaled(3),
            marginTop: d.scaled(4),
            marginBottom: d.scaled(4),
            background: `linear-gradient(90deg, ${COLORS.warmBrown}, ${COLORS.warmGold}99, transparent)`,
          }}
        />

        {/* ②③ Debate topics + Stance distribution two-column */}
        <div
          style={{
            display: "flex",
            gap: d.scaled(80),
            opacity: bodyProgress,
            transform: `translateY(${interpolate(bodyProgress, [0, 1], [12, 0])}px)`,
          }}
        >
          {/* Left: stance distribution with concerns */}
          <div style={{ flex: 1, maxWidth: d.scaled(800), display: "flex", flexDirection: "column" as const, gap: d.scaled(12) }}>
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

          {/* Right: debate topics */}
          <div style={{ flex: `0 0 ${d.scaled(540)}px`, display: "flex", flexDirection: "column" as const, gap: d.scaled(20) }}>
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
              <div key={i} style={{ display: "flex", gap: d.scaled(14), alignItems: "center" as const }}>
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

        {/* ④ Quotes */}
        {quotes.length > 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column" as const,
              gap: d.scaled(12),
              maxWidth: d.scaled(1400),
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [12, 0])}px)`,
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
            {quotes.map((q, i) => (
              <QuoteBlock key={i} q={q} last={i === quotes.length - 1} d={d} />
            ))}
          </div>
        )}

        <WatermarkCharacter expression="atmosphere_card.jpg" />

        <div style={{ position: "absolute" as const, bottom: d.scaled(20) }}>
          <CardAudioWaveform src={elementProps.audio_path as string | undefined} />
        </div>
      </div>
    </div>
  );
};

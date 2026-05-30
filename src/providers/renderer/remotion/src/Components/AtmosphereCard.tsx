/* ================================================================
   AtmosphereCard — 社区回声卡 (Warm Paper Theme)
   ================================================================

   Layout: single-column vertical
     - Controversy score row (score + level tag + total comments)
     - Debate topics (left) + stance distribution bars (right) — two columns
     - Quoted opinions (stripe + quote text + author + likes)

   Adapted for Remotion: accepts ElementProps, uses useDesign() for scaling,
   adds entrance animation via useCurrentFrame/interpolate.
*/

import React from "react";
import { useCurrentFrame, interpolate, Easing, staticFile } from "remotion";
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
import { useDesign, FONTS, FW } from "./design";
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

const STANCE_ORDER: Stance[] = [
  "support",
  "skeptic",
  "neutral",
  "tease",
  "worry",
];

/* ---- sub-components ---- */

function StanceBar({
  stance,
  pct,
  d,
}: {
  stance: Stance;
  pct: number;
  d: ReturnType<typeof useDesign>;
}) {
  const color = STANCE_COLORS[stance];
  return (
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
  return (
    <div
      style={{
        display: "flex",
        gap: d.scaled(16),
        padding: `${d.scaled(18)}px 0`,
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
            fontSize: d.fs.body,
            lineHeight: 1.5,
            color: COLORS.fg,
            fontStyle: "italic",
          }}
        >
          &ldquo;{q.text}&rdquo;
        </div>
        <div
          style={{
            fontFamily: FONTS.mono,
            fontSize: d.fs.caption,
            color: COLORS.dim,
          }}
        >
          {q.author}
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
    controversyScore,
    controversyLevel,
    debateTopics,
    stanceDistribution,
    quotes,
    displayIndex,
    storyCount,
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
        width: d.scaled(CARD_REF.width),
        height: "100%" as const,
        background: COLORS.bg,
        position: "relative" as const,
        overflow: "hidden",
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [32, 0])}px)`,
      }}
    >
      {/* Watermark — same style as EventCard */}
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
          padding: `${d.scaled(80)}px ${d.scaled(56)}px ${d.scaled(140)}px ${d.scaled(100)}px`,
          height: "100%",
          display: "flex",
          flexDirection: "column" as const,
          justifyContent: "center" as const,
          gap: d.scaled(28),
          position: "relative" as const,
        }}
      >
        {/* Score hero row */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            gap: d.scaled(28),
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [10, 0])}px)`,
          }}
        >
          {/* Hero: big score — same style as EventCard title */}
          <span
            style={{
              fontFamily: FONTS.sans,
              fontSize: d.fs.headline,
              fontWeight: FW.heavy,
              lineHeight: 1.15,
              color: COLORS.fg,
              letterSpacing: "-0.015em",
            }}
          >
            {controversyScore.toFixed(1)}
            <span
              style={{
                fontSize: d.fs.body,
                color: COLORS.dim,
                fontWeight: 300,
                marginLeft: d.scaled(4),
              }}
            >
              /10
            </span>
          </span>
          {/* Controversy level — same style as EventCard title */}
          <span
            style={{
              fontFamily: FONTS.sans,
              fontSize: d.fs.headline,
              fontWeight: FW.heavy,
              lineHeight: 1.15,
              color: COLORS.warmBrown,
              letterSpacing: "-0.015em",
            }}
          >
            {CONTROVERSY_LABELS[controversyLevel]}
          </span>
        </div>

        {/* Gradient divider — same as EventCard */}
        <div
          style={{
            width: "100%",
            maxWidth: d.scaled(900),
            height: d.scaled(6),
            borderRadius: d.scaled(3),
            background: `linear-gradient(90deg, ${COLORS.warmBrown}, ${COLORS.warmGold}99, transparent)`,
          }}
        />

        {/* Debate + Stance two-column */}
        <div
          style={{
            display: "flex",
            gap: d.scaled(80),
            opacity: bodyProgress,
            transform: `translateY(${interpolate(bodyProgress, [0, 1], [12, 0])}px)`,
          }}
        >
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
              <div key={i} style={{ display: "flex", gap: d.scaled(14), alignItems: "flex-start" as const }}>
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

          <div style={{ flex: 1, maxWidth: d.scaled(800), display: "flex", flexDirection: "column" as const, gap: d.scaled(18) }}>
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
            {STANCE_ORDER.map((s) => (
              <StanceBar key={s} stance={s} pct={stancePcts[s]} d={d} />
            ))}
          </div>
        </div>

        {/* Quotes */}
        {quotes.length > 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column" as const,
              gap: d.scaled(18),
              maxWidth: d.scaled(1400),
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [12, 0])}px)`,
            }}
          >
            {quotes.map((q, i) => (
              <QuoteBlock key={i} q={q} last={i === quotes.length - 1} d={d} />
            ))}
          </div>
        )}

        <WatermarkCharacter />

        <div style={{ position: "absolute" as const, bottom: d.scaled(20) }}>
          <CardAudioWaveform src={elementProps.audio_path as string | undefined} />
        </div>
      </div>
    </div>
  );
};
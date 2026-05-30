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

   Adapted for Remotion: accepts ElementProps, uses useDesign() for scaling,
   adds entrance animation via useCurrentFrame/interpolate.
*/

import React from "react";
import { useCurrentFrame, interpolate, Easing, staticFile } from "remotion";
import type { ClosingCardProps, CompletedStory } from "./cardTypes";
import { COLORS, CARD_REF } from "./theme";
import type { ElementProps } from "./utils";
import { extractClosingProps } from "./propsExtractors";
import { ANIM_PRESETS } from "./timing";
import { CardAudioWaveform } from "./CardAudioWaveform";
import { useDesign, FONTS, FW } from "./design";
import { WatermarkCharacter } from "./WatermarkCharacter";

/* ---- sub-components ---- */

function StoryItem({
  story,
  d,
}: {
  story: CompletedStory;
  d: ReturnType<typeof useDesign>;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: d.scaled(14), fontSize: d.fs.body }}>
      <span
        style={{
          fontFamily: FONTS.mono,
          color: COLORS.sage,
          fontWeight: FW.heavy,
          fontSize: d.fs.caption,
        }}
      >
        ✓
      </span>
      {story.category && (
        <span
          style={{
            display: "inline-flex",
            fontFamily: FONTS.mono,
            fontSize: d.fs.micro,
            fontWeight: FW.bold,
            letterSpacing: "0.1em",
            padding: `${d.scaled(2)}px ${d.scaled(10)}px`,
            borderRadius: d.scaled(4),
            border: `1px solid ${COLORS.border}`,
            color: COLORS.dim,
          }}
        >
          {story.category}
        </span>
      )}
      <span style={{ color: COLORS.fg, fontWeight: FW.semibold }}>{story.title}</span>
    </div>
  );
}

/* ---- main component ---- */

export const ClosingCard: React.FC<ElementProps> = ({
  elementProps,
  width: _width,
  height: _height,
}) => {
  const frame = useCurrentFrame();
  const d = useDesign();

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

  // Entrance animation — unified via ANIM_PRESETS
  const cardProgress = interpolate(frame, ANIM_PRESETS.card.range, [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleProgress = interpolate(frame, ANIM_PRESETS.title.range, [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyProgress = interpolate(frame, ANIM_PRESETS.body.range, [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const cardY = interpolate(cardProgress, [0, 1], [ANIM_PRESETS.card.yOffset, 0]);
  const titleY = interpolate(titleProgress, [0, 1], [ANIM_PRESETS.title.yOffset, 0]);
  const bodyY = interpolate(bodyProgress, [0, 1], [ANIM_PRESETS.body.yOffset, 0]);

  return (
    <div
      style={{
        width: d.scaled(CARD_REF.width),
        height: "100%" as const,
        background: COLORS.bg,
        position: "relative" as const,
        overflow: "hidden",
        opacity: cardProgress,
        transform: `translateY(${cardY}px)`,
      }}
    >
      <div
        style={{
          padding: `${d.scaled(80)}px ${d.scaled(100)}px`,
          height: "100%",
          display: "flex",
          flexDirection: "column" as const,
          justifyContent: "center",
          alignItems: "flex-start",
          textAlign: "left" as const,
          gap: d.scaled(48),
          position: "relative" as const,
        }}
      >
        {/* Signal tag */}
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: d.scaled(8),
            fontFamily: FONTS.mono,
            fontSize: d.fs.caption,
            fontWeight: FW.bold,
            letterSpacing: "0.2em",
            textTransform: "uppercase" as const,
            padding: `${d.scaled(8)}px ${d.scaled(24)}px`,
            borderRadius: d.scaled(999),
            background: COLORS.brownBg,
            color: COLORS.warmBrown,
            border: `1px solid #d4b896`,
            opacity: titleProgress,
            transform: `translateY(${titleY}px)`,
          }}
        >
          <span
            style={{
              width: d.scaled(8),
              height: d.scaled(8),
              borderRadius: "50%",
              background: COLORS.warmBrown,
            }}
          />
          {signalLabel}
        </div>

        {/* Summary */}
        {summary && (
          <h1
            style={{
              fontSize: d.fs.closing,
              fontWeight: FW.heavy,
              lineHeight: 1.2,
              letterSpacing: "-0.015em",
              color: COLORS.fg,
              maxWidth: d.scaled(1400),
              opacity: titleProgress,
              transform: `translateY(${titleY}px)`,
            }}
          >
            {summary}
          </h1>
        )}

        {/* Keywords */}
        {keywords.length > 0 && (
          <div
            style={{
              display: "flex",
              gap: d.scaled(14),
              flexWrap: "wrap" as const,
              opacity: bodyProgress,
              transform: `translateY(${bodyY}px)`,
            }}
          >
            {keywords.map((k) => (
              <span
                key={k}
                style={{
                  display: "inline-flex",
                  fontFamily: FONTS.mono,
                  fontSize: d.fs.caption,
                  fontWeight: FW.bold,
                  padding: `${d.scaled(8)}px ${d.scaled(22)}px`,
                  borderRadius: d.scaled(6),
                  border: `1.5px solid ${COLORS.warmBrown}`,
                  color: COLORS.warmBrown,
                  letterSpacing: "0.06em",
                }}
              >
                {k}
              </span>
            ))}
          </div>
        )}

        {/* Progress bar */}
        {progressTotal > 0 && (
          <div
            style={{
              width: "100%",
              maxWidth: d.scaled(800),
              display: "flex",
              flexDirection: "column" as const,
              gap: d.scaled(14),
              opacity: bodyProgress,
              transform: `translateY(${bodyY}px)`,
            }}
          >
            <div
              style={{
                fontFamily: FONTS.mono,
                fontSize: d.fs.caption,
                fontWeight: FW.bold,
                letterSpacing: "0.15em",
                textTransform: "uppercase" as const,
                color: COLORS.warmGold,
                display: "flex",
                alignItems: "center",
                justifyContent: "flex-start",
                gap: d.scaled(10),
              }}
            >
              今日脉络
              <strong style={{ color: COLORS.fg, fontSize: d.fs.body }}>
                {progressDone} / {progressTotal}
              </strong>
              已完成
            </div>
            <div
              style={{
                display: "flex",
                gap: 0,
                height: d.scaled(22),
                borderRadius: d.scaled(11),
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${focusPct}%`,
                  background: COLORS.warmBrown,
                  borderRight: "2px solid #fff",
                }}
              />
              <div
                style={{
                  height: "100%",
                  width: `${atmospherePct}%`,
                  background: COLORS.warmGold,
                  borderRight: "2px solid #fff",
                }}
              />
              {remainPct > 0 && (
                <div
                  style={{
                    height: "100%",
                    width: `${remainPct}%`,
                    background: COLORS.surface2,
                  }}
                />
              )}
            </div>
          </div>
        )}

        {/* Completed stories */}
        {completedStories.length > 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column" as const,
              gap: d.scaled(12),
              width: "100%",
              maxWidth: d.scaled(700),
              opacity: bodyProgress,
              transform: `translateY(${bodyY}px)`,
            }}
          >
            {completedStories.map((s, i) => (
              <StoryItem key={i} story={s} d={d} />
            ))}
          </div>
        )}

        {/* Stats row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: d.scaled(28),
            fontFamily: FONTS.mono,
            fontSize: d.fs.bodySmall,
            color: COLORS.dim,
            background: COLORS.goldBg,
            padding: `${d.scaled(16)}px ${d.scaled(28)}px`,
            borderRadius: d.scaled(8),
            opacity: bodyProgress,
            transform: `translateY(${bodyY}px)`,
          }}
        >
          <span>
            <strong style={{ color: COLORS.warmGold, fontSize: d.fs.subhead, fontWeight: FW.bold }}>
              {stats.storyCount}
            </strong>{" "}
            条主线
          </span>
          <span style={{ color: COLORS.border }}>/</span>
          <span>
            <strong style={{ color: COLORS.warmGold, fontSize: d.fs.subhead, fontWeight: FW.bold }}>
              {stats.points.toLocaleString()}
            </strong>{" "}
            points
          </span>
          <span style={{ color: COLORS.border }}>/</span>
          <span>
            <strong style={{ color: COLORS.warmGold, fontSize: d.fs.subhead, fontWeight: FW.bold }}>
              {stats.comments.toLocaleString()}
            </strong>{" "}
            comments
          </span>
        </div>

        {/* Vibe tag */}
        {vibe && (
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              fontFamily: FONTS.mono,
              fontSize: d.fs.micro,
              fontWeight: FW.semibold,
              letterSpacing: "0.14em",
              textTransform: "uppercase" as const,
              padding: `${d.scaled(6)}px ${d.scaled(20)}px`,
              borderRadius: d.scaled(999),
              background: COLORS.goldBg,
              color: COLORS.warmGold,
              border: `1px solid #c4a870`,
              opacity: bodyProgress,
              transform: `translateY(${titleY}px)`,
            }}
          >
            {vibe}
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
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
import { useCurrentFrame, interpolate } from "remotion";
import type { ControversyLevel, Stance } from "./cardTypes";
import { COLORS } from "./design";
import type { ElementProps } from "./utils";
import { extractAtmosphereProps } from "./propsExtractors";
import {
  useDesign,
  FONTS,
  FW,
  ANIM,
  EASE_CARD,
  CARD_LAYOUT,
  COMMON_LAYOUT,
  ATMOSPHERE_LAYOUT,
} from "./design";
import { CardShell, Fill } from "./CardShell";
import { Panel, SectionHeading, SlideIndicator } from "./CardPrimitives";
import { STANCE_COLORS } from "./stance";

/* ---- label maps ---- */

const CONTROVERSY_LABELS: Record<ControversyLevel, string> = {
  consensus: "共识较强",
  divided: "存在分歧",
  highly_controversial: "高度争议",
};

/** Only the 3 core stances rendered on the card (aligned to template: support / neutral / skeptic). */
const CORE_STANCE_ORDER: { label: string; key: Stance }[] = [
  { label: "支持", key: "support" },
  { label: "中立", key: "neutral" },
  { label: "质疑", key: "skeptic" },
];

/* ---- sub-components ---- */

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
    quotes,
    displayIndex,
    storyCount,
  } = typed;

  // Compute percentages for stance bars (support/neutral/skeptic in template order)
  // Normalize to ensure all 3 sum to 100%
  const raw = stanceDistribution;
  const rawSupport = raw.support || 0;
  const rawSkeptic = raw.skeptic || 0;
  const rawNeutral = raw.neutral || 0;
  const totalStance = rawSupport + rawSkeptic + rawNeutral || 1;
  const stancePcts: Record<string, number> = {
    support: Math.round((rawSupport / totalStance) * 100),
    neutral: Math.round((rawNeutral / totalStance) * 100),
    skeptic: Math.round((rawSkeptic / totalStance) * 100),
  };
  // Normalize to ensure they sum to 100
  const pctsSum = stancePcts.support + stancePcts.neutral + stancePcts.skeptic;
  if (pctsSum !== 100) {
    const diff = 100 - pctsSum;
    stancePcts.skeptic += diff;
  }

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
      justify="start"
      gutter={ATMOSPHERE_LAYOUT.gutter}
      paddingTop={ATMOSPHERE_LAYOUT.paddingTop}
      paddingBottom={ATMOSPHERE_LAYOUT.paddingBottom}
      showTopBar
      showWatermark={false}
      showWaveform
      reserveSubtitle
    >
      <SlideIndicator current={displayIndex + 1} total={storyCount} />
      <Fill gap={ATMOSPHERE_LAYOUT.fillGap} maxWidth={CARD_LAYOUT.content.wideMaxWidth}>
        {/* ① Stat-block header (对齐模板 stat-block: prefix + 大数字 + label) */}
        <div
          style={{
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [COMMON_LAYOUT.riseSmall, 0])}px)`,
          }}
        >
          <h1
            style={{
              fontFamily: FONTS.serifBold,
              fontSize: d.fs.text5xl,
              fontWeight: FW.heavy,
              lineHeight: 1,
              color: COLORS.brandDeep,
              display: "flex",
              alignItems: "baseline",
              gap: d.scaled(COMMON_LAYOUT.itemGap),
              flexWrap: "wrap",
            }}
          >
            <span style={{ fontSize: d.fs.text3xl, fontWeight: FW.heavy }}>争议指数</span>
            <span
              style={{
                fontSize: d.fs.text6xl,
                fontFamily: FONTS.serif,
                fontWeight: FW.heavy,
                lineHeight: 1,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              {typed.controversyScore.toFixed(1)}
            </span>
            <span style={{ fontSize: d.fs.text2xl, fontWeight: FW.heavy, color: COLORS.inkSoft }}>
              {CONTROVERSY_LABELS[controversyLevel]}
            </span>
          </h1>
          <p
            style={{
              fontFamily: FONTS.sans,
              fontSize: d.fs.textLg,
              fontWeight: FW.medium,
              lineHeight: 1.4,
              color: COLORS.muted,
              marginTop: d.scaled(COMMON_LAYOUT.smallRadius),
              maxWidth: d.scaled(ATMOSPHERE_LAYOUT.summaryMaxWidth),
            }}
          >
            {discussionSummary || "社区讨论"}
          </p>
        </div>

        {/* ② Three-panel grid (对齐模板: 0.9fr / 1.05fr / 1.05fr) */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: ATMOSPHERE_LAYOUT.gridColumns.map((col) => `${col}fr`).join(" "),
            gap: d.scaled(ATMOSPHERE_LAYOUT.gridGap),
            flex: 1,
            minHeight: 0,
            opacity: bodyProgress,
            transform: `translateY(${interpolate(bodyProgress, [0, 1], [COMMON_LAYOUT.riseSmall, 0])}px)`,
          }}
        >
          {/* Panel A: 立场分布 */}
          <Panel minHeight={ATMOSPHERE_LAYOUT.panelMinHeight}>
            <SectionHeading>立场分布</SectionHeading>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: d.scaled(COMMON_LAYOUT.panelGap),
              }}
            >
              {CORE_STANCE_ORDER.map(({ label, key }) => {
                const stanceKey = key as Stance;
                const pct = stancePcts[stanceKey] ?? 0;
                const color = STANCE_COLORS[stanceKey];
                return (
                  <div
                    key={key}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: d.scaled(ATMOSPHERE_LAYOUT.stanceRowGap),
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "baseline",
                        justifyContent: "space-between",
                        color: COLORS.inkSoft,
                        fontSize: d.fs.textSm,
                        fontWeight: FW.bold,
                      }}
                    >
                      <span>{label}</span>
                      <span
                        style={{
                          color: COLORS.fg,
                          fontFamily: FONTS.mono,
                          fontSize: d.fs.textBase,
                          fontVariantNumeric: "tabular-nums",
                        }}
                      >
                        {pct}%
                      </span>
                    </div>
                    <div
                      style={{
                        height: d.scaled(ATMOSPHERE_LAYOUT.stanceBarHeight),
                        overflow: "hidden",
                        borderRadius: d.scaled(COMMON_LAYOUT.pillRadius),
                        background: COLORS.surfaceMid,
                      }}
                    >
                      <div
                        style={{
                          height: "100%",
                          width: `${pct}%`,
                          borderRadius: "inherit",
                          background: color,
                          transformOrigin: "left center",
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </Panel>

          {/* Panel B: 讨论焦点 */}
          <Panel minHeight={ATMOSPHERE_LAYOUT.panelMinHeight}>
            <SectionHeading>讨论焦点</SectionHeading>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: d.scaled(ATMOSPHERE_LAYOUT.focusGap),
              }}
            >
              {debateTopics.map((topic, i) => (
                <div
                  key={i}
                  style={{
                    paddingLeft: d.scaled(COMMON_LAYOUT.itemGap),
                    borderLeft: `${d.scaled(COMMON_LAYOUT.sectionRuleWidth)}px solid ${COLORS.brandSoft}`,
                    color: COLORS.fg,
                    fontSize: d.fs.textBase,
                    lineHeight: 1.3,
                  }}
                >
                  {topic}
                </div>
              ))}
              {debateTopics.length === 0 && (
                <span style={{ color: COLORS.dim, fontSize: d.fs.textBase }}>暂无显著辩论焦点</span>
              )}
            </div>
          </Panel>

          {/* Panel C: 评论金句 */}
          <Panel minHeight={ATMOSPHERE_LAYOUT.panelMinHeight}>
            <SectionHeading>评论金句</SectionHeading>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: d.scaled(ATMOSPHERE_LAYOUT.focusGap),
              }}
            >
              {quotes.slice(0, ATMOSPHERE_LAYOUT.quoteLimit).map((q, i) => (
                <div
                  key={i}
                  style={{
                    paddingLeft: d.scaled(COMMON_LAYOUT.itemGap),
                    borderLeft: `${d.scaled(COMMON_LAYOUT.sectionRuleWidth)}px solid ${COLORS.brand}`,
                    color: COLORS.inkSoft,
                    fontSize: d.fs.textBase,
                    fontStyle: "italic",
                    lineHeight: 1.3,
                  }}
                >
                  &ldquo;{q.text}&rdquo;
                </div>
              ))}
              {quotes.length === 0 && (
                <span style={{ color: COLORS.dim, fontSize: d.fs.textBase }}>暂无金句</span>
              )}
            </div>
          </Panel>
        </div>
      </Fill>
    </CardShell>
  );
};

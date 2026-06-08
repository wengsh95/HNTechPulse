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
import type { ControversyLevel, Stance, Quote } from "./cardTypes";
import { COLORS } from "./design";
import type { ElementProps } from "./utils";
import { extractAtmosphereProps } from "./propsExtractors";
import { useDesign, FONTS, FW, ANIM, EASE_CARD, CARD_LAYOUT } from "./design";
import { CardShell, Fill, EvenSpread } from "./CardShell";
import { STANCE_LABELS, STANCE_COLORS } from "./stance";

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

function QuoteBlock({ q, last, d }: { q: Quote; last: boolean; d: ReturnType<typeof useDesign> }) {
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
      gutter={70}
      paddingTop={42}
      paddingBottom={160}
      showTopBar
      showWatermark
      showWaveform
      reserveSubtitle
    >
      <Fill gap={16} maxWidth={CARD_LAYOUT.content.wideMaxWidth}>
        {/* ① Stat-block header (对齐模板 stat-block: prefix + 大数字 + label) */}
        <div style={{ opacity: titleProgress, transform: `translateY(${interpolate(titleProgress, [0, 1], [12, 0])}px)` }}>
          <h1
            style={{
              fontFamily: FONTS.serifBold,
              fontSize: d.fs.hero,
              fontWeight: FW.heavy,
              lineHeight: 1,
              color: COLORS.brandDeep,
              display: "flex",
              alignItems: "baseline",
              gap: d.scaled(12),
              flexWrap: "wrap",
            }}
          >
            <span style={{ fontSize: d.fs.subhead, fontWeight: FW.heavy }}>争议指数</span>
            <span style={{ fontSize: d.scaled(96), fontFamily: FONTS.serif, fontWeight: FW.heavy, lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>
              {typed.controversyScore.toFixed(1)}
            </span>
            <span style={{ fontSize: d.fs.subhead, fontWeight: FW.heavy, color: COLORS.inkSoft }}>
              {CONTROVERSY_LABELS[controversyLevel]}
            </span>
          </h1>
          <p
            style={{
              fontFamily: FONTS.sans,
              fontSize: d.fs.bodyLg,
              fontWeight: FW.medium,
              lineHeight: 1.4,
              color: COLORS.muted,
              marginTop: d.scaled(4),
              maxWidth: d.scaled(980),
            }}
          >
            {(discussionSummary || "社区讨论").slice(0, 60)}
          </p>
        </div>

        {/* ② Three-panel grid (对齐模板: 0.9fr / 1.05fr / 1.05fr) */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: `${d.scaled(360)}fr ${d.scaled(420)}fr ${d.scaled(420)}fr`,
            gap: d.scaled(20),
            flex: 1,
            minHeight: 0,
            opacity: bodyProgress,
            transform: `translateY(${interpolate(bodyProgress, [0, 1], [12, 0])}px)`,
          }}
        >
          {/* Panel A: 立场分布 */}
          <div
            style={{
              border: `1px solid ${COLORS.border}`,
              borderRadius: d.scaled(14),
              background: "rgba(255,253,248,0.82)",
              boxShadow: "0 4px 12px rgba(32,25,20,0.04)",
              padding: `${d.scaled(16)}px ${d.scaled(20)}px`,
              display: "flex",
              flexDirection: "column",
              gap: d.scaled(16),
              minHeight: d.scaled(300),
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: d.scaled(8), color: COLORS.brandDeep, fontSize: d.fs.subhead, fontWeight: FW.heavy }}>
              <span style={{ width: d.scaled(4), height: d.scaled(18), borderRadius: d.scaled(999), background: COLORS.brand, flexShrink: 0 }} />
              立场分布
            </span>
            <div style={{ display: "flex", flexDirection: "column", gap: d.scaled(16) }}>
              {CORE_STANCE_ORDER.map(({ label, key }) => {
                const stanceKey = key as Stance;
                const pct = stancePcts[stanceKey] ?? 0;
                const color = STANCE_COLORS[stanceKey];
                return (
                  <div key={key} style={{ display: "flex", flexDirection: "column", gap: d.scaled(8) }}>
                    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", color: COLORS.inkSoft, fontSize: d.fs.bodySmall, fontWeight: FW.bold }}>
                      <span>{label}</span>
                      <span style={{ color: COLORS.fg, fontFamily: FONTS.mono, fontSize: d.fs.body, fontVariantNumeric: "tabular-nums" }}>{pct}%</span>
                    </div>
                    <div style={{ height: d.scaled(11), overflow: "hidden", borderRadius: d.scaled(999), background: "rgba(32,25,20,0.09)" }}>
                      <div style={{ height: "100%", width: `${pct}%`, borderRadius: "inherit", background: color, transformOrigin: "left center" }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Panel B: 讨论焦点 */}
          <div
            style={{
              border: `1px solid ${COLORS.border}`,
              borderRadius: d.scaled(14),
              background: "rgba(255,253,248,0.82)",
              boxShadow: "0 4px 12px rgba(32,25,20,0.04)",
              padding: `${d.scaled(16)}px ${d.scaled(20)}px`,
              display: "flex",
              flexDirection: "column",
              gap: d.scaled(16),
              minHeight: d.scaled(300),
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: d.scaled(8), color: COLORS.brandDeep, fontSize: d.fs.subhead, fontWeight: FW.heavy }}>
              <span style={{ width: d.scaled(4), height: d.scaled(18), borderRadius: d.scaled(999), background: COLORS.brand, flexShrink: 0 }} />
              讨论焦点
            </span>
            <div style={{ display: "flex", flexDirection: "column", gap: d.scaled(12) }}>
              {debateTopics.map((topic, i) => (
                <div key={i} style={{ paddingLeft: d.scaled(12), borderLeft: `3px solid ${COLORS.brandSoft}`, color: COLORS.fg, fontSize: d.fs.body, lineHeight: 1.3 }}>
                  {topic}
                </div>
              ))}
              {debateTopics.length === 0 && (
                <span style={{ color: COLORS.dim, fontSize: d.fs.body }}>暂无显著辩论焦点</span>
              )}
            </div>
          </div>

          {/* Panel C: 评论金句 */}
          <div
            style={{
              border: `1px solid ${COLORS.border}`,
              borderRadius: d.scaled(14),
              background: "rgba(255,253,248,0.82)",
              boxShadow: "0 4px 12px rgba(32,25,20,0.04)",
              padding: `${d.scaled(16)}px ${d.scaled(20)}px`,
              display: "flex",
              flexDirection: "column",
              gap: d.scaled(16),
              minHeight: d.scaled(300),
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: d.scaled(8), color: COLORS.brandDeep, fontSize: d.fs.subhead, fontWeight: FW.heavy }}>
              <span style={{ width: d.scaled(4), height: d.scaled(18), borderRadius: d.scaled(999), background: COLORS.brand, flexShrink: 0 }} />
              评论金句
            </span>
            <div style={{ display: "flex", flexDirection: "column", gap: d.scaled(12) }}>
              {quotes.slice(0, 3).map((q, i) => (
                <div key={i} style={{ paddingLeft: d.scaled(12), borderLeft: `3px solid ${COLORS.brand}`, color: COLORS.inkSoft, fontSize: d.fs.body, fontStyle: "italic", lineHeight: 1.3 }}>
                  &ldquo;{q.text}&rdquo;
                </div>
              ))}
              {quotes.length === 0 && (
                <span style={{ color: COLORS.dim, fontSize: d.fs.body }}>暂无金句</span>
              )}
            </div>
          </div>
        </div>
      </Fill>
    </CardShell>
  );
};

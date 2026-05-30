/* ================================================================
   EventCard — 事件卡 (Warm Paper Theme)
   ================================================================

   Layout:
     - No image: text-only centered single column
     - With image: left-text + right-image (image 48% width, gradient mask)
     - With logo: left-text + right-logo (logo 220px wide, contain centered)
     - Watermark "index / total" at top-right

   Adapted for Remotion: accepts ElementProps, uses useTheme() for scaling,
   adds entrance animation via useCurrentFrame/interpolate.
*/

import React from "react";
import { useCurrentFrame, interpolate, staticFile, Easing } from "remotion";
import type { EventCardProps, AnalysisItem, HeatLevel } from "./cardTypes";
import { COLORS, TYPOGRAPHY, CARD_REF, useTheme } from "./theme";
import type { ElementProps } from "./utils";
import { extractEventProps } from "./propsExtractors";
import { CardAudioWaveform } from "./CardAudioWaveform";
import { WatermarkCharacter } from "./WatermarkCharacter";

/* ---- helpers ---- */

const HEAT_LABELS: Record<HeatLevel, string> = {
  L1: "热度等级 L1",
  L2: "热度等级 L2",
  L3: "热度等级 L3",
};

const HEAT_COLORS: Record<HeatLevel, { bg: string; fg: string }> = {
  L1: { bg: COLORS.sageBg, fg: COLORS.sage },
  L2: { bg: COLORS.goldBg, fg: COLORS.warmGold },
  L3: { bg: COLORS.brownBg, fg: COLORS.warmBrown },
};

const ANALYSIS_META: Record<
  AnalysisItem["type"],
  { label: string; barColor: string; labelColor: string }
> = {
  why: { label: "为何关注", barColor: COLORS.warmBrown, labelColor: COLORS.warmBrown },
  impact: {
    label: "影响分析",
    barColor: COLORS.warmGold,
    labelColor: COLORS.warmGold,
  },
};

const PULSE = `
@keyframes ec-pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}`;

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
    watermark: {
      position: "absolute" as const,
      top: scaled(96),
      right: scaled(56),
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(16),
      fontWeight: 600,
      color: COLORS.dim,
      letterSpacing: "0.1em",
      zIndex: 5,
    } as React.CSSProperties,
    dot: {
      width: scaled(7),
      height: scaled(7),
      borderRadius: "50%",
      background: COLORS.warmBrown,
      animation: "ec-pulse-dot 1.4s infinite",
    } as React.CSSProperties,
    badge: {
      display: "inline-flex",
      alignItems: "center",
      gap: scaled(6),
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(13),
      fontWeight: 700,
      letterSpacing: "0.12em",
      textTransform: "uppercase" as const,
      padding: `${scaled(6)}px ${scaled(16)}px`,
      borderRadius: scaled(4),
      background: COLORS.warmBrown,
      color: "#fff",
    } as React.CSSProperties,
    divider: {
      width: "100%",
      maxWidth: scaled(900),
      height: scaled(6),
      borderRadius: scaled(3),
      background: `linear-gradient(90deg, ${COLORS.warmBrown}, ${COLORS.warmGold}99, transparent)`,
    } as React.CSSProperties,
    domain: {
      fontSize: scaled(16),
      color: COLORS.dim,
      fontFamily: TYPOGRAPHY.fontMono,
      letterSpacing: "0.04em",
    } as React.CSSProperties,
    title: (maxW = 1100) =>
      ({
        fontSize: scaled(64),
        fontWeight: 900,
        lineHeight: 1.15,
        letterSpacing: "-0.015em",
        color: COLORS.fg,
        maxWidth: scaled(maxW),
      }) as React.CSSProperties,
    titleEn: {
      fontSize: scaled(22),
      fontWeight: 400,
      color: COLORS.dim,
      fontFamily: TYPOGRAPHY.fontMono,
      marginTop: scaled(-18),
      marginBottom: scaled(4),
    } as React.CSSProperties,
    header: {
      display: "flex",
      alignItems: "center",
      gap: scaled(16),
    } as React.CSSProperties,
    stats: {
      display: "flex",
      alignItems: "center",
      gap: scaled(20),
      flexWrap: "wrap" as const,
    } as React.CSSProperties,
    heatLevel: (level: HeatLevel) =>
      ({
        display: "inline-flex",
        alignItems: "center",
        gap: scaled(6),
        fontFamily: TYPOGRAPHY.fontMono,
        fontSize: scaled(15),
        fontWeight: 700,
        padding: `${scaled(6)}px ${scaled(18)}px`,
        borderRadius: scaled(999),
        letterSpacing: "0.08em",
        background: HEAT_COLORS[level].bg,
        color: HEAT_COLORS[level].fg,
      }) as React.CSSProperties,
    statNum: (color: string) =>
      ({
        fontFamily: TYPOGRAPHY.fontMono,
        fontSize: scaled(28),
        fontWeight: 700,
        color,
      }) as React.CSSProperties,
    statLabel: {
      fontSize: scaled(15),
      color: COLORS.dim,
    } as React.CSSProperties,
    sep: {
      color: COLORS.border,
      fontSize: scaled(20),
    } as React.CSSProperties,
    analysis: {
      display: "flex",
      flexDirection: "column" as const,
      gap: scaled(14),
      maxWidth: scaled(1100),
    } as React.CSSProperties,
    anItem: {
      display: "flex",
      gap: scaled(16),
      alignItems: "flex-start" as const,
    } as React.CSSProperties,
    anBar: (color: string) =>
      ({
        width: scaled(4),
        minHeight: scaled(56),
        borderRadius: scaled(2),
        flexShrink: 0,
        background: color,
      }) as React.CSSProperties,
    anLabel: (color: string) =>
      ({
        fontFamily: TYPOGRAPHY.fontMono,
        fontSize: scaled(13),
        fontWeight: 700,
        letterSpacing: "0.1em",
        textTransform: "uppercase" as const,
        color,
      }) as React.CSSProperties,
    anText: {
      fontSize: scaled(22),
      lineHeight: 1.5,
      color: COLORS.fg,
    } as React.CSSProperties,
    tags: {
      display: "flex",
      gap: scaled(12),
      flexWrap: "wrap" as const,
    } as React.CSSProperties,
    tag: {
      display: "inline-flex",
      fontFamily: TYPOGRAPHY.fontMono,
      fontSize: scaled(13),
      fontWeight: 600,
      padding: `${scaled(6)}px ${scaled(16)}px`,
      borderRadius: scaled(4),
      border: `1px solid ${COLORS.border}`,
      color: COLORS.muted,
      letterSpacing: "0.04em",
    } as React.CSSProperties,
    imageCol: {
      width: scaled(750),
      position: "absolute" as const,
      top: 0,
      bottom: 0,
      right: scaled(100),
      display: "flex",
      alignItems: "center",
      overflow: "hidden",
      borderRadius: scaled(8),
    } as React.CSSProperties,
    imageImg: {
      width: "100%",
      height: "auto",
      objectFit: "contain" as const,
      transform: `translateY(${scaled(-70)}px)`,
    } as React.CSSProperties,
    imageMask: {
      position: "absolute" as const,
      bottom: 0,
      left: 0,
      right: 0,
      height: scaled(120),
      background: `linear-gradient(to top, ${COLORS.bg}, transparent)`,
    } as React.CSSProperties,
    logoBox: {
      width: scaled(220),
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      flexShrink: 0,
    } as React.CSSProperties,
    logoImg: {
      width: "100%",
      objectFit: "contain" as const,
    } as React.CSSProperties,
  };
}

function TextContent(props: EventCardProps, S: ReturnType<typeof buildStyles>) {
  const {
    domain,
    title,
    englishTitle,
    heatLevel,
    hnScore,
    commentCount,
    analysis,
    keywords,
    imageUrl,
  } = props;
  const maxTitleW = imageUrl ? 700 : 1100;

  return (
    <>
      <div style={S.header}>
        <div style={S.badge}>
          <span style={S.dot} /> 重点观察
        </div>
        {domain && <span style={S.domain}>{domain}</span>}
      </div>
      <h1 style={S.title(maxTitleW)}>{title}</h1>
      {englishTitle && englishTitle !== title && (
        <p style={S.titleEn}>{englishTitle}</p>
      )}
      <div style={S.divider} />
      <div style={S.stats}>
        <span style={S.heatLevel(heatLevel)}>{HEAT_LABELS[heatLevel]}</span>
        <span style={S.statNum(COLORS.warmBrown)}>
          &#x1F525; {hnScore.toLocaleString()}
        </span>
        <span style={S.statLabel}>热度</span>
        <span style={S.sep}>|</span>
        <span style={S.statNum(COLORS.warmGold)}>
          &#x1F4AC; {commentCount.toLocaleString()}
        </span>
        <span style={S.statLabel}>评论</span>
      </div>
      {analysis.length > 0 && (
        <div style={S.analysis}>
          {analysis.map((a, i) => {
            const m = ANALYSIS_META[a.type];
            return (
              <div key={i} style={S.anItem}>
                <div style={S.anBar(m.barColor)} />
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                  }}
                >
                  <span style={S.anLabel(m.labelColor)}>{m.label}</span>
                  <p style={S.anText}>{a.text}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
      {keywords.length > 0 && (
        <div style={S.tags}>
          {keywords.map((kw) => (
            <span key={kw} style={S.tag}>
              {kw}
            </span>
          ))}
        </div>
      )}
    </>
  );
}

export const EventCard: React.FC<ElementProps> = ({
  elementProps,
  width,
  height,
}) => {
  const frame = useCurrentFrame();
  const d = useTheme();
  const S = buildStyles(d.scaled);

  const typed = extractEventProps(elementProps);
  const { index, total, imageUrl, logoUrl } = typed;
  const hasImage = Boolean(imageUrl);
  const hasLogo = Boolean(logoUrl);
  const isTwoCol = hasImage || hasLogo;

  // Entrance animation
  const cardProgress = interpolate(frame, [4, 22], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const innerProgress = interpolate(frame, [8, 26], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const imageProgress = interpolate(frame, [6, 26], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const inner: React.CSSProperties = isTwoCol
    ? {
        display: "flex",
        padding: `${d.scaled(80)}px ${d.scaled(100)}px`,
        height: "100%",
        gap: d.scaled(60),
        alignItems: hasImage ? "stretch" : "center",
        position: "relative" as const,
      }
    : {
        padding: `${d.scaled(80)}px ${d.scaled(100)}px`,
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        gap: d.scaled(36),
      };

  const contentMaxW: React.CSSProperties = isTwoCol
    ? {
        flex: 1,
        display: "flex",
        flexDirection: "column",
        gap: d.scaled(36),
        justifyContent: "center",
      }
    : { display: "flex", flexDirection: "column", gap: d.scaled(36) };

  return (
    <div
      style={{
        ...S.card,
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [32, 0])}px)`,
      }}
    >
      <style>{PULSE}</style>

      <div style={S.watermark}>
        {index} / {total}
      </div>

      <div style={inner}>
        {/* Text column (full-width or left-half) */}
        <div
          style={{
            ...contentMaxW,
            opacity: innerProgress,
            transform: `translateY(${interpolate(innerProgress, [0, 1], [16, 0])}px)`,
          }}
        >
          {TextContent(typed, S)}
        </div>

        {/* Right image */}
        {hasImage && (
          <div
            style={{
              ...S.imageCol,
              opacity: imageProgress,
              transform: `translateX(${interpolate(imageProgress, [0, 1], [28, 0])}px)`,
            }}
          >
            <img src={staticFile(imageUrl!)} alt="" style={S.imageImg} />
            <div style={S.imageMask} />
          </div>
        )}

        {/* Right logo */}
        {hasLogo && !hasImage && (
          <div
            style={{
              ...S.logoBox,
              opacity: imageProgress,
              transform: `translateX(${interpolate(imageProgress, [0, 1], [28, 0])}px)`,
            }}
          >
            <img src={staticFile(logoUrl!)} alt="logo" style={S.logoImg} />
          </div>
        )}

        {/* Waveform */}
        <div style={{ position: "absolute" as const, bottom: d.scaled(20) }}>
          <CardAudioWaveform src={elementProps.audio_path as string | undefined} />
        </div>
      </div>

      {/* Watermark character */}
      <WatermarkCharacter />
    </div>
  );
};

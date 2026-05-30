/* ================================================================
   EventCard — 事件卡 (Warm Paper Theme)
   ================================================================

   Layout:
     - No image: text-only centered single column
     - With image: left-text + right-image (image 48% width, gradient mask)
     - With logo: left-text + right-logo (logo 220px wide, contain centered)
     - Watermark "index / total" at top-right

   Adapted for Remotion: accepts ElementProps, uses useDesign() for scaling,
   adds entrance animation via useCurrentFrame/interpolate.
*/

import React from "react";
import { useCurrentFrame, interpolate, staticFile } from "remotion";
import type { EventCardProps, AnalysisItem, HeatLevel } from "./cardTypes";
import { COLORS, CARD_REF } from "./theme";
import type { ElementProps } from "./utils";
import { extractEventProps } from "./propsExtractors";
import { CardAudioWaveform } from "./CardAudioWaveform";
import { WatermarkCharacter } from "./WatermarkCharacter";
import {
  useDesign,
  FONTS,
  FW,
  ANIM,
  EASE_CARD,
  CARD_PAD,
  LAYOUT,
} from "./design";

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

/* ---- inline-styles builder (design-system aligned) ---- */

function buildStyles(d: ReturnType<typeof useDesign>) {
  return {
    card: {
      width: d.scaled(CARD_REF.width),
      height: "100%" as const,
      background: COLORS.bg,
      position: "relative" as const,
      overflow: "hidden",
    } as React.CSSProperties,
    watermark: {
      position: "absolute" as const,
      top: d.scaled(96),
      right: d.scaled(56),
      fontFamily: FONTS.mono,
      fontSize: d.fs.watermarkLg,
      fontWeight: FW.heavy,
      color: COLORS.dim,
      letterSpacing: "0.1em",
      zIndex: 5,
    } as React.CSSProperties,
    dot: {
      width: d.scaled(7),
      height: d.scaled(7),
      borderRadius: "50%",
      background: COLORS.warmBrown,
      animation: "ec-pulse-dot 1.4s infinite",
    } as React.CSSProperties,
    badge: {
      display: "inline-flex",
      alignItems: "center",
      gap: d.scaled(6),
      fontFamily: FONTS.mono,
      fontSize: d.fs.caption,
      fontWeight: FW.bold,
      letterSpacing: "0.12em",
      textTransform: "uppercase" as const,
      padding: `${d.scaled(6)}px ${d.scaled(16)}px`,
      borderRadius: d.scaled(4),
      background: COLORS.warmBrown,
      color: "#fff",
    } as React.CSSProperties,
    divider: {
      width: "100%",
      maxWidth: d.scaled(900),
      height: d.scaled(6),
      borderRadius: d.scaled(3),
      background: `linear-gradient(90deg, ${COLORS.warmBrown}, ${COLORS.warmGold}99, transparent)`,
    } as React.CSSProperties,
    domain: {
      fontSize: d.fs.bodySmall,
      color: COLORS.dim,
      fontFamily: FONTS.mono,
      letterSpacing: "0.04em",
    } as React.CSSProperties,
    title: (maxW: number) =>
      ({
        fontSize: d.fs.headline,
        fontWeight: FW.heavy,
        lineHeight: 1.15,
        letterSpacing: "-0.015em",
        color: COLORS.fg,
        maxWidth: maxW,
      }) as React.CSSProperties,
    titleEn: {
      fontSize: d.fs.body,
      fontWeight: FW.regular,
      color: COLORS.dim,
      fontFamily: FONTS.mono,
      marginTop: d.scaled(-18),
      marginBottom: d.scaled(4),
    } as React.CSSProperties,
    header: {
      display: "flex",
      alignItems: "center",
      gap: d.scaled(16),
    } as React.CSSProperties,
    stats: {
      display: "flex",
      alignItems: "center",
      gap: d.scaled(20),
      flexWrap: "wrap" as const,
    } as React.CSSProperties,
    heatLevel: (level: HeatLevel) =>
      ({
        display: "inline-flex",
        alignItems: "center",
        gap: d.scaled(6),
        fontFamily: FONTS.mono,
        fontSize: d.fs.caption,
        fontWeight: FW.bold,
        padding: `${d.scaled(6)}px ${d.scaled(18)}px`,
        borderRadius: d.scaled(999),
        letterSpacing: "0.08em",
        background: HEAT_COLORS[level].bg,
        color: HEAT_COLORS[level].fg,
      }) as React.CSSProperties,
    statNum: (color: string) =>
      ({
        fontFamily: FONTS.mono,
        fontSize: d.fs.body,
        fontWeight: FW.bold,
        color,
      }) as React.CSSProperties,
    statLabel: {
      fontSize: d.fs.bodySmall,
      color: COLORS.dim,
    } as React.CSSProperties,
    sep: {
      color: COLORS.border,
      fontSize: d.fs.body,
    } as React.CSSProperties,
    analysis: {
      display: "flex",
      flexDirection: "column" as const,
      gap: d.scaled(14),
      maxWidth: d.scaled(1100),
    } as React.CSSProperties,
    anItem: {
      display: "flex",
      gap: d.scaled(16),
      alignItems: "flex-start" as const,
    } as React.CSSProperties,
    anBar: (color: string) =>
      ({
        width: d.scaled(4),
        minHeight: d.scaled(56),
        borderRadius: d.scaled(2),
        flexShrink: 0,
        background: color,
      }) as React.CSSProperties,
    anLabel: (color: string) =>
      ({
        fontFamily: FONTS.mono,
        fontSize: d.fs.caption,
        fontWeight: FW.bold,
        letterSpacing: "0.1em",
        textTransform: "uppercase" as const,
        color,
      }) as React.CSSProperties,
    anText: {
      fontSize: d.fs.body,
      lineHeight: 1.5,
      color: COLORS.fg,
    } as React.CSSProperties,
    tags: {
      display: "flex",
      gap: d.scaled(12),
      flexWrap: "wrap" as const,
    } as React.CSSProperties,
    tag: {
      display: "inline-flex",
      fontFamily: FONTS.mono,
      fontSize: d.fs.caption,
      fontWeight: FW.semibold,
      padding: `${d.scaled(6)}px ${d.scaled(16)}px`,
      borderRadius: d.scaled(4),
      border: `1px solid ${COLORS.border}`,
      color: COLORS.muted,
      letterSpacing: "0.04em",
    } as React.CSSProperties,
    imageCol: {
      width: d.scaled(750),
      position: "absolute" as const,
      top: 0,
      bottom: 0,
      right: d.scaled(100),
      display: "flex",
      alignItems: "center",
      overflow: "hidden",
      borderRadius: d.scaled(8),
    } as React.CSSProperties,
    imageImg: {
      width: "100%",
      height: "auto",
      objectFit: "contain" as const,
      transform: `translateY(${d.scaled(-70)}px)`,
    } as React.CSSProperties,
    imageMask: {
      position: "absolute" as const,
      bottom: 0,
      left: 0,
      right: 0,
      height: d.scaled(120),
      background: `linear-gradient(to top, ${COLORS.bg}, transparent)`,
    } as React.CSSProperties,
    logoBox: {
      width: d.scaled(220),
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

function TextContent(props: EventCardProps, S: ReturnType<typeof buildStyles>, d: ReturnType<typeof useDesign>) {
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
  const maxTitleW = imageUrl ? d.layout.contentMaxWidth : d.layout.contentWideMaxWidth;

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
                    gap: d.scaled(4),
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
  const d = useDesign();
  const S = buildStyles(d);

  const typed = extractEventProps(elementProps);
  const { index, total, imageUrl, logoUrl } = typed;
  const hasImage = Boolean(imageUrl);
  const hasLogo = Boolean(logoUrl);
  const isTwoCol = hasImage || hasLogo;

  // Entrance animation — using shared ANIM constants
  const cardProgress = interpolate(frame, [ANIM.cardStart, ANIM.cardEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const innerProgress = interpolate(frame, [ANIM.titleStart, ANIM.titleEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const imageProgress = interpolate(frame, [ANIM.imageStart, ANIM.imageEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const inner: React.CSSProperties = isTwoCol
    ? {
        display: "flex",
        padding: `${d.scaled(80)}px ${d.scaled(CARD_PAD.xNormal)}px`,
        height: "100%",
        gap: d.scaled(60),
        alignItems: hasImage ? "stretch" : "center",
        position: "relative" as const,
      }
    : {
        padding: `${d.scaled(80)}px ${d.scaled(CARD_PAD.xNormal)}px`,
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
          {TextContent(typed, S, d)}
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

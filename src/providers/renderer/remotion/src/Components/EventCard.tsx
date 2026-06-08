/* ================================================================
   EventCard — 事件卡 (Warm Paper Theme)
   ================================================================

   Layout:
     - No image: text-only centered single column
     - With image: left-text + right-image (image 48% width, gradient mask)
     - With logo: left-text + right-logo (logo 220px wide, contain centered)

   Adapted for Remotion: accepts ElementProps, uses useDesign() for scaling,
   adds entrance animation via useCurrentFrame/interpolate.
*/

import React from "react";
import { useCurrentFrame, interpolate, staticFile } from "remotion";
import type { EventCardProps, AnalysisItem, HeatLevel } from "./cardTypes";
import { COLORS } from "./design";
import type { ElementProps } from "./utils";
import { extractEventProps } from "./propsExtractors";
import { useDesign, FONTS, FW, ANIM, EASE_CARD, CARD_LAYOUT } from "./design";
import { CardShell } from "./CardShell";

/* ---- helpers ---- */

const HEAT_LABELS: Record<HeatLevel, string> = {
  L1: "热度等级 L1",
  L2: "热度等级 L2",
  L3: "热度等级 L3",
};

const HEAT_COLORS: Record<HeatLevel, { bg: string; fg: string }> = {
  L1: { bg: COLORS.sageBg, fg: COLORS.sage },
  L2: { bg: COLORS.goldBg, fg: COLORS.yellow },
  L3: { bg: COLORS.brandSoft, fg: COLORS.brandDeep },
};

const ANALYSIS_META: Record<
  AnalysisItem["type"],
  { label: string; barColor: string; labelColor: string }
> = {
  why: { label: "为何关注", barColor: COLORS.brand, labelColor: COLORS.brandDeep },
  impact: {
    label: "影响分析",
    barColor: COLORS.brandLight,
    labelColor: COLORS.brandDeep,
  },
};

const PULSE = `
@keyframes ec-pulse-dot {
  0%, 100% { opacity: 0.36; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.35); }
}`;

/* ---- inline-styles builder (design-system aligned) ---- */

function buildStyles(d: ReturnType<typeof useDesign>) {
  return {
    dot: {
      width: d.scaled(9),
      height: d.scaled(9),
      borderRadius: "50%",
      background: COLORS.brand,
      animation: "ec-pulse-dot 1.8s ease-in-out 3 both",
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
      background: COLORS.brand,
      color: "#fff",
    } as React.CSSProperties,
    divider: {
      width: "100%",
      maxWidth: d.scaled(CARD_LAYOUT.divider.maxWidth),
      height: d.scaled(CARD_LAYOUT.divider.height),
      borderRadius: d.scaled(CARD_LAYOUT.divider.borderRadius),
      background: `linear-gradient(90deg, ${COLORS.brand}, ${COLORS.brandSoft}, transparent)`,
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
        lineHeight: 1.14,
        letterSpacing: "0",
        color: COLORS.fg,
        fontFamily: FONTS.serifBold,
        maxWidth: maxW,
      }) as React.CSSProperties,
    titleEn: {
      fontSize: d.fs.body,
      color: COLORS.muted,
      fontFamily: FONTS.sans,
      marginTop: d.scaled(-12),
      marginBottom: d.scaled(2),
      lineHeight: 1.4,
    } as React.CSSProperties,
    header: {
      display: "flex",
      alignItems: "center",
      gap: d.scaled(16),
    } as React.CSSProperties,
    stats: {
      display: "flex",
      alignItems: "center",
      gap: d.scaled(12),
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
    metricPill: (bg: string, fg: string) =>
      ({
        display: "inline-flex",
        alignItems: "center",
        gap: d.scaled(4),
        fontFamily: FONTS.mono,
        fontSize: d.fs.pill,
        fontWeight: FW.bold,
        padding: `${d.scaled(6)}px ${d.scaled(14)}px`,
        borderRadius: d.scaled(999),
        background: COLORS.surface2,
        color: COLORS.fg,
        fontVariantNumeric: "tabular-nums",
      }) as React.CSSProperties,
    analysis: {
      display: "flex",
      flexDirection: "column" as const,
      gap: d.scaled(8),
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
        fontFamily: FONTS.sans,
        fontSize: d.fs.subhead,
        fontWeight: FW.heavy,
        color: COLORS.brandDeep,
        display: "flex",
        alignItems: "center",
        gap: d.scaled(8),
      }) as React.CSSProperties,
    anLabelBar: {
      width: d.scaled(4),
      height: d.scaled(18),
      borderRadius: d.scaled(999),
      background: COLORS.brand,
      flexShrink: 0,
    } as React.CSSProperties,
    anText: {
      fontSize: d.fs.bodySmall,
      lineHeight: 1.5,
      color: COLORS.fg,
    } as React.CSSProperties,
    tags: {
      display: "flex",
      gap: d.scaled(8),
      flexWrap: "wrap" as const,
      minWidth: 0,
      justifyContent: "flex-end",
    } as React.CSSProperties,
    tag: {
      display: "inline-block",
      fontFamily: FONTS.sans,
      fontSize: d.fs.bodySmall,
      fontWeight: FW.semibold,
      padding: `${d.scaled(4)}px ${d.scaled(12)}px`,
      borderRadius: d.scaled(999),
      border: `1px solid ${COLORS.border}`,
      background: "rgba(255,255,255,0.48)",
      color: COLORS.muted,
      maxWidth: d.scaled(240),
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap" as const,
    } as React.CSSProperties,
    imageCol: {
      width: d.scaled(800),
      position: "absolute" as const,
      top: d.scaled(-40),
      bottom: d.scaled(40),
      right: d.scaled(CARD_LAYOUT.padding.right),
      display: "flex",
      alignItems: "center",
      overflow: "hidden",
      borderRadius: d.scaled(8),
    } as React.CSSProperties,
    imageImg: {
      width: "100%",
      height: "auto",
      objectFit: "contain" as const,
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

function TextContent(
  props: EventCardProps,
  S: ReturnType<typeof buildStyles>,
  d: ReturnType<typeof useDesign>,
) {
  const {
    domain,
    title,
    englishTitle,
    heatLevel,
    heatLabel,
    hnScore,
    commentCount,
    analysis,
    keywords,
    imageUrl,
  } = props;
  const maxTitleW = imageUrl ? d.layout.contentMaxWidth : d.layout.contentWideMaxWidth;

  return (
    <>
      <h1 style={S.title(maxTitleW)}>{title}</h1>
      {englishTitle && englishTitle !== title && <p style={S.titleEn}>{englishTitle}</p>}
      {domain && <span style={{ ...S.domain, marginTop: d.scaled(-4) }}>{domain}</span>}
      <div style={{ ...S.divider, marginTop: d.scaled(4) }} />
      <div style={{ ...S.stats, marginTop: d.scaled(-4) }}>
        <span style={S.heatLevel(heatLevel)}>{heatLabel || HEAT_LABELS[heatLevel]}</span>
        <span style={S.metricPill(COLORS.surface2, COLORS.fg)}>
          &#x1F525; {hnScore.toLocaleString()}
        </span>
        <span style={S.metricPill(COLORS.surface2, COLORS.fg)}>
          &#x1F4AC; {commentCount.toLocaleString()}
        </span>
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
                  <span style={S.anLabel(m.labelColor)}>
                    <span style={S.anLabelBar} />
                    {m.label}
                  </span>
                  <p style={{ ...S.anText, marginLeft: d.scaled(12) }}>{a.text}</p>
                </div>
              </div>
            );
          })}
        </div>
      )}
      {keywords.length > 0 && (
        <div style={{ ...S.tags, marginTop: d.scaled(-4) }}>
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
  width: _width,
  height: _height,
}) => {
  const frame = useCurrentFrame();
  const d = useDesign();
  const S = buildStyles(d);

  const typed = extractEventProps(elementProps);
  const { index, total, imageUrl, logoUrl } = typed;
  const hasImage = Boolean(imageUrl);
  const hasLogo = Boolean(logoUrl);
  const isTwoCol = hasImage || hasLogo;

  // Entrance animation
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

  // 内容区样式
  const contentStyle: React.CSSProperties = isTwoCol
    ? {
        display: "flex",
        flex: 1,
        gap: d.scaled(60),
        alignItems: hasImage ? "stretch" : "center",
      }
    : {
        display: "flex",
        flexDirection: "column",
        gap: d.scaled(20),
        flex: 1,
      };

  const textColStyle: React.CSSProperties = isTwoCol
    ? {
        flex: 1,
        display: "flex",
        flexDirection: "column",
        gap: d.scaled(20),
        marginRight: d.scaled(820),
      }
    : { display: "flex", flexDirection: "column", gap: d.scaled(20) };

  return (
    <CardShell
      elementProps={elementProps}
      pageIndex={index - 1}
      totalPages={total}
      justify="start" // 两栏时让内容从顶部开始
      gutter={100} // 对称左右内边距
      paddingTop={80}
      paddingBottom={120}
      showTopBar
      showWatermark
      showWaveform
      reserveSubtitle // 字幕始终显示, 底部给字幕让位
    >
      <style>{PULSE}</style>

      <div style={contentStyle}>
        {/* 文字列 */}
        <div
          style={{
            ...textColStyle,
            opacity: innerProgress,
            transform: `translateY(${interpolate(innerProgress, [0, 1], [16, 0])}px)`,
          }}
        >
          {TextContent(typed, S, d)}
        </div>

        {/* 右侧图片 */}
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

        {/* 右侧 Logo */}
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
      </div>
    </CardShell>
  );
};

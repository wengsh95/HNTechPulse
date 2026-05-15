import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { ElementProps, p } from "./utils";
import {
  COLORS,
  FONTS,
  FW,
  FS,
  getCardMaxHeight,
  glassCard,
  glassCardShadow,
  isCompactHeight,
  LAYOUT,
  S,
} from "./design";
import {
  breathingOpacity,
  CapsuleBadge,
  dividerStyle,
  GlassShimmer,
  HighlightEntry,
  KeywordTag,
  overshootTranslateY,
  rowEntryAnimation,
  SectionLabel,
} from "./HighlightShared";

export const CoverCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();

  const headline = p(elementProps, "headline", "HNTech 每日技术速递");
  const keywords = Array.isArray(elementProps.keywords)
    ? elementProps.keywords.filter((k): k is string => typeof k === "string")
    : [];
  const highlightEntries = Array.isArray(elementProps.highlight_entries)
    ? (elementProps.highlight_entries as HighlightEntry[]).slice(0, 3)
    : [];
  const hasHighlights = highlightEntries.length > 0;

  const compact = isCompactHeight(height);
  const cardW = width - LAYOUT.pageInset * 2;
  const cardH = getCardMaxHeight(height);

  const cardProgress = interpolate(frame, [4, 22], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const titleProgress = interpolate(frame, [8, 26], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const bodyProgress = interpolate(frame, [14, 32], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const footerProgress = interpolate(frame, [20, 36], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <div
      style={{
        ...S,
        left: LAYOUT.pageInset,
        top: LAYOUT.topInset,
        width: cardW,
        height: cardH,
        ...glassCard,
        boxShadow: glassCardShadow,
        padding: compact ? "24px 32px" : "28px 36px",
        boxSizing: "border-box",
        opacity: cardProgress,
        transform: `translateY(${overshootTranslateY(cardProgress, 28)}px)`,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <GlassShimmer frame={frame} />

      {/* Header row: capsule badge */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 8,
          marginBottom: compact ? 16 : 20,
          maxWidth: cardW - (compact ? 64 : 72),
          opacity: titleProgress,
          transform: `translateY(${interpolate(titleProgress, [0, 1], [6, 0])}px)`,
        }}
      >
        <CapsuleBadge text="今日速递" />
      </div>

      {/* Headline */}
      <div
        style={{
          opacity: titleProgress,
          transform: `translateY(${interpolate(titleProgress, [0, 1], [24, 0])}px)`,
        }}
      >
        <div
          style={{
            fontFamily: FONTS.bold,
            fontWeight: FW.heavy,
            fontSize: compact ? 44 : FS.hero,
            color: COLORS.text,
            lineHeight: 1.1,
            letterSpacing: -0.5,
          }}
        >
          {headline}
        </div>
      </div>

      {/* Highlight entries */}
      {hasHighlights && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 6,
            marginTop: compact ? 28 : 36,
            flex: 1,
            opacity: bodyProgress,
            transform: `translateY(${interpolate(bodyProgress, [0, 1], [10, 0])}px)`,
          }}
        >
          <SectionLabel text="今日亮点" delay={14} frame={frame} />
          {highlightEntries.map((entry, i) => {
            const rowProgress = rowEntryAnimation(frame, 14 + i * 6, 22);
            const angle =
              entry.editor_angle ||
              entry.title_translation ||
              entry.title_cn ||
              entry.original_title ||
              entry.title ||
              "";
            const why = entry.why_it_matters || entry.next_watch || entry.original_title || "";
            const num = String(i + 1).padStart(2, "0");

            return (
              <div
                key={`${i}-${angle}`}
                style={{
                  position: "relative",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "center",
                  minHeight: 72,
                  padding: "18px 0",
                  opacity: rowProgress,
                  transform: `translateY(${interpolate(rowProgress, [0, 1], [12, 0])}px)`,
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    right: -8,
                    top: -4,
                    fontFamily: FONTS.mono,
                    fontSize: FS.watermarkLg,
                    fontWeight: FW.heavy,
                    color: `rgba(255,255,255,${breathingOpacity(frame)})`,
                    lineHeight: 1,
                    pointerEvents: "none",
                    letterSpacing: -2,
                  }}
                >
                  {num}
                </div>
                <div style={{ minWidth: 0, position: "relative", zIndex: 1 }}>
                  <div
                    style={{
                      fontFamily: FONTS.bold,
                      fontSize: compact ? 24 : FS.subhead,
                      lineHeight: 1.3,
                      fontWeight: FW.heavy,
                      color: COLORS.text,
                      overflow: "hidden",
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical" as const,
                    }}
                  >
                    {angle}
                  </div>
                  {why && (
                    <div
                      style={{
                        fontFamily: FONTS.sans,
                        fontSize: compact ? FS.body : FS.bodyLg,
                        lineHeight: 1.45,
                        fontWeight: FW.medium,
                        color: COLORS.textSecondary,
                        marginTop: 6,
                        overflow: "hidden",
                        display: "-webkit-box",
                        WebkitLineClamp: 1,
                        WebkitBoxOrient: "vertical" as const,
                      }}
                    >
                      {why}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Keywords */}
      {keywords.length > 0 && (
        <>
          <div style={dividerStyle} />
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              justifyContent: "flex-start",
              gap: 8,
              opacity: footerProgress,
            }}
          >
            {keywords.slice(0, 3).map((kw, i) => (
              <KeywordTag key={kw} keyword={kw} delay={20 + i * 4} frame={frame} />
            ))}
          </div>
        </>
      )}
    </div>
  );
};

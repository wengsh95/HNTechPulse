import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { ElementProps, p } from "./utils";
import {
  COLORS,
  FONTS,
  FW,
  getCardMaxHeight,
  glassCard,
  glassCardShadow,
  isCompactHeight,
  LAYOUT,
  S,
} from "./design";
import { HighlightEntry, rowEntryAnimation } from "./HighlightShared";

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
  const titleProgress = interpolate(frame, [10, 32], [0, 1], {
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
        transform: `translateY(${interpolate(cardProgress, [0, 1], [28, 0])}px)`,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
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
            fontSize: compact ? 44 : 52,
            color: COLORS.text,
            lineHeight: 1.1,
            letterSpacing: -0.5,
          }}
        >
          {headline}
        </div>

        {keywords.length > 0 && (
          <div
            style={{
              display: "flex",
              gap: 10,
              marginTop: 20,
              flexWrap: "wrap",
            }}
          >
            {keywords.slice(0, 3).map((kw, i) => {
              const tagProgress = interpolate(frame, [28 + i * 5, 46 + i * 5], [0, 1], {
                easing: Easing.bezier(0.16, 1, 0.3, 1),
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
              });
              return (
                <div
                  key={kw}
                  style={{
                    padding: "8px 16px",
                    borderRadius: 8,
                    background: "rgba(255,255,255,0.08)",
                    fontFamily: FONTS.sans,
                    fontSize: 16,
                    fontWeight: FW.medium,
                    color: COLORS.text,
                    maxWidth: 280,
                    overflow: "hidden",
                    whiteSpace: "nowrap",
                    textOverflow: "ellipsis",
                    opacity: tagProgress,
                    transform: `translateY(${interpolate(tagProgress, [0, 1], [10, 0])}px)`,
                  }}
                >
                  {kw}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {hasHighlights && (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 6,
            marginTop: compact ? 28 : 36,
            flex: 1,
          }}
        >
          {highlightEntries.map((entry, i) => {
            const rowProgress = rowEntryAnimation(frame, 20 + i * 6, 22);
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
                    fontSize: 84,
                    fontWeight: FW.heavy,
                    color: "rgba(255,255,255,0.04)",
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
                      fontSize: compact ? 24 : 28,
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
                        fontSize: compact ? 16 : 18,
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
    </div>
  );
};

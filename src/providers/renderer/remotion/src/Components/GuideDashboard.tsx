import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

import { ElementProps, UI_TEXT } from "./utils";
import { COLORS, FONTS, glassCard, glassCardShadow, LAYOUT, S } from "./design";
import {
  DashboardEntry,
  MedalBadge,
  CategoryBadge,
  KeywordTags,
  PageIndicator,
  rowEntryAnimation,
  medalSets,
} from "./DashboardShared";

export const GuideDashboard: React.FC<{
  entries: DashboardEntry[];
  frame: number;
  fps: number;
  width: number;
  height: number;
  duration: number;
  focusCount: number;
}> = ({ entries, frame, fps, width, height, duration, focusCount }) => {
  const cardW = width - LAYOUT.pageInset * 2;
  const cardTop = LAYOUT.topInset;

  const cardProgress = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  const guideEntries = entries.slice(0, Math.max(3, Math.min(5, focusCount || 3)));

  return (
    <div
      style={{
        ...S,
        left: LAYOUT.pageInset,
        top: cardTop,
        width: cardW,
        ...glassCard,
        padding: "40px 48px",
        boxShadow: glassCardShadow,
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [28, 0])}px)`,
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          gap: 16,
          marginBottom: 24,
        }}
      >
        <div
          style={{
            fontFamily: FONTS.bold,
            fontWeight: 760,
            fontSize: 36,
            color: COLORS.text,
            lineHeight: 1.12,
            letterSpacing: 0,
          }}
        >
          今日 {Math.min(guideEntries.length, focusCount)} 个信号
        </div>
        <div
          style={{
            fontFamily: FONTS.sans,
            fontSize: 13,
            fontWeight: 700,
            color: COLORS.accentLight,
            backgroundColor: COLORS.accentBg,
            borderRadius: 999,
            padding: "6px 12px",
          }}
        >
          重点观察
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {guideEntries.map((entry, i) => {
          const rowStart = 10 + i * 5;
          const rowProgress = rowEntryAnimation(frame, rowStart, 20);
          const rank = entry.rank || i + 1;
          const angle = entry.editor_angle || entry.title_translation || entry.title_cn || entry.original_title || entry.title || "";
          const why = entry.why_it_matters || entry.next_watch || entry.original_title || "";
          const keywords = entry.keywords ?? [];
          const category = entry.category || "";
          const medal = rank <= 3 ? medalSets[rank - 1] : null;

          return (
            <div
              key={i}
              style={{
                display: "grid",
                gridTemplateColumns: "44px 1fr 128px",
                columnGap: 18,
                alignItems: "center",
                minHeight: 86,
                padding: "12px 16px",
                borderRadius: 10,
                backgroundColor: i < focusCount ? "rgba(255,255,255,0.055)" : "rgba(255,255,255,0.028)",
                border: "1px solid rgba(255,255,255,0.055)",
                opacity: rowProgress,
                transform: `translateY(${interpolate(rowProgress, [0, 1], [16, 0])}px)`,
              }}
            >
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: 34,
                  height: 34,
                  borderRadius: 17,
                  backgroundColor: medal?.bg ?? "rgba(255,255,255,0.07)",
                  border: `1.5px solid ${medal?.ring ?? "rgba(255,255,255,0.12)"}`,
                  fontFamily: FONTS.mono,
                  fontSize: 15,
                  fontWeight: 800,
                  color: medal?.text ?? COLORS.textSecondary,
                }}
              >
                {rank}
              </div>

              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: 22,
                    lineHeight: 1.28,
                    fontWeight: 750,
                    color: COLORS.text,
                    overflow: "hidden",
                    display: "-webkit-box",
                    WebkitLineClamp: 1,
                    WebkitBoxOrient: "vertical" as const,
                  }}
                >
                  {angle}
                </div>
                {why && (
                  <div
                    style={{
                      fontFamily: FONTS.sans,
                      fontSize: 14,
                      lineHeight: 1.36,
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

              <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8 }}>
                {category && <CategoryBadge category={category} />}
                <div style={{ display: "flex", gap: 8, color: COLORS.textTertiary, fontFamily: FONTS.mono, fontSize: 13 }}>
                  <span>{entry.score || 0}</span>
                  <span>·</span>
                  <span>{entry.comment_count || 0}评</span>
                </div>
                {keywords.length > 0 && <KeywordTags keywords={keywords} />}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

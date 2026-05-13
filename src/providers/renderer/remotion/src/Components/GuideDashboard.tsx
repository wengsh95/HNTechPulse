import React from "react";
import { interpolate, Easing } from "remotion";

import { COLORS, FONTS, FW, glassCard, glassCardShadow, LAYOUT, S } from "./design";
import {
  DashboardEntry,
  CategoryBadge,
  KeywordTags,
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
        padding: "28px 36px",
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
            fontWeight: FW.heavy,
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
            fontWeight: FW.bold,
            color: COLORS.accentLight,
            backgroundColor: COLORS.accentBg,
            borderRadius: 6,
            padding: "6px 12px",
          }}
        >
          重点观察
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
        {guideEntries.map((entry, i) => {
          const rowStart = 10 + i * 5;
          const rowProgress = rowEntryAnimation(frame, rowStart, 22);
          const rank = entry.rank || i + 1;
          const angle = entry.editor_angle || entry.title_translation || entry.title_cn || entry.original_title || entry.title || "";
          const why = entry.why_it_matters || entry.next_watch || entry.original_title || "";
          const keywords = entry.keywords ?? [];
          const category = entry.category || "";
          const medal = rank <= 3 ? medalSets[rank - 1] : null;
          const isLast = i === guideEntries.length - 1;

          return (
            <div
              key={i}
              style={{
                display: "grid",
                gridTemplateColumns: "48px 1fr 132px",
                columnGap: 18,
                alignItems: "center",
                minHeight: 86,
                padding: "14px 16px",
                borderRadius: 0,
                backgroundColor: "transparent",
                borderBottom: isLast ? "none" : "1px solid rgba(255,255,255,0.06)",
                borderTop: "none",
                borderLeft: "none",
                borderRight: "none",
                opacity: rowProgress,
                transform: `translateY(${interpolate(rowProgress, [0, 1], [12, 0])}px)`,
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
                  backgroundColor: medal?.bg ?? "rgba(255,255,255,0.06)",
                  border: `1.5px solid ${medal?.ring ?? "rgba(255,255,255,0.10)"}`,
                  fontFamily: FONTS.mono,
                  fontSize: 15,
                  fontWeight: FW.heavy,
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
                    lineHeight: 1.32,
                    fontWeight: FW.bold,
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
                      lineHeight: 1.42,
                      fontWeight: FW.regular,
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
                <div style={{ display: "flex", gap: 8, color: COLORS.textTertiary, fontFamily: FONTS.mono, fontSize: 13, fontWeight: FW.medium }}>
                  <span style={{ color: COLORS.text }}>{entry.score || 0}</span>
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

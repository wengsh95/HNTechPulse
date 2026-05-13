import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

import { ElementProps, UI_TEXT } from "./utils";
import { COLORS, FONTS, FW, glassCard, glassCardShadow, LAYOUT, S } from "./design";
import {
  DashboardEntry,
  MedalBadge,
  PageIndicator,
  rowEntryAnimation,
} from "./DashboardShared";

export const RankingDashboard: React.FC<{
  entries: DashboardEntry[];
  frame: number;
  fps: number;
  width: number;
  height: number;
  duration: number;
}> = ({ entries, frame, fps, width, height, duration }) => {
  const cardW = width - LAYOUT.pageInset * 2;
  const rowH = 76;
  const perPage = 5;

  const allEntries = entries.slice(0, 10);
  const pages: typeof allEntries[] = [];
  for (let i = 0; i < allEntries.length; i += perPage) {
    pages.push(allEntries.slice(i, i + perPage));
  }
  const totalPages = pages.length;

  const halfFrame = Math.floor((duration / 2) * fps);
  const transitionFrames = 12;
  const currentPage = totalPages <= 1 ? 0 : (frame < halfFrame ? 0 : 1);
  const pageEntries = pages[currentPage] ?? pages[0] ?? [];

  const maxScore = Math.max(1, ...pageEntries.map((e) => e.score || 0));

  const pageFadeProgress = currentPage === 0
    ? interpolate(frame, [halfFrame - transitionFrames, halfFrame], [1, 0], {
        easing: Easing.bezier(0.16, 1, 0.3, 1),
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : interpolate(frame, [halfFrame, halfFrame + transitionFrames], [0, 1], {
        easing: Easing.bezier(0.16, 1, 0.3, 1),
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });

  const cardTop = LAYOUT.topInset;
  const cardPadTop = 44;
  const cardPadBottom = 40;
  const titleAreaH = 88;
  const headerH = 34;
  const cardChrome = cardPadTop + titleAreaH + headerH + cardPadBottom;
  const maxVisibleH = height - cardTop - 20;
  const visibleRowsH = maxVisibleH - cardChrome;

  const cardProgress = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

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
      }}
    >
      <div
        style={{
          fontFamily: FONTS.bold,
          fontWeight: FW.bold,
          fontSize: 34,
          color: COLORS.text,
          marginBottom: 24,
          letterSpacing: 0,
          display: "flex",
          alignItems: "baseline",
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <span>{UI_TEXT.topStories}</span>
        <span
          style={{
            fontFamily: FONTS.mono,
            fontSize: 12,
            fontWeight: FW.bold,
            color: COLORS.accentLight,
            backgroundColor: COLORS.accentBg,
            borderRadius: 6,
            padding: "5px 12px",
            letterSpacing: 0.6,
            textTransform: "uppercase",
          }}
        >
          {UI_TEXT.top10}
        </span>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          fontFamily: FONTS.sans,
          fontSize: 11,
          fontWeight: FW.semibold,
          color: COLORS.textTertiary,
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          paddingBottom: 12,
          marginBottom: 8,
          textTransform: "uppercase",
          letterSpacing: 0.8,
        }}
      >
        <span style={{ width: 56 }}>#</span>
        <span style={{ flex: 1 }}>{UI_TEXT.title}</span>
        <span style={{ width: 130, textAlign: "right" }}>{UI_TEXT.heat}</span>
        <span style={{ width: 72, textAlign: "right" }}>{UI_TEXT.comments}</span>
      </div>

      <div style={{ overflow: "hidden", height: visibleRowsH, borderRadius: 0, opacity: pageFadeProgress }}>
        <div>
          {pageEntries.map((entry, i) => {
            const title = entry.original_title || entry.title || "";
            const titleCn = entry.title_translation || entry.title_cn || "";
            const mainTitle = entry.editor_angle || titleCn || title;
            const rank = entry.rank || (currentPage * perPage + i + 1);
            const score = entry.score || 0;

            const pageStartFrame = currentPage === 0 ? 0 : halfFrame;
            const rowStart = pageStartFrame + 6 + i * 5;
            const rowProgress = rowEntryAnimation(frame, rowStart, 14);

            const barTarget = Math.round((score / maxScore) * 40);
            const barWidth = Math.round(interpolate(rowProgress, [0, 1], [0, barTarget]));

            const isMedal = rank <= 3;
            const isLast = i === pageEntries.length - 1;

            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  fontFamily: FONTS.sans,
                  minHeight: rowH,
                  paddingTop: 12,
                  paddingBottom: 12,
                  borderBottom: isLast ? "none" : "1px solid rgba(255,255,255,0.06)",
                  opacity: interpolate(rowProgress, [0, 1], [0.4, 1]),
                  transform: `translateY(${interpolate(rowProgress, [0, 1], [18, 0])}px)`,
                }}
              >
                <span style={{ width: 56, display: "flex", alignItems: "center", paddingTop: 4 }}>
                  <MedalBadge rank={rank} />
                </span>

                <span
                  style={{
                    flex: 1,
                    minWidth: 0,
                    paddingRight: 24,
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                  }}
                >
                  <span
                    style={{
                      lineHeight: 1.42,
                      overflow: "hidden",
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical" as const,
                      fontWeight: FW.medium,
                      fontSize: 20,
                      color: COLORS.text,
                      maxWidth: LAYOUT.contentMaxWidth,
                    }}
                  >
                    {mainTitle}
                  </span>
                  {entry.editor_angle && (titleCn || title) && (
                    <span
                      style={{
                        fontSize: 13,
                        color: COLORS.textSecondary,
                        lineHeight: 1.45,
                        overflow: "hidden",
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical" as const,
                        fontWeight: FW.regular,
                        maxWidth: LAYOUT.contentMaxWidth,
                      }}
                    >
                      {titleCn || title}
                    </span>
                  )}
                </span>

                <span
                  style={{
                    width: 130,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "flex-end",
                    gap: 8,
                    flexShrink: 0,
                    paddingTop: 6,
                  }}
                >
                  <div
                    style={{
                      width: 40,
                      height: 6,
                      borderRadius: 3,
                      background: "rgba(255,255,255,0.08)",
                      overflow: "hidden",
                      flexShrink: 0,
                    }}
                  >
                    <div
                      style={{
                        width: barWidth,
                        height: "100%",
                        borderRadius: 3,
                        background: isMedal
                          ? COLORS.accent
                          : COLORS.accentLight,
                      }}
                    />
                  </div>
                  <span
                    style={{
                      fontFamily: FONTS.mono,
                      fontSize: 16,
                      fontWeight: FW.semibold,
                      color: isMedal ? COLORS.accentLight : COLORS.text,
                      width: 36,
                      textAlign: "right",
                    }}
                  >
                    {score}
                  </span>
                </span>

                <span
                  style={{
                    width: 72,
                    textAlign: "right",
                    fontFamily: FONTS.mono,
                    fontSize: 16,
                    fontWeight: FW.medium,
                    color: COLORS.textSecondary,
                    flexShrink: 0,
                    paddingTop: 7,
                  }}
                >
                  {entry.comment_count || 0}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {totalPages > 1 && <PageIndicator pages={pages} currentPage={currentPage} />}
    </div>
  );
};

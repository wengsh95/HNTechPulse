import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

import { ElementProps } from "./utils";
import { COLORS, FONTS, S } from "./design";

export const DashboardCard: React.FC<ElementProps> = ({ elementProps, width, height, duration }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const entries = (elementProps.entries as Array<{
    rank?: number;
    original_title?: string;
    title?: string;
    title_translation?: string;
    title_cn?: string;
    score?: number;
    comment_count?: number;
  }>) ?? [];

  const cardW = width - 160;
  const rowH = 64;
  const headerH = 30;
  const perPage = 5;

  // Split entries into pages
  const allEntries = entries.slice(0, 10);
  const pages: typeof allEntries[] = [];
  for (let i = 0; i < allEntries.length; i += perPage) {
    pages.push(allEntries.slice(i, i + perPage));
  }
  const totalPages = pages.length;

  // Page switching: use first half of duration for page 1, second half for page 2
  const halfFrame = Math.floor((duration / 2) * fps);
  const transitionFrames = 12; // fade transition duration
  const currentPage = frame < halfFrame ? 0 : 1;
  const pageEntries = pages[currentPage] ?? pages[0];

  // Page fade transition
  const pageFadeProgress = currentPage === 0
    ? interpolate(frame, [halfFrame - transitionFrames, halfFrame], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
    : interpolate(frame, [halfFrame, halfFrame + transitionFrames], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const numRows = pageEntries.length;
  const totalRowsH = numRows * rowH;

  // Card layout: fixed position
  const cardTop = 60;
  const cardPadTop = 44;
  const cardPadBottom = 40;
  const titleAreaH = 74;
  const cardChrome = cardPadTop + titleAreaH + headerH + cardPadBottom;
  const maxVisibleH = height - cardTop - 20;
  const visibleRowsH = maxVisibleH - cardChrome;

  const topY = cardTop;

  // Card entrance: fade + slide up (Apple deceleration curve)
  const cardProgress = interpolate(frame, [0, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  const medalSets = [
    { text: "#a0740a", bg: "#fef7e0", ring: "#e5a810" },
    { text: "#5c6b7a", bg: "#f0f2f5", ring: "#9aa3af" },
    { text: "#a0512b", bg: "#fef3ec", ring: "#d4885c" },
  ];

  return (
    <div
      style={{
        ...S,
        left: 80,
        top: topY,
        width: cardW,
        background: "#ffffff",
        borderRadius: 24,
        padding: "44px 48px 40px",
        boxShadow:
          "0 0 0 0.5px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04), 0 8px 32px rgba(0,0,0,0.07)",
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [28, 0])}px)`,
      }}
    >
      {/* Title */}
      <div
        style={{
          fontFamily: FONTS.bold,
          fontWeight: 700,
          fontSize: 32,
          color: COLORS.text,
          marginBottom: 32,
          letterSpacing: -0.6,
          display: "flex",
          alignItems: "baseline",
          gap: 12,
        }}
      >
        <span>今日热度</span>
        <span
          style={{
            fontFamily: FONTS.mono,
            fontSize: 13,
            fontWeight: 700,
            color: COLORS.accent,
            backgroundColor: COLORS.accent + "10",
            borderRadius: 14,
            padding: "5px 14px",
            letterSpacing: 0.6,
            textTransform: "uppercase",
          }}
        >
          Top 10
        </span>
      </div>

      {/* Column headers */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          fontFamily: FONTS.sans,
          fontSize: 12,
          fontWeight: 600,
          color: COLORS.dim,
          borderBottom: "0.5px solid rgba(0,0,0,0.06)",
          paddingBottom: 14,
          marginBottom: 4,
          textTransform: "uppercase",
          letterSpacing: 0.8,
        }}
      >
        <span style={{ width: 52 }}>#</span>
        <span style={{ flex: 1 }}>标题</span>
        <span style={{ width: 88, textAlign: "right" }}>热度</span>
        <span style={{ width: 76, textAlign: "right" }}>评论</span>
      </div>

      {/* Rows */}
      <div style={{ overflow: "hidden", height: visibleRowsH, borderRadius: 4, opacity: pageFadeProgress }}>
        <div>
          {pageEntries.map((entry, i) => {
            const title = entry.original_title || entry.title || "";
            const titleCn = entry.title_translation || entry.title_cn || "";
            const rank = entry.rank || (currentPage * perPage + i + 1);

            // Staggered row entrance: each row arrives 4 frames after the previous
            const pageStartFrame = currentPage === 0 ? 0 : halfFrame;
            const rowStart = pageStartFrame + 10 + i * 4;
            const rowProgress = interpolate(frame, [rowStart, rowStart + 20], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            });

            const isMedal = rank <= 3;
            const medal = isMedal ? medalSets[rank - 1] : null;
            const isLast = i === numRows - 1;

            return (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  fontFamily: FONTS.sans,
                  minHeight: rowH,
                  borderBottom: isLast ? "none" : "0.5px solid rgba(0,0,0,0.04)",
                  opacity: rowProgress,
                  transform: `translateY(${interpolate(rowProgress, [0, 1], [18, 0])}px)`,
                }}
              >
            {/* Rank */}
            <span style={{ width: 52, display: "flex", alignItems: "center" }}>
              {isMedal ? (
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: 28,
                    height: 28,
                    borderRadius: 14,
                    backgroundColor: medal!.bg,
                    border: `1.5px solid ${medal!.ring}`,
                    fontFamily: FONTS.mono,
                    fontSize: 14,
                    fontWeight: 700,
                    color: medal!.text,
                    lineHeight: 1,
                  }}
                >
                  {rank}
                </span>
              ) : (
                <span
                  style={{
                    fontFamily: FONTS.mono,
                    fontSize: 17,
                    fontWeight: 500,
                    color: COLORS.dim,
                  }}
                >
                  {rank}
                </span>
              )}
            </span>

            {/* Title */}
            <span
              style={{
                flex: 1,
                paddingRight: 20,
                display: "flex",
                flexDirection: "column",
                gap: 4,
              }}
            >
              <span
                style={{
                  lineHeight: 1.35,
                  overflow: "hidden",
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical" as const,
                  fontWeight: 500,
                  fontSize: 19,
                  color: COLORS.text,
                }}
              >
                {titleCn || title}
              </span>
              {titleCn && title && (
                <span
                  style={{
                    fontSize: 14,
                    color: COLORS.dim,
                    lineHeight: 1.3,
                    overflow: "hidden",
                    display: "-webkit-box",
                    WebkitLineClamp: 1,
                    WebkitBoxOrient: "vertical" as const,
                    fontWeight: 400,
                  }}
                >
                  {title}
                </span>
              )}
            </span>

            {/* Score */}
            <span
              style={{
                width: 88,
                textAlign: "right",
                fontFamily: FONTS.mono,
                fontSize: 18,
                fontWeight: 600,
                color: isMedal ? COLORS.accent : COLORS.text,
                flexShrink: 0,
              }}
            >
              {entry.score || 0}
            </span>

            {/* Comments */}
            <span
              style={{
                width: 76,
                textAlign: "right",
                fontFamily: FONTS.mono,
                fontSize: 16,
                fontWeight: 500,
                color: COLORS.dim,
                flexShrink: 0,
              }}
            >
              {entry.comment_count || 0}
            </span>
          </div>
        );
      })}
      </div>

      {/* Page indicator */}
      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 16 }}>
          {pages.map((_, pi) => (
            <div
              key={pi}
              style={{
                width: pi === currentPage ? 24 : 8,
                height: 8,
                borderRadius: 4,
                backgroundColor: pi === currentPage ? COLORS.accent : COLORS.border,
                transition: "all 0.3s",
              }}
            />
          ))}
        </div>
      )}
    </div>
    </div>
  );
};

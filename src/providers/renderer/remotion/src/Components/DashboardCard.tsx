import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

import { ElementProps, UI_TEXT } from "./utils";
import { COLORS, FONTS, glassCard, glassCardShadow, LAYOUT, S } from "./design";

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
    editor_angle?: string;
    why_it_matters?: string;
    next_watch?: string;
    category?: string;
    keywords?: string[];
  }>) ?? [];
  const mode = elementProps.mode === "guide" ? "guide" : "ranking";
  const focusCount = Number(elementProps.focus_count) || 3;

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
  const currentPage = frame < halfFrame ? 0 : 1;
  const pageEntries = pages[currentPage] ?? pages[0] ?? [];

  const pageFadeProgress = currentPage === 0
    ? interpolate(frame, [halfFrame - transitionFrames, halfFrame], [1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : interpolate(frame, [halfFrame, halfFrame + transitionFrames], [0, 1], {
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

  const medalSets = [
    { text: "#f5c542", bg: "rgba(245,197,66,0.15)", ring: "rgba(245,197,66,0.4)" },
    { text: "#bcc4d0", bg: "rgba(188,196,208,0.12)", ring: "rgba(188,196,208,0.3)" },
    { text: "#d4a574", bg: "rgba(212,165,116,0.15)", ring: "rgba(212,165,116,0.35)" },
  ];

  const guideEntries = entries.slice(0, Math.max(3, Math.min(5, focusCount || 3)));

  if (mode === "guide") {
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
            const rowProgress = interpolate(frame, [rowStart, rowStart + 20], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            });
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
                  {category && (
                    <div
                      style={{
                        fontFamily: FONTS.sans,
                        fontSize: 12,
                        fontWeight: 700,
                        color: COLORS.accentLight,
                        backgroundColor: COLORS.accentBg,
                        borderRadius: 999,
                        padding: "5px 10px",
                        maxWidth: 120,
                        overflow: "hidden",
                        whiteSpace: "nowrap",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {category}
                    </div>
                  )}
                  <div style={{ display: "flex", gap: 8, color: COLORS.textTertiary, fontFamily: FONTS.mono, fontSize: 13 }}>
                    <span>{entry.score || 0}</span>
                    <span>·</span>
                    <span>{entry.comment_count || 0}评</span>
                  </div>
                  {keywords.length > 0 && (
                    <div style={{ display: "flex", gap: 5 }}>
                      {keywords.slice(0, 2).map((kw) => (
                        <span
                          key={kw}
                          style={{
                            fontFamily: FONTS.sans,
                            fontSize: 10,
                            color: COLORS.textTertiary,
                            maxWidth: 46,
                            overflow: "hidden",
                            whiteSpace: "nowrap",
                            textOverflow: "ellipsis",
                          }}
                        >
                          {kw}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

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
      }}
    >
      <div
        style={{
          fontFamily: FONTS.bold,
          fontWeight: 700,
          fontSize: 34,
          color: COLORS.text,
          marginBottom: 24,
          letterSpacing: -0.7,
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
            fontWeight: 700,
            color: COLORS.accentLight,
            backgroundColor: COLORS.accentBg,
            borderRadius: 999,
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
          fontWeight: 600,
          color: COLORS.textTertiary,
          borderBottom: "0.5px solid rgba(255,255,255,0.06)",
          paddingBottom: 12,
          marginBottom: 8,
          textTransform: "uppercase",
          letterSpacing: 0.8,
        }}
      >
        <span style={{ width: 56 }}>#</span>
        <span style={{ flex: 1 }}>{UI_TEXT.title}</span>
        <span style={{ width: 96, textAlign: "right" }}>{UI_TEXT.heat}</span>
        <span style={{ width: 82, textAlign: "right" }}>{UI_TEXT.comments}</span>
      </div>

      <div style={{ overflow: "hidden", height: visibleRowsH, borderRadius: 8, opacity: pageFadeProgress }}>
        <div>
          {pageEntries.map((entry, i) => {
            const title = entry.original_title || entry.title || "";
            const titleCn = entry.title_translation || entry.title_cn || "";
            const rank = entry.rank || (currentPage * perPage + i + 1);

            const pageStartFrame = currentPage === 0 ? 0 : halfFrame;
            const rowStart = pageStartFrame + 6 + i * 3;
            const rowProgress = interpolate(frame, [rowStart, rowStart + 12], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            });

            const isMedal = rank <= 3;
            const medal = isMedal ? medalSets[rank - 1] : null;
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
                  borderBottom: isLast ? "none" : "0.5px solid rgba(255,255,255,0.04)",
                  opacity: interpolate(rowProgress, [0, 1], [0.48, 1]),
                  transform: `translateY(${interpolate(rowProgress, [0, 1], [18, 0])}px)`,
                }}
              >
                <span style={{ width: 56, display: "flex", alignItems: "center", paddingTop: 4 }}>
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
                        color: COLORS.textTertiary,
                      }}
                    >
                      {rank}
                    </span>
                  )}
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
                      fontWeight: 500,
                      fontSize: 20,
                      color: COLORS.text,
                      maxWidth: LAYOUT.contentMaxWidth,
                    }}
                  >
                    {titleCn || title}
                  </span>
                  {titleCn && title && (
                    <span
                      style={{
                        fontSize: 13,
                        color: COLORS.textSecondary,
                        lineHeight: 1.45,
                        overflow: "hidden",
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical" as const,
                        fontWeight: 400,
                        maxWidth: LAYOUT.contentMaxWidth,
                      }}
                    >
                      {title}
                    </span>
                  )}
                </span>

                <span
                  style={{
                    width: 96,
                    textAlign: "right",
                    fontFamily: FONTS.mono,
                    fontSize: 18,
                    fontWeight: 600,
                    color: isMedal ? COLORS.accentLight : COLORS.text,
                    flexShrink: 0,
                    paddingTop: 6,
                  }}
                >
                  {entry.score || 0}
                </span>

                <span
                  style={{
                    width: 82,
                    textAlign: "right",
                    fontFamily: FONTS.mono,
                    fontSize: 16,
                    fontWeight: 500,
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

      {totalPages > 1 && (
        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 16 }}>
          {pages.map((_, pi) => (
            <div
              key={pi}
              style={{
                width: pi === currentPage ? 24 : 8,
                height: 8,
                borderRadius: 4,
                backgroundColor: pi === currentPage ? COLORS.accent : "rgba(255,255,255,0.12)",
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
};

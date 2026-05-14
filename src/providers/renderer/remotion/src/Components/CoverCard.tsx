import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing, staticFile } from "remotion";

import { ElementProps, p } from "./utils";
import { COLORS, FONTS, FW, glassCard, glassCardShadow, LAYOUT, S } from "./design";
import {
  HighlightEntry,
  CategoryBadge,
  KeywordTags,
  medalSets,
  rowEntryAnimation,
} from "./HighlightShared";

export const CoverCard: React.FC<ElementProps> = ({ elementProps, duration }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const headline = p(elementProps, "headline", "HNTech 每日技术速递");
  const subtitle = p(elementProps, "subtitle", "");
  const coverImage = p(elementProps, "cover_image", "");
  const keywords = Array.isArray(elementProps.keywords)
    ? elementProps.keywords.filter((k): k is string => typeof k === "string")
    : [];
  const highlightEntries = Array.isArray(elementProps.highlight_entries)
    ? (elementProps.highlight_entries as HighlightEntry[]).slice(0, 3)
    : [];
  const resolvedImage = coverImage ? staticFile(coverImage) : "";
  const hasHighlights = highlightEntries.length > 0;

  const brandProgress = interpolate(frame, [0, 16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const titleProgress = interpolate(frame, [6, 28], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const bodyProgress = interpolate(frame, [18, 42], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  const totalFrames = Math.max(1, Math.round((duration || 5) * fps));
  const kenBurnsScale = interpolate(frame, [0, totalFrames], [1.0, 1.06], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        ...S,
        left: 0,
        top: 0,
        width: "100%",
        height: "100%",
        background: COLORS.bg,
        overflow: "hidden",
      }}
    >
      {resolvedImage && (
        <>
          <img
            src={resolvedImage}
            alt=""
            style={{
              ...S,
              left: 0,
              top: 0,
              width: "100%",
              height: "100%",
              objectFit: "cover",
              opacity: 0.28,
              transform: `scale(${kenBurnsScale})`,
            }}
          />
          <div
            style={{
              ...S,
              left: 0,
              top: 0,
              width: "100%",
              height: "100%",
              background:
                "linear-gradient(180deg, rgba(13,13,15,0.88) 0%, rgba(13,13,15,0.72) 42%, rgba(13,13,15,0.94) 100%)",
            }}
          />
        </>
      )}

      <div
        style={{
          position: "absolute",
          left: LAYOUT.chromeInsetX,
          right: LAYOUT.chromeInsetX,
          top: LAYOUT.chromeTop,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          fontFamily: FONTS.sans,
          opacity: brandProgress,
          transform: `translateY(${interpolate(brandProgress, [0, 1], [-8, 0])}px)`,
        }}
      >
        <div
          style={{
            fontFamily: FONTS.bold,
            fontSize: 22,
            fontWeight: FW.heavy,
            color: COLORS.text,
          }}
        >
          <span style={{ color: COLORS.brand }}>HN</span> TechPulse
        </div>
        {subtitle && (
          <div
            style={{
              fontSize: 16,
              fontWeight: FW.bold,
              color: COLORS.textSecondary,
            }}
          >
            {subtitle}
          </div>
        )}
      </div>

      <div
        style={{
          position: "absolute",
          left: LAYOUT.pageInset,
          right: LAYOUT.pageInset,
          top: 92,
          bottom: 118,
          display: "grid",
          gridTemplateRows: hasHighlights ? "auto auto" : "1fr",
          rowGap: hasHighlights ? 24 : 0,
          alignContent: "start",
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
              fontSize: hasHighlights ? 58 : 68,
              color: COLORS.text,
              lineHeight: 1.08,
              letterSpacing: 0,
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
                const tagProgress = interpolate(frame, [24 + i * 5, 42 + i * 5], [0, 1], {
                  easing: Easing.bezier(0.16, 1, 0.3, 1),
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                });
                return (
                  <div
                    key={kw}
                    style={{
                      padding: "9px 16px",
                      borderRadius: 8,
                      background: "rgba(255,255,255,0.08)",
                      fontFamily: FONTS.sans,
                      fontSize: 15,
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
              display: "grid",
              gridTemplateColumns: "210px 1fr",
              columnGap: 30,
              alignItems: "start",
              ...glassCard,
              boxShadow: glassCardShadow,
              padding: "24px 30px",
              boxSizing: "border-box",
              minHeight: 316,
              overflow: "hidden",
              alignSelf: "start",
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [22, 0])}px)`,
            }}
          >
            <div>
              <div
                style={{
                  fontFamily: FONTS.bold,
                  fontWeight: FW.heavy,
                  fontSize: 30,
                  lineHeight: 1.08,
                  color: COLORS.text,
                  letterSpacing: 0,
                }}
              >
                今日亮点
              </div>
              <div
                style={{
                  display: "inline-flex",
                  marginTop: 12,
                  padding: "7px 12px",
                  borderRadius: LAYOUT.chipRadius,
                  backgroundColor: COLORS.accentBg,
                  fontFamily: FONTS.sans,
                  fontSize: 12,
                  fontWeight: FW.bold,
                  color: COLORS.accentLight,
                }}
              >
                Top 3
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
              {highlightEntries.map((entry, i) => {
                const rowProgress = rowEntryAnimation(frame, 24 + i * 6, 22);
                const rank = entry.rank || i + 1;
                const angle =
                  entry.editor_angle ||
                  entry.title_translation ||
                  entry.title_cn ||
                  entry.original_title ||
                  entry.title ||
                  "";
                const why = entry.why_it_matters || entry.next_watch || entry.original_title || "";
                const category = entry.category || "";
                const keywordsForEntry = entry.keywords ?? [];
                const medal = rank <= 3 ? medalSets[rank - 1] : null;
                const isLast = i === highlightEntries.length - 1;

                return (
                  <div
                    key={`${rank}-${angle}`}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "48px minmax(0, 1fr) 152px",
                      columnGap: 20,
                      alignItems: "center",
                      minHeight: 72,
                      padding: "10px 0",
                      borderBottom: isLast ? "none" : "1px solid rgba(255,255,255,0.07)",
                      opacity: rowProgress,
                      transform: `translateY(${interpolate(rowProgress, [0, 1], [12, 0])}px)`,
                    }}
                  >
                    <div
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: 36,
                        height: 36,
                        borderRadius: 18,
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
                          fontSize: 23,
                          lineHeight: 1.28,
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
                            fontSize: 15,
                            lineHeight: 1.4,
                            fontWeight: FW.regular,
                            color: COLORS.textSecondary,
                            marginTop: 5,
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

                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "flex-end",
                        gap: 7,
                        minWidth: 0,
                      }}
                    >
                      {category && <CategoryBadge category={category} maxWidth={144} />}
                      <div
                        style={{
                          display: "flex",
                          gap: 7,
                          color: COLORS.textTertiary,
                          fontFamily: FONTS.mono,
                          fontSize: 12,
                          fontWeight: FW.medium,
                          whiteSpace: "nowrap",
                        }}
                      >
                        <span style={{ color: COLORS.text }}>{entry.score || 0}</span>
                        <span>分</span>
                        <span>{entry.comment_count || 0}评</span>
                      </div>
                      {keywordsForEntry.length > 0 && <KeywordTags keywords={keywordsForEntry} />}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <div
        style={{
          ...S,
          left: 0,
          bottom: 0,
          width: "100%",
          height: 3,
          background: "linear-gradient(90deg, #ff6600, #FF9F0A)",
          opacity: 0.8 * brandProgress,
        }}
      />
    </div>
  );
};

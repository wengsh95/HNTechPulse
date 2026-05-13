import React from "react";
import { interpolate, Easing, staticFile, useCurrentFrame } from "remotion";

import { COLORS, FONTS, FW, getCardMaxHeight, glassCard, glassCardShadow, innerPanel, isCompactHeight, LAYOUT, S, sectionLabel } from "./design";
import { cleanText, ElementProps, limitList, p, UI_TEXT } from "./utils";

interface KeyPoint {
  label: string;
  text: string;
}

function lineClamp(lines: number): React.CSSProperties {
  return {
    overflow: "hidden",
    display: "-webkit-box",
    WebkitLineClamp: lines,
    WebkitBoxOrient: "vertical" as const,
  };
}

function cleanKeyPoints(value: unknown): KeyPoint[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const point = item as Record<string, unknown>;
      const label = cleanText(String(point.label ?? ""));
      const text = cleanText(String(point.text ?? ""));
      if (!label || !text) {
        return null;
      }
      return { label, text };
    })
    .filter((item): item is KeyPoint => item !== null)
    .slice(0, 2);
}

const InfoPoint: React.FC<{
  point: KeyPoint;
  delay: number;
  frame: number;
}> = ({ point, delay, frame }) => {
  const progress = interpolate(frame, [delay, delay + 18], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "54px minmax(0, 1fr)",
        gap: 12,
        alignItems: "center",
        minHeight: 48,
        padding: "8px 12px",
        ...innerPanel,
        boxSizing: "border-box",
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [8, 0])}px)`,
      }}
    >
      <div
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 44,
          height: 24,
          borderRadius: LAYOUT.chipRadius,
          backgroundColor: COLORS.accentBg,
          border: "1px solid rgba(0,122,255,0.25)",
          boxSizing: "border-box",
          fontFamily: FONTS.sans,
          fontSize: 12,
          fontWeight: FW.bold,
          color: COLORS.textSecondary,
          lineHeight: 1,
          whiteSpace: "nowrap",
        }}
      >
        {point.label}
      </div>
      <div
        style={{
          fontFamily: FONTS.sans,
          fontSize: 15,
          fontWeight: FW.medium,
          color: COLORS.text,
          lineHeight: 1.5,
          letterSpacing: 0,
          overflowWrap: "anywhere",
          wordBreak: "break-word",
          ...lineClamp(2),
        }}
      >
        {point.text}
      </div>
    </div>
  );
};

const KeywordTag: React.FC<{
  keyword: string;
  delay: number;
  frame: number;
}> = ({ keyword, delay, frame }) => {
  const tagProgress = interpolate(frame, [delay, delay + 16], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <span
      style={{
        fontFamily: FONTS.sans,
        fontSize: 12,
        fontWeight: FW.bold,
        color: COLORS.accent,
        backgroundColor: COLORS.accentBg,
        border: "1px solid rgba(0,122,255,0.25)",
        borderRadius: 6,
        padding: "5px 11px",
        letterSpacing: 0,
        opacity: tagProgress,
        transform: `scale(${interpolate(tagProgress, [0, 1], [0.8, 1])})`,
      }}
    >
      {keyword}
    </span>
  );
};

const MetricPill: React.FC<{
  label: string;
  value: number;
  accent?: boolean;
}> = ({ label, value, accent = false }) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      height: 28,
      padding: "0 10px",
      borderRadius: LAYOUT.chipRadius,
      backgroundColor: accent ? COLORS.accentBg : "rgba(255,255,255,0.045)",
      border: accent ? "1px solid rgba(0,122,255,0.22)" : "1px solid rgba(255,255,255,0.08)",
      boxSizing: "border-box",
      fontFamily: FONTS.sans,
      whiteSpace: "nowrap",
    }}
  >
    <span
      style={{
        fontSize: 12,
        fontWeight: FW.bold,
        color: accent ? COLORS.accent : COLORS.textTertiary,
        lineHeight: 1,
      }}
    >
      {label}
    </span>
    <span
      style={{
        fontFamily: FONTS.mono,
        fontSize: 14,
        fontWeight: FW.heavy,
        color: COLORS.text,
        lineHeight: 1,
      }}
    >
      {Math.max(0, Math.round(value)).toLocaleString("en-US")}
    </span>
  </div>
);

export const EventCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();

  const storyTitle = cleanText(p(elementProps, "story_title", ""));
  const sourceTitle = cleanText(p(elementProps, "source_title", storyTitle));
  const titleCn = cleanText(p(elementProps, "title_cn", ""));
  const editorAngle = cleanText(p(elementProps, "editor_angle", ""));
  const eventSummary = cleanText(p(elementProps, "event_summary", ""));
  const dek = cleanText(p(elementProps, "dek", "")) || eventSummary;
  const keyPoints = cleanKeyPoints(elementProps.key_points);
  const imageSrc = p(elementProps, "image_src", "");
  const imageType = p<string>(elementProps, "image_type", "");
  const keywords = limitList(
    Array.isArray(elementProps.keywords) ? elementProps.keywords.filter((k): k is string => typeof k === "string") : [],
    3, 16
  );
  const category = cleanText(p(elementProps, "category", ""));
  const mainTitle = editorAngle || titleCn || storyTitle;
  const showOriginalTitle = Boolean(sourceTitle && mainTitle !== sourceTitle);
  const hasStructuredBody = keyPoints.length > 0;
  const displayIndex = Number(p(elementProps, "display_index", 0));
  const storyCount = Number(p(elementProps, "story_count", 0));
  const showChapterWatermark = displayIndex > 0 && storyCount > 0;
  const heatScore = Number(p(elementProps, "score", 0)) || 0;
  const commentCount = Number(p(elementProps, "comment_count", 0)) || 0;
  const showMetrics = heatScore > 0 || commentCount > 0;

  const hasImage = imageSrc !== "";
  const isLogo = imageType === "logo";
  const compact = isCompactHeight(height);
  const cardW = width - LAYOUT.pageInset * 2;
  const cardMaxH = getCardMaxHeight(height);
  const topY = LAYOUT.topInset;

  const dividerStyle: React.CSSProperties = {
    width: "100%",
    height: 1,
    background: "rgba(255,255,255,0.08)",
    marginBottom: 18,
  };

  const cardProgress = interpolate(frame, [4, 22], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const mediaW = hasImage ? (isLogo ? 320 : Math.min(500, Math.round(cardW * 0.42))) : 0;
  const mediaH = isLogo ? 280 : Math.round(mediaW * 9 / 16);
  const gap = hasImage ? (compact ? 24 : 36) : 0;
  const horizontalPadding = hasImage ? (compact ? 56 : 68) : (compact ? 64 : 72);
  const textColW = hasImage
    ? cardW - mediaW - gap - horizontalPadding
    : Math.min(cardW - horizontalPadding, LAYOUT.contentWideMaxWidth);
  const titleLines = hasImage || compact ? 2 : 3;
  const dekLines = compact ? 2 : (hasStructuredBody ? 3 : 4);

  return (
    <div
      style={{
        ...S,
        left: LAYOUT.pageInset,
        top: topY,
        width: cardW,
        maxHeight: cardMaxH,
        ...glassCard,
        padding: hasImage
          ? compact ? "20px 28px" : "26px 34px"
          : compact ? "24px 32px" : "28px 36px",
        boxShadow: glassCardShadow,
        boxSizing: "border-box",
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [28, 0])}px)`,
        display: "flex",
        gap,
        alignItems: "flex-start",
        overflow: "hidden",
      }}
    >
      {/* Chapter watermark */}
      {showChapterWatermark && (
        <div
          style={{
            position: "absolute",
            right: 36,
            top: 28,
            fontFamily: FONTS.mono,
            fontSize: 72,
            fontWeight: FW.heavy,
            color: "rgba(255,255,255,0.06)",
            lineHeight: 1,
            pointerEvents: "none",
            letterSpacing: -4,
          }}
        >
          {String(displayIndex).padStart(2, "0")}/{String(storyCount).padStart(2, "0")}
        </div>
      )}

      <div style={{ flex: hasImage ? `0 0 ${textColW}px` : 1, maxWidth: textColW, minWidth: 0 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 8,
            marginBottom: compact ? 12 : 16,
            maxWidth: textColW,
          }}
        >
          <div style={{ ...sectionLabel, marginBottom: 0 }}>{UI_TEXT.eventDetail}</div>
          {category && (
            <div
              style={{
                fontFamily: FONTS.sans,
                fontSize: 12,
                fontWeight: FW.bold,
                color: COLORS.accent,
                backgroundColor: COLORS.accentBg,
                border: "1px solid rgba(0,122,255,0.25)",
                borderRadius: 6,
                padding: "5px 10px",
              }}
            >
              {category}
            </div>
          )}
          {showMetrics && (
            <>
              <MetricPill label={UI_TEXT.heat} value={heatScore} accent />
              <MetricPill label={UI_TEXT.comments} value={commentCount} />
            </>
          )}
        </div>

        <div
          style={{
            fontFamily: FONTS.bold,
            fontWeight: FW.heavy,
            fontSize: compact ? 28 : 30,
            color: COLORS.text,
            lineHeight: 1.18,
            letterSpacing: 0,
            marginBottom: compact ? 10 : 14,
            overflowWrap: "anywhere",
            wordBreak: "break-word",
            maxWidth: textColW,
            ...lineClamp(titleLines),
          }}
        >
          {mainTitle}
        </div>

        {showOriginalTitle && (
          <div
            style={{
              fontFamily: FONTS.sans,
              fontWeight: FW.medium,
              fontSize: 16,
              color: COLORS.textTertiary,
              marginBottom: compact ? 12 : 16,
              lineHeight: 1.4,
              maxWidth: textColW,
              overflowWrap: "anywhere",
              wordBreak: "break-word",
              ...lineClamp(1),
            }}
          >
            HN 原题&nbsp;&nbsp;{sourceTitle}
          </div>
        )}

        {(dek || keyPoints.length > 0) && (
          <div style={{ ...dividerStyle, marginBottom: compact ? 14 : dividerStyle.marginBottom }} />
        )}

        {dek && (
          <div
            style={{
              fontFamily: FONTS.sans,
              fontSize: compact ? 17 : 18,
              color: COLORS.textSecondary,
              lineHeight: compact ? 1.48 : 1.55,
              fontWeight: FW.regular,
              marginBottom: hasStructuredBody ? (compact ? 14 : 18) : (compact ? 16 : 20),
              maxWidth: textColW,
              overflowWrap: "anywhere",
              wordBreak: "break-word",
              ...lineClamp(dekLines),
            }}
          >
            {dek}
          </div>
        )}

        {keyPoints.length > 0 && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr",
              gap: compact ? 8 : 10,
              marginBottom: keywords.length > 0 ? (compact ? 12 : 16) : 0,
              maxWidth: textColW,
            }}
          >
            {keyPoints.map((point, i) => (
              <InfoPoint key={`${point.label}-${i}`} point={point} delay={10 + i * 5} frame={frame} />
            ))}
          </div>
        )}

        {keywords.length > 0 && (
          <>
            <div style={{ ...dividerStyle, marginTop: compact ? 0 : 4, marginBottom: compact ? 12 : dividerStyle.marginBottom }} />
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
                marginBottom: 0,
                maxWidth: textColW,
              }}
            >
              {keywords.map((kw, i) => (
                <KeywordTag key={kw} keyword={kw} delay={8 + i * 4} frame={frame} />
              ))}
            </div>
          </>
        )}
      </div>

      {hasImage && (
        <div
          style={{
            flex: `0 0 ${mediaW}px`,
            height: mediaH,
            aspectRatio: isLogo ? undefined : "16 / 9",
            marginTop: isLogo ? (compact ? 26 : 34) : (compact ? 34 : 42),
            borderRadius: LAYOUT.cardRadius,
            overflow: "hidden",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(255,255,255,0.04)",
            border: "none",
            opacity: interpolate(cardProgress, [0, 0.3], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
            transform: `translateX(${interpolate(cardProgress, [0, 1], [20, 0])}px)`,
          }}
        >
          {isLogo ? (
            <div
              style={{
                width: "100%",
                height: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "rgba(255,255,255,0.04)",
                borderRadius: 10,
              }}
            >
              <img
                src={staticFile(imageSrc)}
                alt=""
                style={{
                  maxWidth: "78%",
                  maxHeight: "78%",
                  objectFit: "contain",
                }}
              />
            </div>
          ) : (
            <img
              src={staticFile(imageSrc)}
              alt=""
              style={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
              }}
            />
          )}
        </div>
      )}
    </div>
  );
};

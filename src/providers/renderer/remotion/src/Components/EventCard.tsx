import React from "react";
import { interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

import { COLORS, FONTS, FW, glassCard, glassCardShadow, LAYOUT, S, sectionLabel } from "./design";
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
  fps: number;
}> = ({ point, delay, frame, fps }) => {
  const progress = spring({
    frame,
    fps,
    config: { damping: 11, stiffness: 140 },
    delay,
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
        borderRadius: 14,
        backgroundColor: "rgba(255,255,255,0.03)",
        border: "1px solid rgba(255,255,255,0.045)",
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
          borderRadius: 12,
          backgroundColor: "rgba(255,255,255,0.06)",
          border: "1px solid rgba(255,255,255,0.08)",
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
          color: "rgba(255,255,255,0.78)",
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

export const EventCard: React.FC<ElementProps> = ({ elementProps, width }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const storyTitle = cleanText(p(elementProps, "story_title", ""));
  const sourceTitle = cleanText(p(elementProps, "source_title", storyTitle));
  const titleCn = cleanText(p(elementProps, "title_cn", ""));
  const editorAngle = cleanText(p(elementProps, "editor_angle", ""));
  const eventSummary = cleanText(p(elementProps, "event_summary", ""));
  const dek = cleanText(p(elementProps, "dek", "")) || eventSummary;
  const keyPoints = cleanKeyPoints(elementProps.key_points);
  const imageSrc = p(elementProps, "image_src", "");
  const imageType = p<string>(elementProps, "image_type", "");
  const keywords = limitList((elementProps.keywords as string[]) ?? [], 3, 16);
  const category = cleanText(p(elementProps, "category", ""));
  const mainTitle = editorAngle || titleCn || storyTitle;
  const showOriginalTitle = Boolean(sourceTitle && mainTitle !== sourceTitle);
  const hasStructuredBody = keyPoints.length > 0;
  const displayIndex = Number(p(elementProps, "display_index", 0));
  const storyCount = Number(p(elementProps, "story_count", 0));
  const showChapterWatermark = displayIndex > 0 && storyCount > 0;

  const hasImage = imageSrc !== "";
  const isLogo = imageType === "logo";
  const cardW = width - LAYOUT.pageInset * 2;
  const topY = LAYOUT.topInset;

  const dividerStyle: React.CSSProperties = {
    width: "100%",
    height: 1,
    background: "rgba(255,255,255,0.05)",
    marginBottom: 18,
  };

  const cardProgress = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 120 },
    delay: 4,
  });

  const mediaW = hasImage ? (isLogo ? 330 : Math.round(cardW * 0.35)) : 0;
  const mediaH = isLogo ? 280 : Math.round(mediaW * 9 / 16);
  const gap = hasImage ? 40 : 0;
  const horizontalPadding = hasImage ? 72 : 88;
  const textColW = hasImage
    ? cardW - mediaW - gap - horizontalPadding
    : Math.min(cardW - horizontalPadding, LAYOUT.contentMaxWidth);

  return (
    <div
      style={{
        ...S,
        left: LAYOUT.pageInset,
        top: topY,
        width: cardW,
        ...glassCard,
        padding: hasImage ? "36px 44px" : "40px 48px",
        boxShadow: "0 0 0 0.5px rgba(255,255,255,0.05), 0 0 24px rgba(0,122,255,0.06), 0 8px 28px rgba(0,0,0,0.22)",
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
            color: "rgba(255,255,255,0.025)",
            lineHeight: 1,
            pointerEvents: "none",
            letterSpacing: -4,
          }}
        >
          {String(displayIndex).padStart(2, "0")}/{String(storyCount).padStart(2, "0")}
        </div>
      )}

      <div style={{ flex: hasImage ? `0 0 ${textColW}px` : 1, maxWidth: textColW, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
          <div style={{ ...sectionLabel, marginBottom: 0 }}>{UI_TEXT.eventDetail}</div>
          {category && (
            <div
              style={{
                fontFamily: FONTS.sans,
                fontSize: 12,
                fontWeight: FW.bold,
                color: "rgba(255,255,255,0.68)",
                backgroundColor: "rgba(255,255,255,0.052)",
                border: "1px solid rgba(255,255,255,0.07)",
                borderRadius: 999,
                padding: "5px 10px",
              }}
            >
              {category}
            </div>
          )}
        </div>

        <div
          style={{
            fontFamily: FONTS.bold,
            fontWeight: FW.heavy,
            fontSize: 30,
            color: COLORS.text,
            lineHeight: 1.18,
            letterSpacing: 0,
            marginBottom: 14,
            overflowWrap: "anywhere",
            wordBreak: "break-word",
            maxWidth: textColW,
            ...lineClamp(2),
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
              marginBottom: 16,
              lineHeight: 1.4,
              maxWidth: LAYOUT.contentMaxWidth,
              overflowWrap: "anywhere",
              wordBreak: "break-word",
              ...lineClamp(1),
            }}
          >
            HN 原题&nbsp;&nbsp;{sourceTitle}
          </div>
        )}

        {(dek || keyPoints.length > 0) && (
          <div style={dividerStyle} />
        )}

        {dek && (
          <div
            style={{
              fontFamily: FONTS.sans,
              fontSize: 18,
              color: "rgba(255,255,255,0.78)",
              lineHeight: 1.55,
              fontWeight: FW.regular,
              marginBottom: hasStructuredBody ? 18 : 20,
              maxWidth: LAYOUT.contentMaxWidth,
              overflowWrap: "anywhere",
              wordBreak: "break-word",
              ...lineClamp(hasStructuredBody ? 2 : 4),
            }}
          >
            {dek}
          </div>
        )}

        {keyPoints.length > 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 10,
              marginBottom: keywords.length > 0 ? 16 : 0,
              maxWidth: LAYOUT.contentMaxWidth,
            }}
          >
            {keyPoints.map((point, i) => (
              <InfoPoint key={`${point.label}-${i}`} point={point} delay={10 + i * 5} frame={frame} fps={fps} />
            ))}
          </div>
        )}

        {keywords.length > 0 && (
          <>
            <div style={{ ...dividerStyle, marginTop: 4 }} />
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
                marginBottom: 0,
                maxWidth: LAYOUT.contentMaxWidth,
              }}
            >
              {keywords.map((kw, i) => {
                const tagProgress = spring({
                  frame,
                  fps,
                  config: { damping: 10, stiffness: 140 },
                  delay: 8 + i * 4,
                });

                return (
                  <span
                    key={kw}
                    style={{
                      fontFamily: FONTS.sans,
                      fontSize: 12,
                      fontWeight: FW.bold,
                      color: "rgba(91, 173, 255, 0.88)",
                      backgroundColor: "rgba(0, 122, 255, 0.11)",
                      border: "1px solid rgba(51, 149, 255, 0.25)",
                      borderRadius: 999,
                      padding: "5px 11px",
                      letterSpacing: 0,
                      opacity: tagProgress,
                      transform: `scale(${interpolate(tagProgress, [0, 1], [0.8, 1])})`,
                    }}
                  >
                    {kw}
                  </span>
                );
              })}
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
            marginTop: isLogo ? 44 : 54,
            borderRadius: Math.max(14, LAYOUT.cardRadius - 2),
            overflow: "hidden",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.06)",
            boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.03)",
            opacity: interpolate(cardProgress, [0, 0.3], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
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
                borderRadius: 18,
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

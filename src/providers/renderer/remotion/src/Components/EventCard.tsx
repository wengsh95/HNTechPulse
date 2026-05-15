import React from "react";
import { interpolate, Easing, staticFile, useCurrentFrame } from "remotion";

import {
  COLORS,
  FONTS,
  FW,
  FS,
  getCardMaxHeight,
  glassCard,
  glassCardShadow,
  glassGlow,
  isCompactHeight,
  LAYOUT,
  S,
} from "./design";
import {
  breathingOpacity,
  CapsuleBadge,
  dividerStyle,
  GlassShimmer,
  highlightKeywords,
  KeywordTag,
  lineClamp,
  MetricPill,
  overshootTranslateY,
  SectionLabel,
} from "./HighlightShared";
import { cleanText, ElementProps, limitList, p } from "./utils";

interface KeyPoint {
  label: string;
  text: string;
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
        display: "flex",
        alignItems: "baseline",
        gap: 8,
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [8, 0])}px)`,
      }}
    >
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: FS.label,
          fontWeight: FW.bold,
          color: COLORS.textSecondary,
          whiteSpace: "nowrap",
          lineHeight: 1.7,
        }}
      >
        {point.label}
      </span>
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: FS.bodySmall,
          fontWeight: FW.medium,
          color: COLORS.textBody,
          lineHeight: 1.7,
          overflowWrap: "anywhere",
          wordBreak: "break-word",
          ...lineClamp(2),
        }}
      >
        {point.text}
      </span>
    </div>
  );
};

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
    Array.isArray(elementProps.keywords)
      ? elementProps.keywords.filter((k): k is string => typeof k === "string")
      : [],
    4,
    16,
  );
  const category = cleanText(p(elementProps, "category", ""));
  const mainTitle = editorAngle || titleCn || storyTitle;
  const showOriginalTitle = Boolean(sourceTitle && mainTitle !== sourceTitle);
  const hasBody = Boolean(dek || keyPoints.length > 0);
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

  const padX = compact ? 36 : 44;
  const padY = compact ? 32 : 40;
  const mediaW = hasImage ? (isLogo ? 220 : Math.round(cardW * 0.4)) : 0;
  const mediaH = isLogo
    ? Math.min(240, cardMaxH - padY * 2)
    : Math.min(Math.round((mediaW * 10) / 16), cardMaxH - padY * 2);
  const gap = hasImage ? (compact ? 32 : 40) : 0;
  const textColW = hasImage
    ? Math.max(320, cardW - mediaW - gap - padX * 2)
    : Math.min(cardW - padX * 2, LAYOUT.contentWideMaxWidth);

  const cardProgress = interpolate(frame, [4, 22], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const titleProgress = interpolate(frame, [8, 26], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const bodyProgress = interpolate(frame, [14, 32], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const imageProgress = interpolate(frame, [6, 26], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const footerProgress = interpolate(frame, [20, 36], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const titleFontSize = compact ? 34 : FS.headline;

  return (
    <div
      style={{
        ...S,
        left: LAYOUT.pageInset,
        top: LAYOUT.topInset,
        width: cardW,
        minHeight: cardMaxH,
        ...glassCard,
        padding: `${padY}px ${padX}px`,
        boxShadow: glassCardShadow,
        boxSizing: "border-box",
        opacity: cardProgress,
        transform: `translateY(${overshootTranslateY(cardProgress, 28)}px)`,
        display: "flex",
        gap,
        alignItems: "stretch",
        overflow: "hidden",
      }}
    >
      <GlassShimmer frame={frame} />
      {showChapterWatermark && (
        <div
          style={{
            position: "absolute",
            right: padX,
            top: padY - 4,
            fontFamily: FONTS.mono,
            fontSize: FS.watermark,
            fontWeight: FW.heavy,
            color: `rgba(255,255,255,${breathingOpacity(frame)})`,
            lineHeight: 1,
            pointerEvents: "none",
            letterSpacing: -4,
            zIndex: 0,
          }}
        >
          {String(displayIndex).padStart(2, "0")}/{String(storyCount).padStart(2, "0")}
        </div>
      )}

      <div
        style={{
          flex: hasImage ? `0 0 ${textColW}px` : 1,
          maxWidth: textColW,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          position: "relative",
          zIndex: 1,
        }}
      >
        {/* Header row: HN badge + category + reading time + date */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            flexWrap: "wrap",
            gap: 8,
            marginBottom: compact ? 16 : 20,
            maxWidth: textColW,
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [6, 0])}px)`,
          }}
        >
          <CapsuleBadge text="事件详情" />
        </div>

        {/* Main title — large, bold, the visual anchor */}
        <div
          style={{
            fontFamily: FONTS.bold,
            fontWeight: FW.heavy,
            fontSize: titleFontSize,
            color: COLORS.text,
            lineHeight: 1.15,
            letterSpacing: -0.4,
            marginBottom: showOriginalTitle ? (compact ? 6 : 8) : compact ? 14 : 18,
            overflowWrap: "anywhere",
            wordBreak: "break-word",
            maxWidth: textColW,
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [10, 0])}px)`,
            ...lineClamp(2),
          }}
        >
          {mainTitle}
        </div>

        {/* English subtitle — subordinate to main title */}
        {showOriginalTitle && (
          <div
            style={{
              fontFamily: FONTS.sans,
              fontWeight: FW.regular,
              fontSize: FS.subtitle2,
              color: COLORS.textTertiary,
              marginBottom: compact ? 14 : 18,
              lineHeight: 1.4,
              maxWidth: textColW,
              overflowWrap: "anywhere",
              wordBreak: "break-word",
              opacity: titleProgress,
              transform: `translateY(${interpolate(titleProgress, [0, 1], [6, 0])}px)`,
              ...lineClamp(1),
            }}
          >
            {sourceTitle}
          </div>
        )}

        {/* Metrics row */}
        {showMetrics && (
          <div
            style={{
              display: "flex",
              gap: 8,
              marginBottom: hasBody ? (compact ? 18 : 22) : 0,
            }}
          >
            {heatScore > 0 && <MetricPill icon="🔥" value={heatScore} delay={12} frame={frame} />}
            {commentCount > 0 && (
              <MetricPill icon="💬" value={commentCount} delay={14} frame={frame} />
            )}
          </div>
        )}

        {/* Body: summary + key points */}
        {hasBody && (
          <div
            style={{
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [10, 0])}px)`,
            }}
          >
            {dek && (
              <>
                <SectionLabel text="摘要" delay={14} frame={frame} />
                <div
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: compact ? FS.bodySmall : FS.body,
                    color: COLORS.textBody,
                    lineHeight: 1.7,
                    fontWeight: FW.regular,
                    marginBottom:
                      keyPoints.length > 0
                        ? compact
                          ? 16
                          : 20
                        : keywords.length > 0
                          ? compact
                            ? 14
                            : 16
                          : 0,
                    maxWidth: textColW,
                    overflowWrap: "anywhere",
                    wordBreak: "break-word",
                    ...lineClamp(3),
                  }}
                >
                  {highlightKeywords(dek, keywords, frame, 14)}
                </div>
              </>
            )}

            {keyPoints.length > 0 && (
              <>
                <SectionLabel text="要点" delay={16} frame={frame} />
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr",
                    gap: compact ? 8 : 12,
                    marginBottom: keywords.length > 0 ? (compact ? 16 : 20) : 0,
                    maxWidth: textColW,
                  }}
                >
                  {keyPoints.map((point, i) => (
                    <InfoPoint
                      key={`${point.label}-${i}`}
                      point={point}
                      delay={18 + i * 5}
                      frame={frame}
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {/* Keywords row */}
        {keywords.length > 0 && (
          <>
            <div style={dividerStyle} />
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                justifyContent: "flex-start",
                gap: 8,
                marginBottom: 0,
                maxWidth: textColW,
                opacity: footerProgress,
              }}
            >
              {keywords.map((kw, i) => (
                <KeywordTag key={kw} keyword={kw} delay={20 + i * 4} frame={frame} />
              ))}
            </div>
          </>
        )}

        {/* Spacer when no body, no metrics, no keywords */}
        {!hasBody && !showMetrics && keywords.length === 0 && <div style={{ flex: 1 }} />}
      </div>

      {/* Right: image panel — no browser chrome, glass glow, 3D tilt */}
      {hasImage && (
        <div
          style={{
            flex: `0 0 ${mediaW}px`,
            alignSelf: "center",
            opacity: imageProgress,
            transform: `perspective(1000px) rotateY(${interpolate(imageProgress, [0, 1], [3, -1.5])}deg) translateX(${interpolate(imageProgress, [0, 1], [24, 0])}px)`,
          }}
        >
          <div
            style={{
              borderRadius: 12,
              overflow: "hidden",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: COLORS.surfaceSubtle,
              border: "1px solid " + COLORS.borderLow,
              boxShadow: glassGlow,
              width: mediaW,
              height: mediaH,
            }}
          >
            {isLogo ? (
              <img
                src={staticFile(imageSrc)}
                alt=""
                style={{
                  maxWidth: "75%",
                  maxHeight: "75%",
                  objectFit: "contain",
                }}
              />
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
        </div>
      )}
    </div>
  );
};

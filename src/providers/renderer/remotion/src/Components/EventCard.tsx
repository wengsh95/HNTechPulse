import React from "react";
import { interpolate, Easing, staticFile, useCurrentFrame } from "remotion";

import {
  COLORS,
  FONTS,
  FW,
  getCardMaxHeight,
  glassCard,
  glassCardShadow,
  glassGlow,
  isCompactHeight,
  LAYOUT,
  S,
} from "./design";
import { cleanText, ElementProps, limitList, p } from "./utils";

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

function estimateReadingTime(dek: string, keyPoints: KeyPoint[]): number {
  let chars = dek.length;
  for (const kp of keyPoints) {
    chars += kp.label.length + kp.text.length;
  }
  return Math.max(1, Math.round(chars / 400));
}

function formatDate(ts: number): string {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}/${m}/${day}`;
}

function highlightKeywords(text: string, keywords: string[]): React.ReactNode {
  if (!text || keywords.length === 0) return text;
  const escaped = keywords
    .filter((k) => k.length > 1)
    .map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .sort((a, b) => b.length - a.length);
  if (escaped.length === 0) return text;
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(pattern);
  if (parts.length <= 1) return text;
  return parts.map((part, i) => {
    const isMatch = keywords.some((k) => k.toLowerCase() === part.toLowerCase());
    if (isMatch) {
      return (
        <span key={i} style={{ color: COLORS.accentLight, fontWeight: FW.semibold }}>
          {part}
        </span>
      );
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}

const SectionLabel: React.FC<{ text: string; delay: number; frame: number }> = ({
  text,
  delay,
  frame,
}) => {
  const progress = interpolate(frame, [delay, delay + 14], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        marginBottom: 8,
        opacity: progress,
        transform: `translateX(${interpolate(progress, [0, 1], [-6, 0])}px)`,
      }}
    >
      <div
        style={{
          width: 3,
          height: 12,
          borderRadius: 2,
          background: COLORS.accent,
          flexShrink: 0,
        }}
      />
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: 12,
          fontWeight: FW.semibold,
          color: COLORS.textTertiary,
          letterSpacing: 0.6,
        }}
      >
        {text}
      </span>
    </div>
  );
};

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
          fontSize: 13,
          fontWeight: FW.bold,
          color: COLORS.textTertiary,
          whiteSpace: "nowrap",
          lineHeight: 1.7,
        }}
      >
        {point.label}
      </span>
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: 15,
          fontWeight: FW.medium,
          color: COLORS.textSecondary,
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
        fontWeight: FW.semibold,
        color: COLORS.accentLight,
        backgroundColor: "rgba(0,122,255,0.10)",
        border: "1px solid rgba(0,122,255,0.18)",
        borderRadius: 999,
        padding: "5px 14px",
        letterSpacing: 0.2,
        opacity: tagProgress,
        transform: `scale(${interpolate(tagProgress, [0, 1], [0.85, 1])})`,
      }}
    >
      {keyword}
    </span>
  );
};

const MetricPill: React.FC<{
  icon: string;
  value: number;
  delay: number;
  frame: number;
}> = ({ icon, value, delay, frame }) => {
  const progress = interpolate(frame, [delay, delay + 14], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        height: 28,
        padding: "0 12px",
        borderRadius: 14,
        backgroundColor: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.07)",
        boxSizing: "border-box",
        fontFamily: FONTS.mono,
        whiteSpace: "nowrap",
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [4, 0])}px)`,
      }}
    >
      <span style={{ fontSize: 13, lineHeight: 1 }}>{icon}</span>
      <span
        style={{
          fontSize: 13,
          fontWeight: FW.heavy,
          color: COLORS.textSecondary,
          lineHeight: 1,
        }}
      >
        {Math.max(0, Math.round(value)).toLocaleString("en-US")}
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
  const articleUrl = cleanText(p(elementProps, "url", ""));
  const publishedAt = Number(p(elementProps, "published_at", 0)) || 0;
  const dateDisplay = formatDate(publishedAt);
  const readingTime = estimateReadingTime(dek, keyPoints);

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

  const dividerStyle: React.CSSProperties = {
    width: "100%",
    height: 1,
    background:
      "linear-gradient(90deg, rgba(255,255,255,0.10) 0%, rgba(255,255,255,0.02) 100%)",
    marginTop: 12,
    marginBottom: 14,
  };

  const titleFontSize = compact ? 34 : 38;

  return (
    <div
      style={{
        ...S,
        left: LAYOUT.pageInset,
        top: LAYOUT.topInset,
        width: cardW,
        height: cardMaxH,
        ...glassCard,
        padding: `${padY}px ${padX}px`,
        boxShadow: glassCardShadow,
        boxSizing: "border-box",
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [28, 0])}px)`,
        display: "flex",
        gap,
        alignItems: "stretch",
        overflow: "hidden",
      }}
    >
      {showChapterWatermark && (
        <div
          style={{
            position: "absolute",
            right: padX,
            top: padY - 4,
            fontFamily: FONTS.mono,
            fontSize: 64,
            fontWeight: FW.heavy,
            color: "rgba(255,255,255,0.04)",
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
          <span
            style={{
              fontFamily: FONTS.sans,
              fontSize: 12,
              fontWeight: FW.heavy,
              color: COLORS.brand,
              backgroundColor: COLORS.brandBg,
              border: "1px solid rgba(255,102,0,0.25)",
              borderRadius: 999,
              padding: "3px 10px",
              letterSpacing: 0.3,
            }}
          >
            HN
          </span>
          {category && (
            <span
              style={{
                fontFamily: FONTS.sans,
                fontSize: 11,
                fontWeight: FW.bold,
                color: "#ffffff",
                background: `linear-gradient(135deg, ${COLORS.accent} 0%, ${COLORS.accentLight} 100%)`,
                borderRadius: 999,
                padding: "3px 12px",
                letterSpacing: 0.3,
              }}
            >
              {category}
            </span>
          )}
          {readingTime > 0 && (
            <span
              style={{
                fontFamily: FONTS.sans,
                fontSize: 12,
                fontWeight: FW.medium,
                color: COLORS.textTertiary,
                marginLeft: 4,
              }}
            >
              阅读约 {readingTime} 分钟
            </span>
          )}
          {dateDisplay && (
            <span
              style={{
                fontFamily: FONTS.mono,
                fontSize: 11,
                fontWeight: FW.medium,
                color: COLORS.textTertiary,
                marginLeft: 2,
              }}
            >
              {dateDisplay}
            </span>
          )}
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
              fontSize: 14,
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
            {heatScore > 0 && (
              <MetricPill icon="🔥" value={heatScore} delay={12} frame={frame} />
            )}
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
                    fontSize: compact ? 15 : 16,
                    color: "rgba(245,245,247,0.70)",
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
                  {highlightKeywords(dek, keywords)}
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
                justifyContent: "center",
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

        {/* "阅读原文" link */}
        {articleUrl && (
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              marginTop: keywords.length > 0 ? 14 : (hasBody ? 18 : 0),
              opacity: footerProgress,
              transform: `translateX(${interpolate(footerProgress, [0, 1], [8, 0])}px)`,
            }}
          >
            <span
              style={{
                fontFamily: FONTS.sans,
                fontSize: 13,
                fontWeight: FW.semibold,
                color: COLORS.accentLight,
                letterSpacing: 0.3,
              }}
            >
              查看原文 →
            </span>
          </div>
        )}

        {/* Spacer when no body, no metrics, no keywords */}
        {!hasBody && !showMetrics && keywords.length === 0 && (
          <div style={{ flex: 1 }} />
        )}
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
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.08)",
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

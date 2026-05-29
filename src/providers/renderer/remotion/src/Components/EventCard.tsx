import React, { useMemo } from "react";
import { interpolate, Easing, staticFile, useCurrentFrame } from "remotion";

import {
  COLORS,
  FONTS,
  FW,
  useDesign,
  useChapterTone,
  glassCard,
  glassCardShadow,
  glassGlow,
  S,
} from "./design";
import {
  dividerStyle,
  GlassShimmer,
  highlightKeywords,
  lineClamp,
  MetricPill,
  overshootTranslateY,
  useCardPad,
  useCardAnimations,
  headerMargin,
  titleBodyGap,
  bodySectionGap,
  titleFontSize,
  focusTitleFontSize,
  ChapterWatermark,
  CardKeywordsFooter,
  CARD_ENTRANCE_Y,
  TITLE_ENTRANCE_Y,
  BODY_ENTRANCE_Y,
  HEADER_ENTRANCE_Y,
  IMAGE_ENTRANCE_X,
  ITEM_DURATION,
  IMAGE_PANEL_RADIUS,
  IMAGE_PANEL_SHADOW,
  IMAGE_PANEL_BORDER,
  IMAGE_PANEL_BG,
} from "./HighlightShared";
import { cleanText, ElementProps, limitList, p, UI_TEXT } from "./utils";

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

function findKeyPointText(points: KeyPoint[], labels: string[]): string {
  const labelSet = new Set(labels);
  return points.find((point) => labelSet.has(point.label))?.text ?? "";
}

const INFO_POINT_COLORS = [COLORS.brand, COLORS.accent, COLORS.green];

const InfoPoint: React.FC<{
  point: KeyPoint;
  delay: number;
  frame: number;
  index: number;
}> = ({ point, delay, frame, index }) => {
  const progress = interpolate(frame, [delay, delay + ITEM_DURATION], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const { fs, scaled } = useDesign();
  const accentColor = INFO_POINT_COLORS[index % INFO_POINT_COLORS.length];

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: scaled(4),
        opacity: progress,
        transform: `translateY(${interpolate(progress, [0, 1], [8, 0])}px)`,
        backgroundColor: COLORS.surfaceSubtle,
        borderRadius: scaled(8),
        padding: `${scaled(10)}px ${scaled(14)}px`,
        borderLeft: `${scaled(3)}px solid ${accentColor}`,
      }}
    >
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: fs.caption,
          fontWeight: FW.bold,
          color: accentColor,
          lineHeight: 1.4,
          letterSpacing: 0.2,
        }}
      >
        {point.label}
      </span>
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: fs.body,
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
  const tone = useChapterTone();

  const storyTitle = cleanText(p(elementProps, "story_title", ""));
  const sourceTitle = cleanText(p(elementProps, "source_title", storyTitle));
  const titleCn = cleanText(p(elementProps, "title_cn", ""));
  const editorAngle = cleanText(p(elementProps, "editor_angle", ""));
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
  const mainTitle = editorAngle || titleCn || storyTitle;
  const showOriginalTitle = Boolean(sourceTitle && mainTitle !== sourceTitle);
  const whyItMatters =
    cleanText(p(elementProps, "why_it_matters", "")) ||
    findKeyPointText(keyPoints, ["为何关注", "为什么关注"]);
  const impactText =
    findKeyPointText(keyPoints, ["影响", "后续影响"]) || cleanText(p(elementProps, "impact", ""));
  const insightPoints: KeyPoint[] = [
    whyItMatters ? { label: UI_TEXT.whyItMatters, text: whyItMatters } : null,
    impactText ? { label: "影响", text: impactText } : null,
  ].filter((point): point is KeyPoint => point !== null);
  const sourceDomain = cleanText(p(elementProps, "source_domain", ""));
  const hasBody = insightPoints.length > 0;
  const displayIndex = Number(p(elementProps, "display_index", 0));
  const storyCount = Number(p(elementProps, "story_count", 0));
  const displayOrdinal = displayIndex + 1;
  const showChapterWatermark = displayIndex >= 0 && storyCount > 0;
  const heatScore = Number(p(elementProps, "score", 0)) || 0;
  const commentCount = Number(p(elementProps, "comment_count", 0)) || 0;
  const heatLevel = cleanText(p(elementProps, "heat_level", ""));
  const showMetrics = heatScore > 0 || commentCount > 0 || heatLevel !== "";

  const hasImage = imageSrc !== "";
  const isLogo = imageType === "logo";
  const d = useDesign();
  const compact = d.isCompactHeight;

  const { padX, padY } = useCardPad(compact);
  const { cardProgress, titleProgress, bodyProgress, imageProgress, footerProgress } =
    useCardAnimations(frame);

  const layout = useMemo(() => {
    const cardW = width - d.layout.pageInset * 2;
    const cardMaxH = d.getCardMaxHeight;
    const mediaW = hasImage ? (isLogo ? d.scaled(220) : Math.round(cardW * 0.48)) : 0;
    const mediaH = isLogo
      ? Math.min(d.scaled(240), cardMaxH - padY * 2)
      : Math.min(Math.round(mediaW * 0.62), cardMaxH - padY * 2);
    const heroImage = hasImage && !isLogo;
    const gap = hasImage ? d.scaled(compact ? 24 : 28) : 0;
    const availableTextW = cardW - mediaW - gap - padX * 2;
    const textColW = hasImage
      ? Math.max(d.scaled(320), Math.min(availableTextW, cardW - padX * 2))
      : Math.min(cardW - padX * 2, d.layout.contentWideMaxWidth);
    const resolvedTitleFontSize = focusTitleFontSize(d);
    return { cardW, cardMaxH, mediaW, mediaH, heroImage, gap, availableTextW, textColW, resolvedTitleFontSize };
  }, [width, d, compact, padX, padY, hasImage, isLogo]);
  const { cardW, cardMaxH, mediaW, mediaH, heroImage, gap, textColW, resolvedTitleFontSize } = layout;

  return (
    <div
      style={{
        ...S,
        left: d.layout.pageInset,
        top: d.layout.topInset,
        width: cardW,
        minHeight: cardMaxH,
        maxHeight: cardMaxH,
        ...glassCard,
        padding: `${padY}px ${padX}px`,
        boxShadow: glassCardShadow,
        boxSizing: "border-box",
        opacity: cardProgress,
        transform: `translateY(${overshootTranslateY(cardProgress, d.scaled(CARD_ENTRANCE_Y))}px)`,
        display: "flex",
        gap,
        alignItems: "stretch",
        overflow: "hidden",
      }}
    >
      <GlassShimmer frame={frame} />
      {showChapterWatermark && (
        <ChapterWatermark
          displayIndex={displayOrdinal}
          storyCount={storyCount}
          padX={padX}
          padY={padY}
          frame={frame}
        />
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
          alignSelf: hasImage ? undefined : "center",
        }}
      >
        {/* Header row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: d.scaled(12),
            marginBottom: headerMargin(compact),
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [HEADER_ENTRANCE_Y, 0])}px)`,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: d.scaled(10) }}>
            <div
              style={{
                width: d.scaled(3),
                height: d.scaled(14),
                borderRadius: 2,
                background: tone.accent,
                flexShrink: 0,
              }}
            />
            <span
              style={{
                fontFamily: FONTS.sans,
                fontSize: d.fs.bodySmall,
                fontWeight: FW.semibold,
                color: tone.labelText,
                letterSpacing: 0.4,
              }}
            >
              重点观察
            </span>
          </div>
          {sourceDomain && (
            <span
              style={{
                fontFamily: FONTS.mono,
                fontSize: d.fs.caption,
                fontWeight: FW.semibold,
                color: COLORS.textTertiary,
                backgroundColor: COLORS.surfaceFaint,
                border: `1px solid ${COLORS.borderLow}`,
                borderRadius: d.scaled(4),
                padding: `${d.scaled(3)}px ${d.scaled(10)}px`,
                lineHeight: 1.4,
                letterSpacing: 0.2,
              }}
            >
              {sourceDomain}
            </span>
          )}
        </div>

        {/* Main title */}
        <div
          style={{
            fontFamily: FONTS.bold,
            fontWeight: FW.heavy,
            fontSize: resolvedTitleFontSize,
            color: COLORS.text,
            lineHeight: 1.15,
            letterSpacing: -0.4,
            marginBottom: showOriginalTitle ? titleBodyGap(compact) * 0.5 : titleBodyGap(compact),
            overflowWrap: "anywhere",
            wordBreak: "break-word",
            maxWidth: textColW,
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [TITLE_ENTRANCE_Y, 0])}px)`,
            ...lineClamp(2),
          }}
        >
          {mainTitle}
        </div>

        {/* English subtitle */}
        {showOriginalTitle && (
          <div
            style={{
              fontFamily: FONTS.sans,
              fontWeight: FW.regular,
              fontSize: d.fs.bodyLg,
              color: COLORS.textTertiary,
              marginBottom: titleBodyGap(compact),
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
              gap: d.scaled(10),
              marginBottom: hasBody ? bodySectionGap(compact) : 0,
            }}
          >
            {heatLevel && (
              <span
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: d.fs.pill,
                  fontWeight: FW.bold,
                  color: COLORS.white,
                  background: `linear-gradient(135deg, ${COLORS.orange} 0%, ${COLORS.orangeRed}BB 100%)`,
                  borderRadius: 999,
                  padding: `${d.scaled(4)}px ${d.scaled(14)}px`,
                  letterSpacing: 0.3,
                  opacity: interpolate(frame, [12, 18], [0, 1], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                  }),
                  transform: `translateY(${interpolate(frame, [12, 18], [4, 0], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                  })}px)`,
                }}
              >
                {heatLevel}
              </span>
            )}
            {heatScore > 0 && <MetricPill icon="🔥" value={heatScore} delay={12} frame={frame} />}
            {commentCount > 0 && (
              <MetricPill icon="💬" value={commentCount} delay={14} frame={frame} />
            )}
          </div>
        )}

        {/* Body: why it matters + impact */}
        {hasBody && (
          <div
            style={{
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [BODY_ENTRANCE_Y, 0])}px)`,
            }}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr",
                gap: d.scaled(compact ? 8 : 12),
                marginBottom: keywords.length > 0 ? bodySectionGap(compact) : 0,
                maxWidth: textColW,
              }}
            >
              {insightPoints.map((point, i) => (
                <InfoPoint
                  key={`${point.label}-${i}`}
                  point={{
                    ...point,
                    text: cleanText(point.text),
                  }}
                  delay={16 + i * 5}
                  frame={frame}
                  index={i}
                />
              ))}
            </div>
          </div>
        )}

        {/* Keywords row */}
        {keywords.length > 0 && (
          <>
            <div style={dividerStyle} />
            <CardKeywordsFooter
              keywords={keywords}
              progress={footerProgress}
              frame={frame}
              delayBase={20}
            />
          </>
        )}

        {/* Spacer when no body, no metrics, no keywords */}
        {!hasBody && !showMetrics && keywords.length === 0 && <div style={{ flex: 1 }} />}
      </div>

      {/* Right: image panel — focus chapter renders large hero, logo stays compact */}
      {hasImage && (
        <div
          style={{
            flex: `0 0 ${mediaW}px`,
            alignSelf: "stretch",
            display: "flex",
            alignItems: heroImage ? "stretch" : "center",
            opacity: imageProgress,
            transform: `perspective(1000px) rotateY(${interpolate(imageProgress, [0, 1], [3, -1.5])}deg) translateX(${interpolate(imageProgress, [0, 1], [IMAGE_ENTRANCE_X, 0])}px)`,
          }}
        >
          <div
            style={{
              borderRadius: IMAGE_PANEL_RADIUS,
              overflow: "hidden",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: IMAGE_PANEL_BG,
              border: IMAGE_PANEL_BORDER,
              boxShadow: IMAGE_PANEL_SHADOW,
              width: mediaW,
              height: heroImage ? "100%" : mediaH,
              position: "relative",
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
              <>
                <img
                  src={staticFile(imageSrc)}
                  alt=""
                  style={{
                    width: "100%",
                    height: "100%",
                    objectFit: "cover",
                  }}
                />
                {/* Bottom overlay strip — chapter accent gradient anchors the hero to the page */}
                <div
                  style={{
                    position: "absolute",
                    left: 0,
                    right: 0,
                    bottom: 0,
                    height: "28%",
                    background: `linear-gradient(180deg, transparent 0%, ${tone.accentBg} 60%, rgba(0,0,0,0.30) 100%)`,
                    pointerEvents: "none",
                  }}
                />
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

import React from "react";
import { interpolate, staticFile, useCurrentFrame } from "remotion";

import {
  COLORS,
  FONTS,
  FW,
  glassCard,
  glassCardShadow,
  S,
  useChapterTone,
  useDesign,
} from "./design";
import {
  CardKeywordsFooter,
  ChapterWatermark,
  GlassShimmer,
  MetricPill,
  bodySectionGap,
  dividerStyle,
  headerMargin,
  lineClamp,
  overshootTranslateY,
  titleBodyGap,
  titleFontSize,
  useCardAnimations,
  useCardPad,
  BODY_ENTRANCE_Y,
  CARD_ENTRANCE_Y,
  HEADER_ENTRANCE_Y,
  IMAGE_ENTRANCE_X,
  IMAGE_PANEL_BG,
  IMAGE_PANEL_BORDER,
  IMAGE_PANEL_RADIUS,
  IMAGE_PANEL_SHADOW,
  TITLE_ENTRANCE_Y,
} from "./HighlightShared";
import { cleanText, ElementProps, limitList, p } from "./utils";

const AccentPanel: React.FC<{
  label: string;
  text: string;
  accent: string;
  muted?: boolean;
}> = ({ label, text, accent, muted = false }) => {
  const d = useDesign();
  if (!text) {
    return null;
  }

  return (
    <div
      style={{
        backgroundColor: COLORS.surfaceFaint,
        borderLeft: `${d.scaled(3)}px solid ${accent}`,
        borderRadius: d.scaled(8),
        padding: `${d.scaled(10)}px ${d.scaled(14)}px`,
      }}
    >
      <div
        style={{
          fontFamily: FONTS.sans,
          fontSize: d.fs.caption,
          fontWeight: FW.bold,
          color: accent,
          lineHeight: 1.4,
          marginBottom: d.scaled(4),
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: FONTS.sans,
          fontSize: muted ? d.fs.bodyLg : d.fs.body,
          fontWeight: muted ? FW.medium : FW.semibold,
          color: muted ? COLORS.textSecondary : COLORS.textBody,
          lineHeight: 1.65,
          overflowWrap: "anywhere",
          wordBreak: "break-word",
          ...lineClamp(2),
        }}
      >
        {text}
      </div>
    </div>
  );
};

function discussionModeLabel(mode: string): string {
  const labels: Record<string, string> = {
    debate: "有分歧",
    field_notes: "经验补充",
    nostalgia: "怀旧回看",
    troubleshooting: "排障讨论",
    qna: "问答解释",
    correction: "事实纠偏",
    showcase: "作品反馈",
    low_signal: "轻讨论",
  };
  return labels[mode] || "社区氛围";
}

const CommunityPulse: React.FC<{
  mode: string;
  summary: string;
}> = ({ mode, summary }) => {
  const d = useDesign();
  if (!summary) {
    return null;
  }
  const label = discussionModeLabel(mode);

  return (
    <div
      style={{
        backgroundColor: COLORS.surfaceFaint,
        borderLeft: `${d.scaled(3)}px solid ${COLORS.green}`,
        borderRadius: d.scaled(8),
        padding: `${d.scaled(10)}px ${d.scaled(14)}px`,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: d.scaled(8),
          marginBottom: d.scaled(4),
        }}
      >
        <span
          style={{
            fontFamily: FONTS.sans,
            fontSize: d.fs.caption,
            fontWeight: FW.bold,
            color: COLORS.green,
            lineHeight: 1.4,
          }}
        >
          社区氛围
        </span>
        <span
          style={{
            fontFamily: FONTS.sans,
            fontSize: d.fs.caption,
            fontWeight: FW.bold,
            color: COLORS.textTertiary,
            backgroundColor: COLORS.surfaceSubtle,
            borderRadius: d.scaled(4),
            padding: `${d.scaled(1)}px ${d.scaled(6)}px`,
            lineHeight: 1.4,
          }}
        >
          {label}
        </span>
      </div>
      <div
        style={{
          fontFamily: FONTS.sans,
          fontSize: d.fs.body,
          fontWeight: FW.medium,
          color: COLORS.textSecondary,
          lineHeight: 1.55,
          overflowWrap: "anywhere",
          wordBreak: "break-word",
          ...lineClamp(2),
        }}
      >
        {summary}
      </div>
    </div>
  );
};

/** Three vertical mini bars showing this story's "shape" — score / comments / depth. */
const StoryShapeBars: React.FC<{
  score: number;
  comments: number;
  depthChars: number;
  delay: number;
  frame: number;
  accent: string;
}> = ({ score, comments, depthChars, delay, frame, accent }) => {
  const d = useDesign();
  const grow = interpolate(frame, [delay, delay + 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  // Soft caps tuned to typical HN values; values above the cap clip at 100%.
  const bars = [
    { label: "热度", value: score, cap: 600, key: "heat" },
    { label: "讨论", value: comments, cap: 300, key: "talk" },
    { label: "深度", value: depthChars, cap: 250, key: "depth" },
  ];
  const maxBarH = d.scaled(48);
  const barW = d.scaled(12);
  return (
    <div
      style={{
        display: "flex",
        gap: d.scaled(14),
        alignItems: "flex-end",
        justifyContent: "center",
        paddingTop: d.scaled(10),
      }}
    >
      {bars.map((b, i) => {
        const ratio = Math.min(1, b.value / b.cap);
        const segGrow = interpolate(grow, [i * 0.18, i * 0.18 + 0.55], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        });
        const h = Math.max(d.scaled(4), maxBarH * ratio * segGrow);
        return (
          <div
            key={b.key}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: d.scaled(6),
              minWidth: barW,
            }}
          >
            <div
              style={{
                position: "relative",
                width: barW,
                height: maxBarH,
                display: "flex",
                alignItems: "flex-end",
                backgroundColor: COLORS.surfaceLow,
                borderRadius: 999,
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: "100%",
                  height: h,
                  backgroundColor: accent,
                  borderRadius: 999,
                }}
              />
            </div>
            <span
              style={{
                fontFamily: FONTS.sans,
                fontSize: d.fs.micro,
                color: COLORS.textTertiary,
                fontWeight: FW.semibold,
                lineHeight: 1,
              }}
            >
              {b.label}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export const StoryCompactCard: React.FC<ElementProps> = ({ elementProps, width }) => {
  const frame = useCurrentFrame();
  const tone = useChapterTone();
  const d = useDesign();
  const compact = d.isCompactHeight;
  const { padX, padY } = useCardPad(compact);
  const { cardProgress, titleProgress, bodyProgress, imageProgress, footerProgress } =
    useCardAnimations(frame);

  const displayTitle = cleanText(
    p(elementProps, "display_title", "") ||
      p(elementProps, "editor_angle", "") ||
      p(elementProps, "title_cn", "") ||
      p(elementProps, "source_title", ""),
  );
  const sourceTitle = cleanText(p(elementProps, "source_title", ""));
  const sourceDomain = cleanText(p(elementProps, "source_domain", ""));
  const readerHook = cleanText(p(elementProps, "reader_hook", ""));
  const microTakeaway =
    cleanText(p(elementProps, "micro_takeaway", "")) ||
    cleanText(p(elementProps, "discussion_summary", ""));
  const discussionMode = cleanText(p(elementProps, "discussion_mode", ""));
  const discussionSummary = cleanText(p(elementProps, "discussion_summary", ""));
  const category = cleanText(p(elementProps, "category", ""));
  const imageSrc = p(elementProps, "image_src", "");
  const imageType = p<string>(elementProps, "image_type", "");
  const score = Number(p(elementProps, "score", 0)) || 0;
  const commentCount = Number(p(elementProps, "comment_count", 0)) || 0;
  const heatLevel = cleanText(p(elementProps, "heat_level", ""));
  const displayIndex = Number(p(elementProps, "display_index", 0)) || 0;
  const storyCount = Number(p(elementProps, "story_count", 0)) || 0;
  const subtitleTexts = Array.isArray(elementProps.subtitle_texts)
    ? (elementProps.subtitle_texts as unknown[]).filter((s): s is string => typeof s === "string")
    : [];
  const subtitleCharCount = subtitleTexts.reduce((s, t) => s + t.length, 0);
  const keywords = limitList(
    Array.isArray(elementProps.keywords)
      ? elementProps.keywords.filter((k): k is string => typeof k === "string")
      : [],
    4,
    16,
  );

  const cardW = width - d.layout.pageInset * 2;
  const cardH = d.getCardMaxHeight;
  const hasImage = imageSrc !== "";
  const isLogo = imageType === "logo";
  const isScreenshot = imageType === "screenshot" || imageType === "article";
  // Always reserve a media column — fall back to a domain/keyword placeholder when no image.
  const mediaW = isLogo ? d.scaled(180) : Math.round(cardW * 0.28);
  const mediaH = isLogo
    ? Math.min(d.scaled(190), cardH - padY * 2)
    : Math.min(Math.round((mediaW * 10) / 16), cardH - padY * 2);
  const gap = d.scaled(compact ? 24 : 30);
  const availableTextW = cardW - mediaW - gap - padX * 2;
  const textMaxW = Math.max(d.scaled(420), Math.min(availableTextW, cardW - padX * 2));
  const showOriginalTitle = Boolean(sourceTitle && sourceTitle !== displayTitle);
  const showMetrics = score > 0 || commentCount > 0 || heatLevel !== "";

  return (
    <div
      style={{
        ...S,
        left: d.layout.pageInset,
        top: d.layout.topInset,
        width: cardW,
        minHeight: cardH,
        maxHeight: cardH,
        ...glassCard,
        boxShadow: glassCardShadow,
        padding: `${padY}px ${padX}px`,
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
      {storyCount > 0 && (
        <ChapterWatermark
          displayIndex={displayIndex + 1}
          storyCount={storyCount}
          padX={padX}
          padY={padY}
          frame={frame}
        />
      )}

      <div
        style={{
          flex: `0 0 ${textMaxW}px`,
          maxWidth: textMaxW,
          minWidth: 0,
          position: "relative",
          zIndex: 1,
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
        }}
      >
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
              速读
            </span>
          </div>
          {category && (
            <span
              style={{
                fontFamily: FONTS.sans,
                fontSize: d.fs.caption,
                fontWeight: FW.bold,
                color: COLORS.textTertiary,
                backgroundColor: COLORS.surfaceFaint,
                border: `1px solid ${COLORS.borderLow}`,
                borderRadius: d.scaled(4),
                padding: `${d.scaled(3)}px ${d.scaled(8)}px`,
                lineHeight: 1.4,
              }}
            >
              {category}
            </span>
          )}
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
              }}
            >
              {sourceDomain}
            </span>
          )}
        </div>

        <div
          style={{
            fontFamily: FONTS.bold,
            fontWeight: FW.heavy,
            fontSize: titleFontSize(d, compact),
            color: COLORS.text,
            lineHeight: 1.15,
            letterSpacing: 0,
            marginBottom: showOriginalTitle ? titleBodyGap(compact) * 0.5 : titleBodyGap(compact),
            overflowWrap: "anywhere",
            wordBreak: "break-word",
            opacity: titleProgress,
            transform: `translateY(${interpolate(titleProgress, [0, 1], [TITLE_ENTRANCE_Y, 0])}px)`,
            ...lineClamp(2),
          }}
        >
          {displayTitle}
        </div>

        {showOriginalTitle && (
          <div
            style={{
              fontFamily: FONTS.sans,
              fontWeight: FW.regular,
              fontSize: d.fs.bodyLg,
              color: COLORS.textTertiary,
              marginBottom: titleBodyGap(compact),
              lineHeight: 1.4,
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

        {showMetrics && (
          <div
            style={{
              display: "flex",
              gap: d.scaled(10),
              marginBottom: bodySectionGap(compact),
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
                  lineHeight: 1.2,
                }}
              >
                {heatLevel}
              </span>
            )}
            {score > 0 && <MetricPill icon="🔥" value={score} delay={12} frame={frame} />}
            {commentCount > 0 && (
              <MetricPill icon="💬" value={commentCount} delay={14} frame={frame} />
            )}
          </div>
        )}

        <div
          style={{
            opacity: bodyProgress,
            transform: `translateY(${interpolate(bodyProgress, [0, 1], [BODY_ENTRANCE_Y, 0])}px)`,
            display: "grid",
            gridTemplateColumns: "1fr",
            gap: d.scaled(compact ? 8 : 12),
          }}
        >
          <AccentPanel label="看点" text={readerHook} accent={COLORS.accent} />
          <CommunityPulse mode={discussionMode} summary={discussionSummary} />
          <AccentPanel label="记忆点" text={microTakeaway} accent={COLORS.brand} muted />
        </div>
        <div style={{ flex: 1 }} />
        {keywords.length > 0 && (
          <div style={{ position: "relative", zIndex: 1 }}>
            <div style={dividerStyle} />
            <CardKeywordsFooter
              keywords={keywords}
              progress={footerProgress}
              frame={frame}
              delayBase={20}
            />
          </div>
        )}
      </div>

      <div
        style={{
          flex: `0 0 ${mediaW}px`,
          alignSelf: "center",
          position: "relative",
          zIndex: 1,
          opacity: imageProgress,
          transform: `translateX(${interpolate(imageProgress, [0, 1], [IMAGE_ENTRANCE_X, 0])}px)`,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            width: mediaW,
            height: mediaH,
            borderRadius: IMAGE_PANEL_RADIUS,
            overflow: "hidden",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: IMAGE_PANEL_BG,
            border: IMAGE_PANEL_BORDER,
            boxShadow: IMAGE_PANEL_SHADOW,
          }}
        >
          {hasImage ? (
            isLogo ? (
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
                  objectPosition: isScreenshot ? "top" : "center",
                }}
              />
            )
          ) : (
            <div
              style={{
                width: "100%",
                height: "100%",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: d.scaled(10),
                padding: d.scaled(16),
                background: `radial-gradient(ellipse at 30% 20%, ${COLORS.accentBg} 0%, transparent 60%), ${IMAGE_PANEL_BG}`,
                boxSizing: "border-box",
              }}
            >
              <span
                style={{
                  fontFamily: FONTS.mono,
                  fontSize: d.fs.caption,
                  fontWeight: FW.bold,
                  color: COLORS.textTertiary,
                  letterSpacing: 0.4,
                }}
              >
                {sourceDomain || "hacker news"}
              </span>
              {keywords.slice(0, 2).map((kw) => (
                <span
                  key={kw}
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: d.fs.caption,
                    fontWeight: FW.semibold,
                    color: COLORS.accentLight,
                    backgroundColor: COLORS.accentBg,
                    border: `1px solid ${COLORS.borderLow}`,
                    borderRadius: d.scaled(6),
                    padding: `${d.scaled(3)}px ${d.scaled(10)}px`,
                    textAlign: "center",
                    maxWidth: "90%",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {kw}
                </span>
              ))}
            </div>
          )}
        </div>
        <StoryShapeBars
          score={score}
          comments={commentCount}
          depthChars={subtitleCharCount}
          delay={18}
          frame={frame}
          accent={tone.accent}
        />
      </div>
    </div>
  );
};

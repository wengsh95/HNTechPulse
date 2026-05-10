import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, staticFile } from "remotion";

import { cleanText, ElementProps, p, UI_TEXT } from "./utils";
import { COLORS, FONTS, glassCard, glassCardShadow, LAYOUT, S, sectionLabel } from "./design";

export const EventCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const storyTitle = cleanText(p(elementProps, "story_title", ""));
  const titleCn = cleanText(p(elementProps, "title_cn", ""));
  const editorAngle = cleanText(p(elementProps, "editor_angle", ""));
  const eventSummary = cleanText(p(elementProps, "event_summary", ""));
  const imageSrc = p(elementProps, "image_src", "");
  const imageType = p<string>(elementProps, "image_type", "");
  const keywords = (elementProps.keywords as string[]) ?? [];
  const mainTitle = editorAngle || titleCn || storyTitle;
  const showOriginalTitle = Boolean(storyTitle && mainTitle !== storyTitle);

  const hasImage = imageSrc !== "";
  const isLogo = imageType === "logo";
  const cardW = width - LAYOUT.pageInset * 2;
  const topY = Math.round(height * 0.13);

  const cardProgress = spring({
    frame,
    fps,
    config: { damping: 14, stiffness: 120 },
  });

  const mediaW = hasImage ? (isLogo ? 340 : Math.round(cardW * 0.40)) : 0;
  const mediaH = isLogo ? 280 : 336;
  const textColW = hasImage
    ? cardW - mediaW - 28 - 72
    : Math.min(cardW - 96, LAYOUT.contentMaxWidth);

  return (
    <div
      style={{
        ...S,
        left: LAYOUT.pageInset,
        top: topY,
        width: cardW,
        ...glassCard,
        padding: hasImage ? "28px 36px 30px" : "36px 44px 38px",
        boxShadow: glassCardShadow,
        boxSizing: "border-box",
        opacity: cardProgress,
        transform: `translateY(${interpolate(cardProgress, [0, 1], [28, 0])}px)`,
        display: "flex",
        gap: 28,
        alignItems: "stretch",
        overflow: "hidden",
      }}
    >
      <div style={{ flex: hasImage ? `0 0 ${textColW}px` : 1, maxWidth: textColW, minWidth: 0 }}>
        <div style={sectionLabel}>{UI_TEXT.eventDetail}</div>

        <div
          style={{
            fontFamily: FONTS.bold,
            fontWeight: 700,
            fontSize: 30,
            color: COLORS.text,
            lineHeight: 1.16,
            letterSpacing: 0,
            marginBottom: 12,
            overflowWrap: "anywhere",
            wordBreak: "break-word",
          }}
        >
          {mainTitle}
        </div>

        {showOriginalTitle && (
          <div
            style={{
              fontFamily: FONTS.sans,
              fontWeight: 500,
              fontSize: 20,
              color: COLORS.textSecondary,
              marginBottom: 14,
              lineHeight: 1.4,
              maxWidth: LAYOUT.contentMaxWidth,
              overflowWrap: "anywhere",
              wordBreak: "break-word",
            }}
          >
            {storyTitle}
          </div>
        )}

        {eventSummary && (
          <div
            style={{
              fontFamily: FONTS.sans,
              fontSize: 20,
              color: COLORS.textSecondary,
              lineHeight: 1.42,
              fontWeight: 400,
              marginBottom: 18,
              maxWidth: LAYOUT.contentMaxWidth,
              overflowWrap: "anywhere",
              wordBreak: "break-word",
            }}
          >
            {eventSummary}
          </div>
        )}

        {keywords.length > 0 && (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 10,
              marginBottom: 20,
              maxWidth: LAYOUT.contentMaxWidth,
            }}
          >
            {keywords.map((kw, i) => {
              const tagProgress = spring({
                frame,
                fps,
                config: { damping: 10, stiffness: 140 },
                delay: 5 + i * 3,
              });

              return (
                <span
                  key={kw}
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: 12,
                    fontWeight: 600,
                    color: COLORS.accentLight,
                    backgroundColor: COLORS.accentBg,
                    borderRadius: 999,
                    padding: "5px 12px",
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
        )}

      </div>

      {hasImage && (
        <div
          style={{
            flex: `0 0 ${mediaW}px`,
            height: mediaH,
            borderRadius: 18,
            overflow: "hidden",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(255,255,255,0.035)",
            border: "1px solid rgba(255,255,255,0.06)",
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
                objectFit: "contain",
              }}
            />
          )}
        </div>
      )}
    </div>
  );
};

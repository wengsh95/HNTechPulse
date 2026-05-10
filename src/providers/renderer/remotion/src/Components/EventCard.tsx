import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, spring, staticFile } from "remotion";

import { ElementProps, limitList, p, truncate, UI_TEXT } from "./utils";
import { COLORS, FONTS, glassCard, glassCardShadow, LAYOUT, S } from "./design";

const CONTROVERSY_COLORS = {
  green: "#34c759",
  yellow: "#ff9f0a",
  red: "#ff3b30",
};

function getControversyColor(score: number): string {
  if (score <= 3) return CONTROVERSY_COLORS.green;
  if (score <= 7) return CONTROVERSY_COLORS.yellow;
  return CONTROVERSY_COLORS.red;
}

function getControversyLabel(score: number): string {
  if (score <= 3) return "共识较强";
  if (score <= 7) return "存在分歧";
  return "高度争议";
}

export const EventCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const storyTitle = truncate(p(elementProps, "story_title", ""), 104);
  const titleCn = truncate(p(elementProps, "title_cn", ""), 42);
  const editorAngle = truncate(p(elementProps, "editor_angle", ""), 42);
  const eventSummary = truncate(p(elementProps, "event_summary", ""), 64);
  const whyItMatters = truncate(p(elementProps, "why_it_matters", ""), 54);
  const nextWatch = truncate(p(elementProps, "next_watch", ""), 42);
  const category = truncate(p(elementProps, "category", ""), 12);
  const controversyScore = p(elementProps, "controversy_score", 0);
  const commentCount = Number(p(elementProps, "comment_count", 0)) || 0;
  const heatScore = Number(p(elementProps, "score", 0)) || 0;
  const scoreNum =
    typeof controversyScore === "number" ? controversyScore : Number(controversyScore) || 0;
  const controversyColor = getControversyColor(scoreNum);
  const controversyLabel = getControversyLabel(scoreNum);

  const imageSrc = p(elementProps, "image_src", "");
  const imageType = p<string>(elementProps, "image_type", "");
  const keywords = limitList((elementProps.keywords as string[]) ?? [], 3, 16);
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

  const badgeProgress = spring({
    frame,
    fps,
    config: { damping: 10, stiffness: 150 },
    delay: 8,
  });

  const mediaW = hasImage ? (isLogo ? 340 : Math.round(cardW * 0.47)) : 0;
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
      <div
        style={{
          ...S,
          left: 0,
          top: 0,
          width: "100%",
          height: 5,
          background: `linear-gradient(90deg, ${controversyColor}, ${controversyColor}22)`,
        }}
      />
      <div style={{ flex: hasImage ? `0 0 ${textColW}px` : 1, maxWidth: textColW, minWidth: 0 }}>
        <div
          style={{
            fontFamily: FONTS.bold,
            fontWeight: 700,
            fontSize: hasImage ? 32 : 36,
            color: COLORS.text,
            lineHeight: 1.16,
            letterSpacing: 0,
            marginBottom: 12,
            overflow: "hidden",
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical" as const,
          }}
        >
          {mainTitle}
        </div>

        {showOriginalTitle && (
          <div
            style={{
              fontFamily: FONTS.sans,
              fontWeight: 500,
              fontSize: 15,
              color: COLORS.textSecondary,
              marginBottom: 14,
              lineHeight: 1.4,
              maxWidth: LAYOUT.contentMaxWidth,
              overflow: "hidden",
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical" as const,
            }}
          >
            {storyTitle}
          </div>
        )}

        {eventSummary && (
          <div
            style={{
              fontFamily: FONTS.sans,
              fontSize: 22,
              color: COLORS.textSecondary,
              lineHeight: 1.5,
              fontWeight: 400,
              marginBottom: 20,
              maxWidth: LAYOUT.contentMaxWidth,
              overflow: "hidden",
              display: "-webkit-box",
              WebkitLineClamp: 2,
              WebkitBoxOrient: "vertical" as const,
            }}
          >
            {eventSummary}
          </div>
        )}

        {(whyItMatters || nextWatch) && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: whyItMatters && nextWatch ? "1fr 1fr" : "1fr",
              gap: 10,
              marginBottom: 18,
              maxWidth: LAYOUT.contentMaxWidth,
            }}
          >
            {whyItMatters && (
              <div
                style={{
                  backgroundColor: "rgba(255,255,255,0.045)",
                  border: "1px solid rgba(255,255,255,0.055)",
                  borderRadius: 12,
                  padding: "10px 12px",
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: 10,
                    fontWeight: 750,
                    color: COLORS.textTertiary,
                    marginBottom: 5,
                  }}
                >
                  为什么重要
                </div>
                <div
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: 14,
                    lineHeight: 1.35,
                    fontWeight: 560,
                    color: COLORS.textSecondary,
                    overflow: "hidden",
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical" as const,
                  }}
                >
                  {whyItMatters}
                </div>
              </div>
            )}
            {nextWatch && (
              <div
                style={{
                  backgroundColor: "rgba(0,122,255,0.08)",
                  border: "1px solid rgba(51,149,255,0.16)",
                  borderRadius: 12,
                  padding: "10px 12px",
                  minWidth: 0,
                }}
              >
                <div
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: 10,
                    fontWeight: 750,
                    color: COLORS.accentLight,
                    marginBottom: 5,
                  }}
                >
                  接下来观察
                </div>
                <div
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: 14,
                    lineHeight: 1.35,
                    fontWeight: 560,
                    color: COLORS.textSecondary,
                    overflow: "hidden",
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical" as const,
                  }}
                >
                  {nextWatch}
                </div>
              </div>
            )}
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
            {category && (
              <span
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: 12,
                  fontWeight: 700,
                  color: COLORS.text,
                  backgroundColor: "rgba(255,255,255,0.08)",
                  borderRadius: 999,
                  padding: "5px 12px",
                  letterSpacing: 0,
                }}
              >
                {category}
              </span>
            )}
          </div>
        )}

        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            flexWrap: "wrap",
            backgroundColor: controversyColor + "15",
            border: `1.5px solid ${controversyColor}40`,
            borderRadius: 16,
            padding: "10px 18px",
            opacity: badgeProgress,
            transform: `scale(${interpolate(badgeProgress, [0, 1], [0.6, 1])})`,
          }}
        >
          <span
            style={{
              fontFamily: FONTS.sans,
              fontSize: 12,
              fontWeight: 600,
              color: controversyColor,
              letterSpacing: 0,
            }}
          >
            {UI_TEXT.controversy}
          </span>
          <span
            style={{
              fontFamily: FONTS.mono,
              fontSize: 24,
              fontWeight: 700,
              color: controversyColor,
            }}
          >
            {scoreNum.toFixed(1)}
          </span>
          <span
            style={{
              fontFamily: FONTS.sans,
              fontSize: 12,
              color: COLORS.textSecondary,
            }}
          >
            {UI_TEXT.scoreSuffix}
          </span>
          {(commentCount > 0 || heatScore > 0) && (
            <span
              style={{
                fontFamily: FONTS.sans,
                fontSize: 12,
                color: COLORS.textSecondary,
                marginLeft: 4,
              }}
            >
              {commentCount > 0
                ? `${UI_TEXT.comments} ${commentCount}`
                : `${UI_TEXT.heat} ${heatScore}`}
            </span>
          )}
          <span
            style={{
              fontFamily: FONTS.sans,
              fontSize: 12,
              color: COLORS.textSecondary,
            }}
          >
            {controversyLabel}
          </span>
        </div>
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

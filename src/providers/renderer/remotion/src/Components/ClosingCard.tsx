import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { ElementProps, p } from "./utils";
import { COLORS, FONTS, FW, useDesign, glassCard, glassCardShadow, S } from "./design";
import {
  GlassShimmer,
  overshootTranslateY,
  SectionLabel,
  useCardPad,
  useCardAnimations,
  CARD_ENTRANCE_Y,
  HERO_ENTRANCE_Y,
  BODY_ENTRANCE_Y,
  FOOTER_ENTRANCE_Y,
  CardKeywordsFooter,
  dividerStyle,
} from "./HighlightShared";

export const ClosingCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();
  const d = useDesign();
  const compact = d.isCompactHeight;

  const question = p(elementProps, "question", "");
  const visualMood = p(elementProps, "visual_mood", "");
  const keywords = Array.isArray(elementProps.keywords)
    ? elementProps.keywords.filter((k): k is string => typeof k === "string")
    : [];

  const cardW = width - d.layout.pageInset * 2;
  const cardH = d.getCardMaxHeight;
  const { padX, padY } = useCardPad(compact);
  const { cardProgress, titleProgress, bodyProgress, footerProgress } = useCardAnimations(frame);

  return (
    <div
      style={{
        ...S,
        left: d.layout.pageInset,
        top: d.layout.topInset,
        width: cardW,
        height: cardH,
        ...glassCard,
        boxShadow: glassCardShadow,
        padding: `${padY}px ${padX}px`,
        boxSizing: "border-box",
        opacity: cardProgress,
        transform: `translateY(${overshootTranslateY(cardProgress, d.scaled(CARD_ENTRANCE_Y))}px)`,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <GlassShimmer frame={frame} />

      {/* Header row */}
      <SectionLabel text="每日速递" delay={8} frame={frame} />

      {/* Main content area - centered */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          position: "relative",
          zIndex: 1,
          minHeight: 0,
        }}
      >
        {question && (
          <div
            style={{
              opacity: titleProgress,
              transform: `translateY(${interpolate(titleProgress, [0, 1], [HERO_ENTRANCE_Y, 0])}px)`,
              textAlign: "center",
              maxWidth: "100%",
            }}
          >
            <div
              style={{
                fontFamily: FONTS.bold,
                fontSize: d.fs.headline,
                color: COLORS.text,
                lineHeight: 1.35,
                fontWeight: FW.bold,
                letterSpacing: 0,
              }}
            >
              {question}
            </div>
          </div>
        )}

        {visualMood && (
          <div
            style={{
              marginTop: d.scaled(compact ? 24 : 36),
              opacity: bodyProgress,
              transform: `translateY(${interpolate(bodyProgress, [0, 1], [BODY_ENTRANCE_Y, 0])}px)`,
              textAlign: "center",
            }}
          >
            <div
              style={{
                fontFamily: FONTS.mono,
                fontSize: d.fs.body,
                color: COLORS.textSecondary,
                fontWeight: FW.medium,
                letterSpacing: 0.4,
                textTransform: "uppercase",
              }}
            >
              {visualMood}
            </div>
          </div>
        )}

        <div
          style={{
            marginTop: visualMood ? d.scaled(compact ? 36 : 48) : d.scaled(compact ? 48 : 64),
            opacity: footerProgress,
            transform: `translateY(${interpolate(footerProgress, [0, 1], [FOOTER_ENTRANCE_Y, 0])}px)`,
            textAlign: "center",
          }}
        >
          <div
            style={{
              fontFamily: FONTS.bold,
              fontWeight: FW.bold,
              fontSize: d.fs.closing,
              color: COLORS.text,
              lineHeight: 1.15,
              letterSpacing: 0,
            }}
          >
            <span style={{ color: COLORS.brand }}>HN</span> TechPulse
          </div>
        </div>
      </div>

      {/* Keywords footer */}
      {keywords.length > 0 && (
        <>
          <div style={dividerStyle} />
          <CardKeywordsFooter keywords={keywords.slice(0, 3)} progress={footerProgress} frame={frame} delayBase={20} />
        </>
      )}
    </div>
  );
};

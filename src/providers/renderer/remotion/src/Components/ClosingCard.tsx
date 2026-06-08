import React from "react";
import { interpolate, useCurrentFrame } from "remotion";

import { CardShell, Fill } from "./CardShell";
import { NumberDisc, Panel } from "./CardPrimitives";
import {
  ANIM,
  CARD_LAYOUT,
  CLOSING_LAYOUT,
  COLORS,
  COMMON_LAYOUT,
  EASE_CARD,
  FONTS,
  FW,
  useDesign,
} from "./design";
import { extractClosingProps } from "./propsExtractors";
import type { ElementProps } from "./utils";

export const ClosingCard: React.FC<ElementProps> = ({ elementProps }) => {
  const frame = useCurrentFrame();
  const d = useDesign();
  const props = extractClosingProps(elementProps);
  const { summary, completedStories } = props;

  const subtitle =
    props.takeaways.length > 0
      ? props.takeaways.join(" / ")
      : props.stats.storyCount > 0
        ? `${props.stats.storyCount} 个关键故事，一条共同的结构变化`
        : "";

  const titleProgress = interpolate(frame, [ANIM.titleStart, ANIM.titleEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyProgress = interpolate(frame, [ANIM.bodyStart, ANIM.bodyEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const titleY = interpolate(titleProgress, [0, 1], [COMMON_LAYOUT.riseSmall, 0]);
  const bodyY = interpolate(bodyProgress, [0, 1], [COMMON_LAYOUT.riseSmall, 0]);
  const justify = completedStories.length >= CLOSING_LAYOUT.centerThreshold ? "start" : "center";

  return (
    <CardShell
      elementProps={elementProps}
      justify={justify}
      gutter={CLOSING_LAYOUT.gutter}
      paddingTop={CLOSING_LAYOUT.paddingTop}
      paddingBottom={CLOSING_LAYOUT.paddingBottom}
      showTopBar
      showWatermark={false}
      showWaveform
      reserveSubtitle
    >
      <Fill gap={CLOSING_LAYOUT.fillGap} maxWidth={CARD_LAYOUT.content.wideMaxWidth}>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: d.scaled(18),
            opacity: titleProgress,
            transform: `translateY(${titleY}px)`,
          }}
        >
          <h1
            style={{
              margin: 0,
              color: COLORS.fg,
              fontFamily: FONTS.serifBold,
              fontSize: Math.round(d.fs.text5xl * CLOSING_LAYOUT.titleScale),
              fontWeight: FW.heavy,
              lineHeight: 1.12,
              letterSpacing: 0,
            }}
          >
            今日回顾
          </h1>
          {summary && (
            <p
              style={{
                margin: 0,
                maxWidth: d.scaled(CARD_LAYOUT.content.wideMaxWidth),
                color: COLORS.inkSoft,
                fontFamily: FONTS.sans,
                fontSize: d.fs.textBase,
                lineHeight: 1.3,
              }}
            >
              {summary}
            </p>
          )}
          {subtitle && (
            <p
              style={{
                margin: 0,
                maxWidth: d.scaled(CARD_LAYOUT.content.wideMaxWidth),
                color: COLORS.muted,
                fontFamily: FONTS.sans,
                fontSize: d.fs.textLg,
                lineHeight: 1.3,
              }}
            >
              {subtitle}
            </p>
          )}
        </div>

        {completedStories.length > 0 && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: d.scaled(CLOSING_LAYOUT.listGap),
              width: "100%",
              opacity: bodyProgress,
              transform: `translateY(${bodyY}px)`,
            }}
          >
            {completedStories.map((story, i) => (
              <Panel
                key={`${story.title}-${i}`}
                style={{
                  display: "grid",
                  gridTemplateColumns: `${d.scaled(COMMON_LAYOUT.numDiscSize)}px minmax(0, 1fr)`,
                  gap: d.scaled(CLOSING_LAYOUT.rowGap),
                  alignItems: "center",
                }}
              >
                <NumberDisc>{i + 1}</NumberDisc>
                <div style={{ minWidth: 0 }}>
                  <div
                    style={{
                      color: COLORS.fg,
                      fontFamily: FONTS.sans,
                      fontSize: d.fs.textXl,
                      fontWeight: FW.heavy,
                      lineHeight: 1.3,
                    }}
                  >
                    {story.title}
                  </div>
                  {story.signal && (
                    <div
                      style={{
                        marginTop: d.scaled(CLOSING_LAYOUT.subtitleMarginTop),
                        color: COLORS.inkFaint,
                        fontFamily: FONTS.sans,
                        fontSize: d.fs.textSm,
                        lineHeight: 1.25,
                      }}
                    >
                      {story.signal}
                    </div>
                  )}
                </div>
              </Panel>
            ))}
          </div>
        )}
      </Fill>
    </CardShell>
  );
};

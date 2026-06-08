import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";

import { COLORS, EASE_CARD, GRADIENTS, PROGRESS_LAYOUT, useDesign } from "./design";

interface ProgressBarProps {
  totalDuration: number;
  storyBoundaries: number[];
  activeStoryIndex?: number;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({
  totalDuration,
  storyBoundaries,
  activeStoryIndex = -1,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { layout } = useDesign();

  const currentTime = frame / fps;
  const progress = totalDuration > 0 ? Math.min(Math.max(currentTime / totalDuration, 0), 1) : 0;

  const fadeIn = interpolate(frame, [0, PROGRESS_LAYOUT.fadeInFrames], [0, 1], {
    easing: EASE_CARD,
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const BAR_HEIGHT = PROGRESS_LAYOUT.barHeight;
  const TICK_HEIGHT = PROGRESS_LAYOUT.tickHeight;
  const PAD = layout.progressInsetX;

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        height: TICK_HEIGHT + PROGRESS_LAYOUT.outerPaddingBottom,
        opacity: fadeIn,
        zIndex: 10,
      }}
    >
      {/* Track container */}
      <div
        style={{
          position: "absolute",
          left: PAD,
          right: PAD,
          bottom: layout.progressBottom,
          height: BAR_HEIGHT,
        }}
      >
        {/* Track background */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: COLORS.surfaceLow,
            borderRadius: BAR_HEIGHT / 2,
          }}
        />

        {/* Fill */}
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            height: BAR_HEIGHT,
            width: `${progress * 100}%`,
            background: GRADIENTS.accentFill,
            borderRadius: BAR_HEIGHT / 2,
          }}
        />

        {/* Story boundary ticks */}
        {storyBoundaries.map((t, i) => {
          const pos = totalDuration > 0 ? Math.min(Math.max(t / totalDuration, 0), 1) : 0;
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: `${pos * 100}%`,
                top: -(TICK_HEIGHT - BAR_HEIGHT) / 2,
                width: PROGRESS_LAYOUT.tickWidth,
                height: TICK_HEIGHT,
                borderRadius: PROGRESS_LAYOUT.tickRadius,
                background:
                  i === activeStoryIndex
                    ? COLORS.text
                    : progress >= pos
                      ? COLORS.accentLight
                      : COLORS.surfaceMid,
              }}
            />
          );
        })}
      </div>
    </div>
  );
};

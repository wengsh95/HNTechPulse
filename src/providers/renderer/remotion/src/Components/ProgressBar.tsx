import React from "react";
import { interpolate, Easing, useCurrentFrame, useVideoConfig } from "remotion";

import { COLORS, GRADIENTS, LAYOUT } from "./design";

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

  const currentTime = frame / fps;
  const progress = totalDuration > 0 ? Math.min(Math.max(currentTime / totalDuration, 0), 1) : 0;

  const fadeIn = interpolate(frame, [0, 12], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const BAR_HEIGHT = 3;
  const TICK_HEIGHT = 8;
  const PAD = LAYOUT.progressInsetX;

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        height: TICK_HEIGHT + 8,
        opacity: fadeIn,
      }}
    >
      {/* Track container */}
      <div
        style={{
          position: "absolute",
          left: PAD,
          right: PAD,
          bottom: LAYOUT.progressBottom,
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
                width: 1.5,
                height: TICK_HEIGHT,
                borderRadius: 1,
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

import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";

import { COLORS } from "./design";

interface ProgressBarProps {
  totalDuration: number;
  storyBoundaries: number[];
}

export const ProgressBar: React.FC<ProgressBarProps> = ({
  totalDuration,
  storyBoundaries,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const currentTime = frame / fps;
  const progress = Math.min(currentTime / totalDuration, 1);

  const fadeIn = interpolate(frame, [0, 12], [0, 1], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
  });

  const BAR_HEIGHT = 3;
  const TICK_HEIGHT = 7;
  const PAD = 24;

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
          bottom: 6,
          height: BAR_HEIGHT,
        }}
      >
        {/* Track background */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background: "rgba(255, 255, 255, 0.08)",
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
            background: `linear-gradient(90deg, ${COLORS.accent}, ${COLORS.accentLight})`,
            borderRadius: BAR_HEIGHT / 2,
            boxShadow: `0 0 6px ${COLORS.accent}60`,
          }}
        />

        {/* Story boundary ticks */}
        {storyBoundaries.map((t, i) => {
          const pos = t / totalDuration;
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
                  progress >= pos
                    ? COLORS.accentLight
                    : "rgba(255, 255, 255, 0.15)",
              }}
            />
          );
        })}
      </div>
    </div>
  );
};

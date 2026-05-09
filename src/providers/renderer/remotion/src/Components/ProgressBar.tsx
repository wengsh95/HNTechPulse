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

  const BAR_HEIGHT = 2;
  const TICK_HEIGHT = 6;
  const TRACK_COLOR = "rgba(255, 255, 255, 0.15)";
  const FILL_COLOR = COLORS.accent;

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 0,
        height: TICK_HEIGHT,
        opacity: fadeIn,
      }}
    >
      {/* Track */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: BAR_HEIGHT,
          background: TRACK_COLOR,
          borderRadius: BAR_HEIGHT / 2,
        }}
      />

      {/* Fill */}
      <div
        style={{
          position: "absolute",
          left: 0,
          bottom: 0,
          height: BAR_HEIGHT,
          width: `${progress * 100}%`,
          background: FILL_COLOR,
          borderRadius: BAR_HEIGHT / 2,
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
              bottom: 0,
              width: 1,
              height: TICK_HEIGHT,
              background:
                progress >= pos ? FILL_COLOR : "rgba(255, 255, 255, 0.25)",
            }}
          />
        );
      })}
    </div>
  );
};

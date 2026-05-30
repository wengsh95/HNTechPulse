import { Easing, interpolate } from "remotion";

/** Shared animation presets for all cards (1080p reference). */
export const ANIM_PRESETS = {
  card: { range: [4, 22] as [number, number], yOffset: 32 },
  title: { range: [8, 26] as [number, number], yOffset: 28 },
  body: { range: [14, 32] as [number, number], yOffset: 12 },
  meta: { range: [18, 36] as [number, number], yOffset: 8 },
} as const;

export const segmentLocalFrame = (absoluteFrame: number, segmentStartFrame: number) =>
  Math.max(0, absoluteFrame - segmentStartFrame);

export const segmentTransitionOpacity = ({
  absoluteFrame,
  startFrame,
  durationFrames,
  transitionFrames,
  isLastSegment,
}: {
  absoluteFrame: number;
  startFrame: number;
  durationFrames: number;
  transitionFrames: number;
  isLastSegment: boolean;
}) => {
  const localFrame = segmentLocalFrame(absoluteFrame, startFrame);
  const fadeIn = interpolate(localFrame, [0, transitionFrames], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const framesRemaining = durationFrames - localFrame;
  const fadeOut = isLastSegment
    ? 1
    : interpolate(framesRemaining, [0, transitionFrames], [0, 1], {
        easing: Easing.bezier(0.16, 1, 0.3, 1),
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });

  return fadeIn * fadeOut;
};

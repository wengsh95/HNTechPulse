import { Easing, interpolate } from "remotion";

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

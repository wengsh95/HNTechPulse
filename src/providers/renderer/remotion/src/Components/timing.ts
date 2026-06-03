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
  // 与 ElementFadeWrap 对齐: 每张卡 6 帧淡入淡出, 段间靠 premountFor + 双方各 6 帧 = 12 帧 cross-fade.
  // 首段和末段沿用较长的 transitionFrames, 避免首帧突兀 / 收尾硬切.
  const fadeInFrames = startFrame === 0 ? transitionFrames : 6;
  const fadeOutFrames = isLastSegment ? transitionFrames : 6;
  const fadeIn = interpolate(localFrame, [0, fadeInFrames], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fadeOut = interpolate(durationFrames - localFrame, [0, fadeOutFrames], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return fadeIn * fadeOut;
};

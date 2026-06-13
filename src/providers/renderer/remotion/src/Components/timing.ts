import React from "react";
import { interpolate } from "remotion";

import { EASE_CARD, TIMING_LAYOUT } from "./design";

/** Shared animation presets for all cards (24fps, aligned with ANIM in design.ts). */
export const ANIM_PRESETS = {
  card: { range: [3, 18] as [number, number], yOffset: 16 },
  title: { range: [6, 21] as [number, number], yOffset: 10 },
  body: { range: [11, 26] as [number, number], yOffset: 6 },
  meta: { range: [14, 29] as [number, number], yOffset: 4 },
} as const;

/**
 * 计算子元素的 fade-up 入场样式。
 * 用法: style={{ ...fadeUp(frame, ANIM_PRESETS.title) }}
 * 配合 ANIM_PRESETS 使用，产生 opacity + translateY 的交错入场效果。
 */
export const fadeUp = (
  frame: number,
  preset: { range: [number, number]; yOffset: number },
  /** 行级交错偏移帧数（默认 0） */
  stagger = 0,
): React.CSSProperties => {
  const [start, end] = preset.range;
  const progress = interpolate(frame, [start + stagger, end + stagger], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: EASE_CARD,
  });
  return {
    opacity: progress,
    transform: `translateY(${Math.round(interpolate(progress, [0, 1], [preset.yOffset, 0]))}px)`,
  };
};

const segmentLocalFrame = (absoluteFrame: number, segmentStartFrame: number) =>
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
  // 段级仅控制可见性, 卡片自身的 cardProgress 动画负责视觉入场.
  // 所有段均跳过段级淡入 (fadeIn=1), 完全交给 CardShell 处理,
  // 避免双层 ease-out 相乘导致的"切入抖动".
  // 段间靠 premountFor + 双方各 4 帧 = 8 帧 cross-fade. 末段沿用较长 transitionFrames 避免硬切.
  const fadeOutFrames = isLastSegment ? transitionFrames : TIMING_LAYOUT.segmentFadeFrames;
  const fadeOut = interpolate(durationFrames - localFrame, [0, fadeOutFrames], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return fadeOut;
};

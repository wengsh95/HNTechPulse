/* ================================================================
   WaveformBars — 音频波形可视化组件
   ================================================================

   垂直波形柱，底部排列，随音频或模拟信号跳动。
   支持预计算 amplitude 数据驱动，也支持无数据时的模拟模式。
*/

import React from "react";
import { useCurrentFrame } from "remotion";
import { COLORS, WAVEFORM_LAYOUT } from "./design";

interface WaveformBarsProps {
  /** 预计算的分帧振幅数据（每帧一个 0~1 的值），优先使用 */
  amplitudeData?: number[];
  /** 柱子数量，默认 28 */
  barCount?: number;
  /** 柱子宽度（px，参考值），默认 6 */
  barWidth?: number;
  /** 柱子间隔（px，参考值），默认 4 */
  barGap?: number;
  /** 最大高度（px，参考值），默认 80 */
  maxHeight?: number;
  /** 柱子颜色，默认 brand */
  color?: string;
  /** 距离底部偏移量，默认 20 */
  bottomOffset?: number;
  /** 是否圆形顶部，默认 true */
  roundTop?: boolean;
  /** 整体左边距（px），默认居中 */
  leftOffset?: number;
}

export const WaveformBars: React.FC<WaveformBarsProps> = ({
  amplitudeData,
  barCount = WAVEFORM_LAYOUT.barCount,
  barWidth = WAVEFORM_LAYOUT.barWidth,
  barGap = WAVEFORM_LAYOUT.barGap,
  maxHeight = WAVEFORM_LAYOUT.maxHeight,
  color = COLORS.brand,
  bottomOffset = WAVEFORM_LAYOUT.bottomOffset,
  roundTop = true,
  leftOffset,
}) => {
  const frame = useCurrentFrame();

  const totalWidth = barCount * barWidth + (barCount - 1) * barGap;
  const startX = leftOffset ?? (WAVEFORM_LAYOUT.canvasWidth - totalWidth) / 2;

  return (
    <>
      {Array.from({ length: barCount }).map((_, i) => {
        // 均匀采样 amplitude 数据
        const sampleIdx =
          amplitudeData && amplitudeData.length > 0
            ? Math.floor((i / barCount) * amplitudeData.length)
            : -1;

        let amp: number;

        if (sampleIdx >= 0) {
          amp =
            amplitudeData![Math.min(sampleIdx, amplitudeData!.length - 1)] ??
            WAVEFORM_LAYOUT.fallbackAmplitude;
        } else {
          // 模拟模式：多谐波正弦叠加，平滑变化
          const t = frame * WAVEFORM_LAYOUT.frameSpeed + i * WAVEFORM_LAYOUT.barPhaseStep;
          amp =
            Math.sin(t * 1.7) * 0.28 +
            Math.sin(t * 3.2) * 0.22 +
            Math.sin(t * 5.1) * 0.12 +
            Math.sin(t * 7.7) * 0.08 +
            WAVEFORM_LAYOUT.simulatedBaseAmplitude;
          amp = Math.max(WAVEFORM_LAYOUT.simulatedMinAmplitude, Math.min(1, amp));
        }

        const barHeight = Math.max(WAVEFORM_LAYOUT.fallbackMinHeight, maxHeight * amp);

        return (
          <div
            key={i}
            style={{
              position: "absolute" as const,
              bottom: bottomOffset,
              left: startX + i * (barWidth + barGap),
              width: barWidth,
              height: barHeight,
              background: color,
              borderRadius: roundTop ? barWidth / 2 : 0,
              opacity: WAVEFORM_LAYOUT.opacityBase + amp * WAVEFORM_LAYOUT.opacityScale,
            }}
          />
        );
      })}
    </>
  );
};

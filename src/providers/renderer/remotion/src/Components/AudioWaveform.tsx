/* ================================================================
   AudioWaveform — 真实音频波形可视化组件
   ================================================================

   使用 Remotion useAudioData + visualizeAudio 从真实音频文件
   读取振幅数据，驱动 WaveformBars 渲染。
*/

import React, { useState, useEffect } from "react";
import { useCurrentFrame, useVideoConfig, staticFile } from "remotion";
import { useAudioData, visualizeAudio } from "@remotion/media-utils";
import { WaveformBars } from "./WaveformBars";

interface AudioWaveformProps {
  /** 音频文件路径（相对于 public 目录） */
  src?: string;
  /** 柱子数量（2的幂次） */
  barCount?: number;
  /** 柱子宽度 */
  barWidth?: number;
  /** 柱子间隔 */
  barGap?: number;
  /** 最大高度（px） */
  maxHeight?: number;
  /** 颜色 */
  color?: string;
  /** 左边距 */
  leftOffset?: number;
}

export const AudioWaveform: React.FC<AudioWaveformProps> = ({
  src,
  barCount = 64,
  barWidth = 12,
  barGap = 5,
  maxHeight = 30,
  color,
  leftOffset,
}) => {
  // useAudioData is not null-safe — early return before hooks when src is missing
  if (!src || src.length === 0) {
    return (
      <WaveformBars
        amplitudeData={undefined}
        barCount={barCount}
        barWidth={barWidth}
        barGap={barGap}
        maxHeight={maxHeight}
        color={color}
        leftOffset={leftOffset}
      />
    );
  }

  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const audioData = useAudioData(staticFile(src));

  // Log state for debugging
  useEffect(() => {
    console.log("[AudioWaveform] src=", src, "audioData loaded:", !!audioData);
  }, [src, audioData]);

  let amplitudes: number[] | undefined;
  if (audioData) {
    try {
      const result: number[] = visualizeAudio({
        fps,
        frame,
        audioData,
        numberOfSamples: barCount,
        smoothing: true,
      });
      // 语音 amplitude 集中在低值区，做对数放大让波形更明显
      amplitudes = result.map((v) => {
        const db = 20 * Math.log10(Math.max(v, 1e-6));
        const scaled = (db + 80) / 80; // -80dB~0dB → 0~1
        return Math.max(0.02, Math.min(1, scaled));
      });
      console.log("[AudioWaveform] frame=", frame, "first3:", amplitudes.slice(0, 3));
    } catch (e) {
      console.warn("[AudioWaveform] visualizeAudio error:", e);
    }
  }

  return (
    <WaveformBars
      amplitudeData={amplitudes}
      barCount={barCount}
      barWidth={barWidth}
      barGap={barGap}
      maxHeight={maxHeight}
      color={color}
      leftOffset={leftOffset}
    />
  );
};
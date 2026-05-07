/**
 * HNTechPulseComposition —— 主合成组件
 *
 * 遍历所有 segments，按时间线排列，每个 segment 内部渲染其 scene_elements。
 * Remotion 的优势：浏览器原生渲染文字（GPU 加速），并行帧渲染。
 */
import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";

import { ScriptProps, SegmentData } from "../types";
import {
  TitleCard,
  Subtitle,
  ClosingCard,
  DashboardCard,
  StoryScanCard,
  ImageCard,
} from "./Elements";

const C_BG = "radial-gradient(ellipse 80% 60% at 50% 35%, #ececf2 0%, #f5f5f7 50%, #e8e8ed 100%)";

/** 元素类型 → React 组件映射 */
const ELEMENT_RENDERERS: Record<
  string,
  React.FC<{ elementProps: Record<string, unknown>; duration: number; width: number; height: number }>
> = {
  title_card: (props) => <TitleCard {...props} />,
  closing_card: (props) => <ClosingCard {...props} />,
  image_card: (props) => <ImageCard {...props} />,
  dashboard_card: (props) => <DashboardCard {...props} />,
  story_scan_card: (props) => <StoryScanCard {...props} />,
};

/** 渲染单个元素
 *
 * 注意：Sequence.from 期望帧数，不是秒数！
 * Remotion Sequence 组件的 from/durationInFrames 都以帧为单位。
 */
const SceneElementRenderer: React.FC<{
  elem: import("../types").SceneElementData;
  width: number;
  height: number;
  fps: number;
}> = ({ elem, width, height, fps }) => {
  const RendererComponent = ELEMENT_RENDERERS[elem.element_type];
  if (!RendererComponent) {
    console.warn(`[Remotion] Unknown element type: ${elem.element_type}`);
    return null;
  }

  const duration = elem.end_time - elem.start_time;
  if (duration <= 0) return null;

  const startFrame = Math.floor(elem.start_time * fps);
  const durationFrames = Math.max(1, Math.ceil(duration * fps));

  return (
    <Sequence
      from={startFrame}
      durationInFrames={durationFrames}
      layout="none"
    >
      {/* 用绝对定位 + offset 来定位，避免嵌套 Sequence 的复杂度 */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: "100%",
          height: "100%",
          pointerEvents: "none",
        }}
      >
        <RendererComponent
          elementProps={elem.props as Record<string, unknown>}
          duration={duration}
          width={width}
          height={height}
        />
      </div>
    </Sequence>
  );
};

/** 渲染单个 Segment */
const SegmentRenderer: React.FC<{
  segment: SegmentData;
  index: number;
  width: number;
  height: number;
  fps: number;
}> = ({ segment, index, width, height, fps }) => {
  const startFrame = Math.floor(segment.start_time * fps);
  const durationFrames = Math.max(1, Math.ceil(segment.duration * fps));
  const segmentDuration = segment.duration;

  return (
    <Sequence
      from={startFrame}
      durationInFrames={durationFrames}
      name={`segment-${index}-${segment.segment_type}`}
    >
      {/* 背景 */}
      <AbsoluteFill style={{ background: C_BG }} />

      {/* 场景元素 */}
      {segment.scene_elements.map((elem, i) => (
        <SceneElementRenderer
          key={`${index}-elem-${i}`}
          elem={elem}
          width={width}
          height={height}
          fps={fps}
        />
      ))}

      {/* 字幕（始终显示在底部，按 cues 逐句切换） */}
      <Subtitle
        elementProps={{ text: segment.audio_text, cues: segment.cues }}
        duration={segmentDuration}
        width={width}
        height={height}
      />
    </Sequence>
  );
};

/** 主 Composition 组件 */
export const HNTechPulseComposition: React.FC<ScriptProps> = ({
  width,
  height,
  fps,
  bgColor,
  segments,
  audioDir,
}) => {
  return (
    <AbsoluteFill style={{ background: bgColor || C_BG }}>
      {/* 遍历所有 segments，按时间线排列视觉内容 */}
      {segments.map((segment, index) => (
        <SegmentRenderer
          key={`seg-${index}`}
          segment={segment}
          index={index}
          width={width}
          height={height}
          fps={fps}
        />
      ))}

      {/* 音频轨道：每个音频用绝对定位的 Sequence，与视觉 Segment 严格对齐 */}
      {segments
        .filter((seg) => seg.audio_path && seg.duration > 0)
        .map((segment, index) => (
          <Sequence
            key={`audio-${index}`}
            from={Math.floor(segment.start_time * fps)}
            durationInFrames={Math.max(1, Math.ceil(segment.duration * fps))}
            name={`audio-seg-${index}`}
            layout="none"
          >
            <Audio src={staticFile(segment.audio_path!)} />
          </Sequence>
        ))}
    </AbsoluteFill>
  );
};

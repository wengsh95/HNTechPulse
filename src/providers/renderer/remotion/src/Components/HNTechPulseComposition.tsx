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
  StoryHeader,
  Highlight,
  CommentBubble,
  Subtitle,
  DiscussionOverview,
  CommentCard,
  PerspectiveCompare,
  SynthesisCard,
  NewsCarouselCard,
  PatternInsight,
  OutroCard,
  HookCard,
  ConflictCard,
  TurnCard,
  ClosingCard,
  DebateCard,
  InfoTable,
  DashboardCard,
  StoryScanCard,
  ImageCard,
} from "./Elements";

// ── HN Light 配色 ──────────────────────────────────
const C_BG = "#f6f6ef";
const C_TEXT = "#000000";
const C_DIM = "#828282";
const C_INFO = "#3c7bb3";
const C_HN_ORANGE = "#ff6600";
const C_COMMENT = "#5a5a5a";
const C_WARN = "#a03030";
const C_CODE = "#4a4a4a";
const C_PERSP_A = "#3c7bb3";
const C_PERSP_B = "#9b4dca";
const C_CARD_BG = "#ffffff";

/** 元素类型 → React 组件映射 */
const ELEMENT_RENDERERS: Record<
  string,
  React.FC<{ elementProps: Record<string, unknown>; duration: number; width: number; height: number }>
> = {
  title_card: (props) => <TitleCard {...props} />,
  story_header: (props) => <StoryHeader {...props} />,
  highlight: (props) => <Highlight {...props} />,
  comment_bubble: (props) => <CommentBubble {...props} />,
  subtitle: (props) => <Subtitle {...props} />,
  discussion_overview: (props) => <DiscussionOverview {...props} />,
  comment_card: (props) => <CommentCard {...props} />,
  perspective_compare: (props) => <PerspectiveCompare {...props} />,
  synthesis_card: (props) => <SynthesisCard {...props} />,
  news_carousel_card: (props) => <NewsCarouselCard {...props} />,
  pattern_insight: (props) => <PatternInsight {...props} />,
  outro_card: (props) => <OutroCard {...props} />,
  hook_card: (props) => <HookCard {...props} />,
  conflict_card: (props) => <ConflictCard {...props} />,
  turn_card: (props) => <TurnCard {...props} />,
  closing_card: (props) => <ClosingCard {...props} />,
  debate_card: (props) => <DebateCard {...props} />,
  image_card: (props) => <ImageCard {...props} />,
  info_table: (props) => <InfoTable {...props} />,
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
      <AbsoluteFill style={{ backgroundColor: C_BG }} />

      {/* HN 顶部橙色导航条 */}
      <div style={{
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        height: 36,
        backgroundColor: C_HN_ORANGE,
        display: "flex",
        alignItems: "center",
        paddingLeft: 16,
        gap: 12,
        fontFamily: 'Verdana, Geneva, sans-serif',
        fontSize: 13,
        fontWeight: 700,
        color: "#000000",
        zIndex: 100,
      }}>
        <span style={{ fontWeight: 700, letterSpacing: -0.5 }}>YC</span>
        <span style={{ borderLeft: "1px solid #000", paddingLeft: 12 }}>Hacker News</span>
        <span style={{ fontWeight: 400, fontSize: 11, color: C_DIM }}>new | threads | comments | show | ask | jobs</span>
      </div>

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
    <AbsoluteFill style={{ backgroundColor: bgColor || C_BG }}>
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

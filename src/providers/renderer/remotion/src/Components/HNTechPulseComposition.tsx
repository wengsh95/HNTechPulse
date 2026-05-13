/**
 * HNTechPulseComposition —— 主合成组件
 *
 * 遍历所有 segments，按时间线排列，每个 segment 内部渲染其 scene_elements。
 * Remotion 的优势：浏览器原生渲染文字（GPU 加速），并行帧渲染。
 */
import React, { useMemo } from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, Easing, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

import { ScriptProps, SegmentData } from "../types";
import {
  Subtitle,
  ClosingCard,
  CoverCard,
  EventCard,
  AtmosphereCard,
  QuoteCard,
} from "./Elements";
import { ProgressBar } from "./ProgressBar";
import { COLORS, FONTS, FW, LAYOUT, S } from "./design";

type StoryChapter = {
  startTime: number;
  endTime: number;
  title: string;
  category: string;
  index: number;
  total: number;
};

type StoryEvent = {
  startTime: number;
  segmentEndTime: number;
  props: Record<string, unknown>;
};

const STORY_MARKER_TYPES = new Set([
  "event_card",
  "story_header",
  "news_carousel_card",
  "story_scan_card",
]);

const asNumber = (value: unknown): number | undefined => {
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
};

const titleFromProps = (props: Record<string, unknown>): string => {
  return String(
    props.editor_angle
    ?? props.title_cn
    ?? props.story_title
    ?? props.source_title
    ?? ""
  );
};

const collectStoryEvents = (segments: SegmentData[]): StoryEvent[] => {
  const events: StoryEvent[] = [];
  const seen = new Set<string>();

  segments.forEach((seg) => {
    seg.scene_elements.forEach((elem) => {
      if (!STORY_MARKER_TYPES.has(elem.element_type)) return;

      const props = elem.props as Record<string, unknown>;
      const storyIndex = asNumber(props.story_index ?? props.display_index);
      const absoluteStart = seg.start_time + elem.start_time;
      const key = storyIndex !== undefined
        ? `story-${storyIndex}`
        : `time-${absoluteStart.toFixed(3)}`;

      if (seen.has(key)) return;
      seen.add(key);
      events.push({
        startTime: absoluteStart,
        segmentEndTime: seg.end_time,
        props,
      });
    });
  });

  return events.sort((a, b) => a.startTime - b.startTime);
};

/** 元素类型 → React 组件映射 */
const ELEMENT_RENDERERS: Record<
  string,
  React.FC<{ elementProps: Record<string, unknown>; duration: number; width: number; height: number }>
> = {
  closing_card: (props) => <ClosingCard {...props} />,
  cover_card: (props) => <CoverCard {...props} />,
  event_card: (props) => <EventCard {...props} />,
  atmosphere_card: (props) => <AtmosphereCard {...props} />,
  quote_card: (props) => <QuoteCard {...props} />,
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
  const frame = useCurrentFrame();
  const startFrame = Math.floor(segment.start_time * fps);
  const durationFrames = Math.max(1, Math.ceil(segment.duration * fps));
  const segmentDuration = segment.duration;
  const hasTitleLikeCard = segment.scene_elements.some((elem) =>
    elem.element_type === "cover_card" || elem.element_type === "closing_card"
  );
  const subtitleMode = hasTitleLikeCard || segment.segment_type === "opening" || segment.segment_type === "closing"
    ? "minimal"
    : "standard";

  const TRANSITION_FRAMES = 12;
  const segOpacity = interpolate(frame, [0, TRANSITION_FRAMES], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <Sequence
      from={startFrame}
      durationInFrames={durationFrames}
      name={`segment-${index}-${segment.segment_type}`}
      premountFor={Math.min(8, durationFrames)}
    >
      {/* Scene wrapper with transition opacity */}
      <div style={{ ...S, left: 0, top: 0, width: "100%", height: "100%", opacity: segOpacity, pointerEvents: "none" }}>
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
          elementProps={{ text: segment.audio_text, cues: segment.cues, mode: subtitleMode }}
          duration={segmentDuration}
          width={width}
          height={height}
        />
      </div>
    </Sequence>
  );
};

const GlobalChrome: React.FC<{
  dateLabel: string;
  chapters: StoryChapter[];
  startTime: number;
}> = ({ dateLabel, chapters, startTime }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  const activeChapter = chapters.find(
    (chapter) => currentTime >= chapter.startTime && currentTime < chapter.endTime
  );
  const showChapter = Boolean(activeChapter);
  if (currentTime < startTime) {
    return null;
  }

  const opacity = interpolate(currentTime - startTime, [0, 0.5], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        left: LAYOUT.chromeInsetX,
        right: LAYOUT.chromeInsetX,
        top: LAYOUT.chromeTop,
        height: LAYOUT.chromeHeight,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        opacity,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          fontFamily: FONTS.sans,
          color: COLORS.textSecondary,
          fontSize: 15,
          fontWeight: FW.heavy,
          letterSpacing: 0,
        }}
      >
        <span style={{ color: COLORS.text }}>HN TechPulse</span>
        {dateLabel && (
          <>
            <span style={{ color: COLORS.textTertiary }}>/</span>
            <span>{dateLabel}</span>
          </>
        )}
      </div>

      {showChapter && activeChapter && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            height: 30,
            padding: "0 12px",
            borderRadius: 999,
            background: "rgba(0, 122, 255, 0.12)",
            border: "1px solid rgba(0, 122, 255, 0.25)",
            boxShadow: "0 2px 8px rgba(0,0,0,0.30)",
            boxSizing: "border-box",
          }}
        >
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              height: 16,
              fontFamily: FONTS.mono,
              fontSize: 12,
              fontWeight: FW.heavy,
              color: COLORS.accentLight,
              lineHeight: 1,
            }}
          >
            {String(activeChapter.index + 1).padStart(2, "0")}/{String(activeChapter.total).padStart(2, "0")}
          </span>
          {activeChapter.category && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                height: 16,
                fontFamily: FONTS.sans,
                fontSize: 12,
                fontWeight: FW.bold,
                color: COLORS.textSecondary,
                lineHeight: 1,
              }}
            >
              {activeChapter.category}
            </span>
          )}
        </div>
      )}
    </div>
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
  transitionTimes,
}) => {
  const frame = useCurrentFrame();
  const totalDuration = useMemo(
    () => segments.length > 0 ? segments[segments.length - 1].end_time : 0,
    [segments]
  );

  const { storyBoundaries, storyChapters, dateLabel } = useMemo(() => {
    const events = collectStoryEvents(segments);
    const boundaries = events.map((event) => event.startTime);
    const chapters: StoryChapter[] = events.map((event, i) => {
      const index = asNumber(event.props.display_index ?? event.props.story_index) ?? i;
      const total = asNumber(event.props.story_count) ?? events.length;
      return {
        startTime: event.startTime,
        endTime: events[i + 1]?.startTime ?? event.segmentEndTime,
        title: titleFromProps(event.props),
        category: String(event.props.category ?? ""),
        index,
        total,
      };
    });
    const firstTitle = segments
      .flatMap((seg) => seg.scene_elements)
      .find((elem) => elem.element_type === "cover_card");
    const label = firstTitle
      ? String((firstTitle.props as Record<string, unknown>).subtitle ?? "")
      : "";
    return { storyBoundaries: boundaries, storyChapters: chapters, dateLabel: label };
  }, [segments]);
  const currentTime = frame / fps;
  const activeStoryIndex = storyChapters.findIndex((chapter) => {
    return currentTime >= chapter.startTime && currentTime < chapter.endTime;
  });

  return (
    <AbsoluteFill style={{ background: bgColor || COLORS.bg }}>
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

      {/* Per-subtitle 音频轨道 (story_scan 使用) */}
      {segments
        .filter((seg) => seg.subtitle_audios && seg.subtitle_audios.length > 0)
        .flatMap((segment) =>
          (segment.subtitle_audios ?? []).map((sa, i) => ({
            key: `sub-audio-${segment.start_time}-${i}`,
            absoluteStart: segment.start_time + sa.start_time,
            duration: sa.end_time - sa.start_time,
            audioPath: sa.audio_path,
          }))
        )
        .filter((item) => item.duration > 0)
        .map((item) => (
          <Sequence
            key={item.key}
            from={Math.floor(item.absoluteStart * fps)}
            durationInFrames={Math.max(1, Math.ceil(item.duration * fps))}
            layout="none"
          >
            <Audio src={staticFile(item.audioPath)} />
          </Sequence>
        ))}

      {/* 每个 story 切入时的转场音效（从 gap 起点播放，填充段间停顿） */}
      {(transitionTimes ?? storyBoundaries).map((startTime, i) => (
        <Sequence
          key={`transition-${i}`}
          from={Math.floor(startTime * fps)}
          durationInFrames={Math.ceil(1 * fps)}
          layout="none"
        >
          <Audio src={staticFile("double-click-computer-mouse.mp3")} />
        </Sequence>
      ))}

      {/* 底部进度条 */}
      <ProgressBar
        totalDuration={totalDuration}
        storyBoundaries={storyBoundaries}
        activeStoryIndex={activeStoryIndex}
      />
      <GlobalChrome
        dateLabel={dateLabel}
        chapters={storyChapters}
        startTime={segments.find((seg) => seg.segment_type !== "opening")?.start_time ?? 0}
      />
    </AbsoluteFill>
  );
};

/**
 * HNTechPulseComposition —— 主合成组件
 *
 * 遍历所有 segments，按时间线排列，每个 segment 内部渲染其 scene_elements。
 * Remotion 的优势：浏览器原生渲染文字（GPU 加速），并行帧渲染。
 */
import React, { useMemo } from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame } from "remotion";

import { ScriptProps, SegmentData } from "../types";
import { Subtitle, ClosingCard, CoverCard, EventCard, AtmosphereCard } from "./Elements";
import { ProgressBar } from "./ProgressBar";
import { BackgroundAtmosphere } from "./BackgroundAtmosphere";
import { COLORS, ChapterName, ChapterProvider, ELEMENT_TYPE_TO_CHAPTER, S } from "./design";
import { segmentTransitionOpacity } from "./timing";

type StoryChapter = {
  startTime: number;
  endTime: number;
  title: string;
  category: string;
  chapter: ChapterName;
  displayIndex: number;
  total: number;
};

type StoryEvent = {
  startTime: number;
  segmentEndTime: number;
  elementType: string;
  props: Record<string, unknown>;
};

const STORY_MARKER_TYPES = new Set(["event_card"]);

const asNumber = (value: unknown): number | undefined => {
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
};

const titleFromProps = (props: Record<string, unknown>): string => {
  return String(
    props.editor_angle ?? props.title_cn ?? props.story_title ?? props.source_title ?? "",
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
      const key =
        storyIndex !== undefined ? `story-${storyIndex}` : `time-${absoluteStart.toFixed(3)}`;

      if (seen.has(key)) return;
      seen.add(key);
      events.push({
        startTime: absoluteStart,
        segmentEndTime: seg.end_time,
        elementType: elem.element_type,
        props,
      });
    });
  });

  return events.sort((a, b) => a.startTime - b.startTime);
};

/** 元素类型 → React 组件映射 */
const ELEMENT_RENDERERS: Record<
  string,
  React.FC<{
    elementProps: Record<string, unknown>;
    duration: number;
    width: number;
    height: number;
  }>
> = {
  closing_card: (props) => <ClosingCard {...props} />,
  cover_card: (props) => <CoverCard {...props} />,
  event_card: (props) => <EventCard {...props} />,
  atmosphere_card: (props) => <AtmosphereCard {...props} />,
};

/** 卡片元素淡入淡出包装 */
const ElementFadeWrap: React.FC<{
  needsFade: boolean;
  durationFrames: number;
  children: React.ReactNode;
}> = ({ needsFade, durationFrames, children }) => {
  const frame = useCurrentFrame();
  const FADE_FRAMES = 6;
  const opacity = needsFade
    ? interpolate(
        frame,
        [0, FADE_FRAMES, durationFrames - FADE_FRAMES, durationFrames],
        [0, 1, 1, 0],
        { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
      )
    : 1;
  return (
    <div style={{ position: "absolute", inset: 0, opacity, pointerEvents: "none" }}>{children}</div>
  );
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
  /** 额外注入的 props，会与 elem.props merge（用于 story_gap 的 prev/next chapter） */
  extraProps?: Record<string, unknown>;
}> = ({ elem, width, height, fps, extraProps }) => {
  const RendererComponent = ELEMENT_RENDERERS[elem.element_type];
  if (!RendererComponent) {
    console.warn(`[Remotion] Unknown element type: ${elem.element_type}`);
    return null;
  }

  const duration = elem.end_time - elem.start_time;
  if (duration <= 0) return null;

  const startFrame = Math.floor(elem.start_time * fps);
  const durationFrames = Math.max(1, Math.ceil(duration * fps));
  const chapter: ChapterName = ELEMENT_TYPE_TO_CHAPTER[elem.element_type] ?? "focus";
  const mergedProps = extraProps
    ? { ...(elem.props as Record<string, unknown>), ...extraProps }
    : (elem.props as Record<string, unknown>);
  const needsFade = true;

  return (
    <Sequence from={startFrame} durationInFrames={durationFrames} layout="none">
      <ChapterProvider chapter={chapter}>
        <ElementFadeWrap needsFade={needsFade} durationFrames={durationFrames}>
          <RendererComponent
            elementProps={mergedProps}
            duration={duration}
            width={width}
            height={height}
          />
        </ElementFadeWrap>
      </ChapterProvider>
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
  isLastSegment: boolean;
  dateLabel?: string;
}> = ({ segment, index, width, height, fps, isLastSegment, dateLabel }) => {
  const frame = useCurrentFrame();
  const startFrame = Math.floor(segment.start_time * fps);
  const durationFrames = Math.max(1, Math.ceil(segment.duration * fps));
  const segmentDuration = segment.duration;
  const hasTitleLikeCard = segment.scene_elements.some(
    (elem) => elem.element_type === "cover_card" || elem.element_type === "closing_card",
  );
  const subtitleMode =
    hasTitleLikeCard || segment.segment_type === "opening" || segment.segment_type === "closing"
      ? "standard"
      : "standard";

  const TRANSITION_FRAMES = 12;
  const segOpacity = segmentTransitionOpacity({
    absoluteFrame: frame,
    startFrame,
    durationFrames,
    transitionFrames: TRANSITION_FRAMES,
    isLastSegment,
  });

  // 章节上下文 (居中 masthead 标签) — 按 segment_type 派生
  const chapterLabel = (() => {
    if (segment.segment_type === "opening") return "今日封面";
    if (segment.segment_type === "closing") return "今日信号";
    if (segment.segment_type === "story_scan") {
      // 找 segment 第一个 event_card 拿 category / editor_angle
      const firstEvent = segment.scene_elements.find((e) => e.element_type === "event_card");
      const props = (firstEvent?.props ?? {}) as Record<string, unknown>;
      const storyIdx = typeof props.story_index === "number" ? props.story_index : null;
      const displayIdx = typeof props.display_index === "number" ? props.display_index : null;
      const idx = (displayIdx ?? storyIdx ?? 0) + 1;
      const total = typeof props.story_count === "number" ? props.story_count : null;
      const cat = String(props.category ?? "").trim();
      const headline = String(props.editor_angle ?? "").trim();
      // 截断标题到合适长度, 配合 EVENT 01 · 标题
      const short = headline.length > 14 ? headline.slice(0, 13) + "…" : headline;
      const totalPart = total ? ` / ${total}` : "";
      if (cat && short) return `EVENT 0${idx}${totalPart} · ${cat} · ${short}`;
      if (short) return `EVENT 0${idx}${totalPart} · ${short}`;
      return `EVENT 0${idx}${totalPart}`;
    }
    return undefined;
  })();

  return (
    <Sequence
      from={startFrame}
      durationInFrames={durationFrames}
      name={`segment-${index}-${segment.segment_type}`}
      premountFor={Math.min(TRANSITION_FRAMES, durationFrames)}
    >
      {/* Scene wrapper with transition opacity */}
      <div
        style={{
          ...S,
          left: 0,
          top: 0,
          width: "100%",
          height: "100%",
          opacity: segOpacity,
          pointerEvents: "none",
        }}
      >
        {/* 场景元素 */}
        {segment.scene_elements.map((elem, i) => (
          <SceneElementRenderer
            key={`${index}-elem-${i}`}
            elem={elem}
            width={width}
            height={height}
            fps={fps}
            extraProps={{
              audio_path: segment.audio_path,
              dateLabel,
              ...(chapterLabel ? { chapterLabel } : {}),
            }}
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

/** 主 Composition 组件 */
export const HNTechPulseComposition: React.FC<ScriptProps> = ({
  width,
  height,
  fps,
  bgColor,
  segments,
}) => {
  const frame = useCurrentFrame();
  const totalDuration = useMemo(
    () => (segments.length > 0 ? segments[segments.length - 1].end_time : 0),
    [segments],
  );

  const { storyBoundaries, storyChapters, dateLabel } = useMemo(() => {
    const events = collectStoryEvents(segments);
    const boundaries = events.map((event) => event.startTime);
    const chapters: StoryChapter[] = events.map((event, i) => {
      const displayIndex = asNumber(event.props.display_index);
      const storyIndex = asNumber(event.props.story_index);
      const total = asNumber(event.props.story_count) ?? events.length;
      const displayOrdinal =
        displayIndex !== undefined
          ? displayIndex + 1
          : storyIndex !== undefined
            ? storyIndex + 1
            : i + 1;
      return {
        startTime: event.startTime,
        endTime: events[i + 1]?.startTime ?? event.segmentEndTime,
        title: titleFromProps(event.props),
        category: String(event.props.category ?? ""),
        chapter: ELEMENT_TYPE_TO_CHAPTER[event.elementType] ?? "focus",
        displayIndex: displayOrdinal,
        total,
      };
    });
    const firstTitle = segments
      .flatMap((seg) => seg.scene_elements)
      .find((elem) => elem.element_type === "cover_card");
    const firstTitleProps = (firstTitle?.props ?? {}) as Record<string, unknown>;
    // chrome 优先读 date_label (纯日期), fallback 到 subtitle (兼容旧数据)
    const label = String(firstTitleProps.date_label ?? firstTitleProps.subtitle ?? "");
    return { storyBoundaries: boundaries, storyChapters: chapters, dateLabel: label };
  }, [segments]);
  const currentTime = frame / fps;
  const activeStoryIndex = storyChapters.findIndex((chapter) => {
    return currentTime >= chapter.startTime && currentTime < chapter.endTime;
  });

  return (
    <AbsoluteFill style={{ background: bgColor || COLORS.bg }}>
      {/* Background atmosphere: glow spots + micro grid */}
      <BackgroundAtmosphere width={width} height={height} />

      {/* 遍历所有 segments，按时间线排列视觉内容 */}
      {segments.map((segment, index) => (
        <SegmentRenderer
          key={`seg-${index}`}
          segment={segment}
          index={index}
          width={width}
          height={height}
          fps={fps}
          isLastSegment={index === segments.length - 1}
          dateLabel={dateLabel}
        />
      ))}

      {/* 音频轨道：每个音频用绝对定位的 Sequence，与视觉 Segment 严格对齐 */}
      {/* 排除已有 per-subtitle 音频的 story_scan，避免双重播放 */}
      {segments
        .filter(
          (seg) =>
            seg.audio_path &&
            seg.duration > 0 &&
            !(seg.subtitle_audios && seg.subtitle_audios.length > 0),
        )
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
          })),
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

      {/* 底部进度条 */}
      <ProgressBar
        totalDuration={totalDuration}
        storyBoundaries={storyBoundaries}
        activeStoryIndex={activeStoryIndex}
      />
    </AbsoluteFill>
  );
};

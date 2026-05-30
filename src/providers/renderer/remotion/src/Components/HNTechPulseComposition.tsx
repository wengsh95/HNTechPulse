/**
 * HNTechPulseComposition —— 主合成组件
 *
 * 遍历所有 segments，按时间线排列，每个 segment 内部渲染其 scene_elements。
 * Remotion 的优势：浏览器原生渲染文字（GPU 加速），并行帧渲染。
 */
import React, { useMemo } from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  Easing,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import { ScriptProps, SegmentData } from "../types";
import {
  Subtitle,
  ClosingCard,
  CoverCard,
  EventCard,
  AtmosphereCard,
} from "./Elements";
import {
  CommentCard,
  DiscussionOverviewCard,
  NewsCarouselCard,
  OutroCard,
  PatternInsightCard,
  PerspectiveCompareCard,
  StoryHeaderCard,
  SynthesisCard,
} from "./LegacyCards";
import { ProgressBar } from "./ProgressBar";
import { BackgroundAtmosphere } from "./BackgroundAtmosphere";
import {
  CHAPTERS,
  COLORS,
  ChapterName,
  ChapterProvider,
  ELEMENT_TYPE_TO_CHAPTER,
  FONTS,
  FW,
  S,
  useDesign,
} from "./design";
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
  outro_card: (props) => <OutroCard {...props} />,
  cover_card: (props) => <CoverCard {...props} />,
  event_card: (props) => <EventCard {...props} />,
  atmosphere_card: (props) => <AtmosphereCard {...props} />,
  story_header: (props) => <StoryHeaderCard {...props} />,
  discussion_overview: (props) => <DiscussionOverviewCard {...props} />,
  comment_card: (props) => <CommentCard {...props} />,
  perspective_compare: (props) => <PerspectiveCompareCard {...props} />,
  synthesis_card: (props) => <SynthesisCard {...props} />,
  news_carousel_card: (props) => <NewsCarouselCard {...props} />,
  pattern_insight: (props) => <PatternInsightCard {...props} />,
  story_gap: (props) => <StoryGap {...props} />,
};

const StoryGap: React.FC<{
  elementProps: Record<string, unknown>;
  duration: number;
  width: number;
  height: number;
}> = ({ elementProps, duration }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const fadeDur = duration * 0.2;
  const overlayAlpha = interpolate(t, [0, fadeDur, duration - fadeDur, duration], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const prevChapter = elementProps.prev_chapter as ChapterName | undefined;
  const nextChapter = elementProps.next_chapter as ChapterName | undefined;
  // 把 focus 和 atmosphere 视为同一过渡分组（同一 story 内的 event/atmosphere 配对）
  const groupOf = (c: ChapterName | undefined): string | undefined =>
    c === "atmosphere" ? "focus" : c;
  const isCrossChapter = Boolean(
    prevChapter && nextChapter && groupOf(prevChapter) !== groupOf(nextChapter),
  );
  // 同章节：低强度黑闪保持连贯；跨章节：黑闪 + 下章节色细横扫
  const blackAlpha = isCrossChapter ? 0.45 : 0.25;
  const sweepProgress = interpolate(t, [0, duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const sweepOpacity = isCrossChapter
    ? interpolate(sweepProgress, [0, 0.4, 0.7, 1], [0, 0.55, 0.55, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 0;
  const sweepX = interpolate(sweepProgress, [0, 1], [110, -30]); // % from right edge
  const sweepAccent = nextChapter ? CHAPTERS[nextChapter].accent : COLORS.accent;
  return (
    <>
      <Audio src={staticFile("double-click-computer-mouse.mp3")} />
      {/* Black flash */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `rgba(0,0,0,${blackAlpha * overlayAlpha})`,
          pointerEvents: "none",
        }}
      />
      {/* Cross-chapter color sweep */}
      {isCrossChapter && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            overflow: "hidden",
            pointerEvents: "none",
            opacity: sweepOpacity,
          }}
        >
          <div
            style={{
              position: "absolute",
              top: "-10%",
              left: `${sweepX}%`,
              width: "22%",
              height: "120%",
              transform: "skewX(-14deg)",
              background: `linear-gradient(90deg, transparent 0%, ${sweepAccent} 50%, transparent 100%)`,
              filter: "blur(20px)",
            }}
          />
        </div>
      )}
    </>
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

  return (
    <Sequence from={startFrame} durationInFrames={durationFrames} layout="none">
      <ChapterProvider chapter={chapter}>
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
            elementProps={mergedProps}
            duration={duration}
            width={width}
            height={height}
          />
        </div>
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
}> = ({ segment, index, width, height, fps, isLastSegment }) => {
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
        {segment.scene_elements.map((elem, i) => {
          let extraProps: Record<string, unknown> | undefined;
          if (elem.element_type === "story_gap") {
            // Find nearest non-gap neighbor on each side to determine chapter transition.
            // event_card → atmosphere_card 不被视为跨章节（属于同一 story 的两段），
            // 因此遇到 atmosphere_card 时继续向前找它对应的 event_card 章节。
            const lookupChapter = (start: number, dir: -1 | 1): ChapterName | undefined => {
              for (let j = start; j >= 0 && j < segment.scene_elements.length; j += dir) {
                const t = segment.scene_elements[j].element_type;
                if (t === "story_gap") continue;
                return ELEMENT_TYPE_TO_CHAPTER[t];
              }
              return undefined;
            };
            const prevChapter = lookupChapter(i - 1, -1);
            const nextChapter = lookupChapter(i + 1, 1);
            extraProps = {
              prev_chapter: prevChapter,
              next_chapter: nextChapter,
            };
          }
          return (
            <SceneElementRenderer
              key={`${index}-elem-${i}`}
              elem={elem}
              width={width}
              height={height}
              fps={fps}
              extraProps={{
                ...extraProps,
                audio_path: segment.audio_path,
              }}
            />
          );
        })}

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
  startTime: number;
}> = ({ dateLabel, startTime }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { layout, fs, scaled } = useDesign();
  const currentTime = frame / fps;

  if (currentTime < startTime) {
    return null;
  }

  const opacity = interpolate(currentTime - startTime, [0, 0.5], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const chromeH = layout.chromeHeight;

  return (
    <div
      style={{
        position: "absolute",
        left: layout.chromeInsetX,
        right: layout.chromeInsetX,
        top: layout.chromeTop,
        height: chromeH,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        opacity,
        pointerEvents: "none",
        zIndex: 10,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: scaled(10),
          fontFamily: FONTS.sans,
          color: COLORS.muted,
          fontSize: fs.bodySmall,
          fontWeight: FW.heavy,
          letterSpacing: 0,
        }}
      >
        <span style={{ color: COLORS.text }}>HN每日观察</span>
        {dateLabel && (
          <>
            <span style={{ color: COLORS.dim }}>/</span>
            <span>{dateLabel}</span>
          </>
        )}
      </div>

      {/* Chapter pill removed per user request */}
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
      <GlobalChrome dateLabel={dateLabel} startTime={0} />
    </AbsoluteFill>
  );
};

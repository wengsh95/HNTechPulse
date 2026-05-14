/**
 * Remotion 渲染器类型定义
 *
 * 这些类型与 Python 端的 Script/ScriptSegment/SceneElement 对应，
 * 通过 JSON 序列化在 Python→Remotion 之间传递。
 */

/** 单个场景元素（对应 Python SceneElement） */
export interface SceneElementData {
  element_type: string;
  start_time: number; // 秒
  end_time: number; // 秒
  props: Record<string, unknown>;
}

/** 单个字幕提示（对应 Python Cue） */
export interface CueData {
  text: string;
  start_time: number; // 秒（相对于 segment 起始）
  end_time: number; // 秒（相对于 segment 起始）
}

/** 单条字幕音频（用于 per-subtitle TTS 模式） */
export interface SubtitleAudioData {
  audio_path: string; // 音频文件名（相对于 public/ 目录）
  start_time: number; // 秒（相对于 segment 起始）
  end_time: number; // 秒（相对于 segment 起始）
}

/** 单个 Segment（对应 Python ScriptSegment） */
export interface SegmentData {
  segment_type: string; // "opening" | "deep_dive" | "medium_dive" | "quick_news" | "quick_briefs" | "context" | "viewpoint_a" | "viewpoint_b" | "comment_deep" | "synthesis" | "closing"
  audio_text: string;
  cues: CueData[]; // 按时间拆分的字幕提示
  duration: number; // 实际时长（秒）
  start_time: number; // 在时间线上的绝对起始位置（秒）
  end_time: number; // 在时间线上的绝对结束位置（秒）
  audio_path?: string; // TTS 音频文件路径（相对于 audioDir 或绝对路径）
  subtitle_audios?: SubtitleAudioData[]; // per-subtitle 音频（story_scan 使用）
  scene_elements: SceneElementData[];
}

/** 完整脚本 Props（Python Script → JSON → Remotion Props） */
export interface ScriptProps {
  width: number;
  height: number;
  fps: number;
  bgColor: string;
  title: string;
  totalDuration: number; // 总时长（秒）
  segments: SegmentData[];
  audioDir: string; // 音频文件根目录
  transitionTimes?: number[]; // 每个 story 的转场音效起始时间（秒）
}

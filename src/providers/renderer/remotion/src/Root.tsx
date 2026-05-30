import React from "react";
import { Composition } from "remotion";

import { HNTechPulseComposition } from "./Components/HNTechPulseComposition";
import { CoverThumbnail } from "./Components/CoverThumbnail";
import { ScriptProps } from "./types";

/**
 * Remotion 根组件 —— 注册 Composition
 *
 * Remotion v4 架构要点：
 * 1. registerRoot 返回一个接收 props 的函数组件
 * 2. 该组件直接返回 <Composition>，由 Remotion 自动注入 props
 * 3. calculateMetadata 动态计算视频总时长（Studio 和 CLI 都会调用）
 * 4. defaultProps 提供备用值（CLI 模式下被 --props 覆盖）
 *
 * Studio 预览模式：Remotion 会调用 calculateMetadata，可在其中访问完整 props
 * CLI 渲染模式：通过 --props 参数注入完整数据，Remotion 自动传递给组件
 */

/** Validate and extract ScriptProps from raw props */
function validateScriptProps(props: Record<string, unknown>): ScriptProps {
  const segments = Array.isArray(props.segments) ? props.segments : [];
  return {
    width: typeof props.width === "number" ? props.width : 1920,
    height: typeof props.height === "number" ? props.height : 1080,
    fps: typeof props.fps === "number" ? props.fps : 24,
    bgColor: typeof props.bgColor === "string" ? props.bgColor : "#fefcf8",
    title: typeof props.title === "string" ? props.title : "",
    totalDuration: typeof props.totalDuration === "number" ? props.totalDuration : 0,
    segments,
    audioDir: typeof props.audioDir === "string" ? props.audioDir : "",
  };
}

/** calculateMetadata：根据 props 动态计算分辨率、总帧数 */
const calcMeta = async ({ props }: { props: Record<string, unknown> }) => {
  const p = validateScriptProps(props);
  const fps = p.fps;
  const totalDuration =
    p.totalDuration || p.segments.reduce((sum: number, seg) => sum + (seg.duration ?? 0), 0) || 10;

  return {
    durationInFrames: Math.ceil(totalDuration * fps),
    width: p.width,
    height: p.height,
    props,
  };
};

/** 默认 props（CLI 模式下被 --props 覆盖，Studio 模式下被 calculateMetadata 返回的 props 覆盖） */
const defaultProps: ScriptProps = {
  width: 1920,
  height: 1080,
  fps: 24,
  bgColor: "#fefcf8",
  title: "",
  totalDuration: 10,
  segments: [],
  audioDir: "",
};

/** Wrapper that validates raw props before passing to HNTechPulseComposition */
const ValidatedComposition: React.FC<Record<string, unknown>> = (rawProps) => {
  const props = validateScriptProps(rawProps);
  return <HNTechPulseComposition {...props} />;
};

/** 根组件：Remotion registerRoot 要求无参数函数组件，props 通过 Composition 机制传递 */
export const Root: React.FC = () => {
  return (
    <>
      <Composition
        id="HNTechPulseComposition"
        component={ValidatedComposition}
        durationInFrames={240}
        fps={24}
        width={1920}
        height={1080}
        defaultProps={defaultProps}
        calculateMetadata={calcMeta}
      />
      <Composition
        id="CoverThumbnail"
        component={CoverThumbnail}
        durationInFrames={1}
        fps={24}
        width={1920}
        height={1080}
        defaultProps={{
          backgroundImage: "cover_test.png",
          title: "开源、隐私、和一行没写的代码",
          subtitle: "Liquid AI 发布 1.5B MoE 模型，但许可证争议不断",
          dateLabel: "2026-05-31",
        }}
      />
    </>
  );
};

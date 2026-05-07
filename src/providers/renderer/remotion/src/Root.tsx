import React from "react";
import { Composition } from "remotion";

import { HNTechPulseComposition } from "./Components/HNTechPulseComposition";
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

/** calculateMetadata：根据所有 segment 的时长动态计算总帧数 */
const calcMeta = async ({ props }: { props: ScriptProps }) => {
  const fps = props.fps ?? 24;
  const totalDuration =
    props.totalDuration
    || (props.segments ?? []).reduce((sum, seg) => sum + (seg.duration ?? 0), 0)
    || 10;

  return {
    durationInFrames: Math.ceil(totalDuration * fps),
    props,
  };
};

/** 默认 props（CLI 模式下被 --props 覆盖，Studio 模式下被 calculateMetadata 返回的 props 覆盖） */
const defaultProps: ScriptProps = {
  width: 1280,
  height: 720,
  fps: 24,
  bgColor: "#0d1117",
  title: "",
  totalDuration: 10,
  segments: [],
  audioDir: "",
};

/** 根组件：Remotion registerRoot 要求无参数函数组件，props 通过 Composition 机制传递 */
export const Root: React.FC = () => {
  return (
    <Composition
      id="HNTechPulseComposition"
      component={HNTechPulseComposition}
      durationInFrames={240}
      fps={24}
      width={1280}
      height={720}
      defaultProps={defaultProps}
      calculateMetadata={calcMeta}
    />
  );
};

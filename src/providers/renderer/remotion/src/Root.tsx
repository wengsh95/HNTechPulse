import React from "react";
import { cancelRender, Composition, continueRender, delayRender, staticFile } from "remotion";

import { HNTechPulseComposition } from "./Components/HNTechPulseComposition";
import { CoverThumbnail } from "./Components/CoverThumbnail";
import { CardShellDemo } from "./Components/CardShellDemo";
import { VIDEO_DEFAULTS } from "./Components/design";
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

// ── 字体本地化加载 ────────────────────────────────────────────────────────
// 字体源文件在 assets/fonts/，由 prepare_render 复制到
// data/{month}/{date}/render/remotion/public/fonts/，再通过 staticFile("fonts/...")
// 取到 URL。使用 delayRender 阻塞抓帧，直到所有字体就绪——绝不允许悄悄
// 回退到 Georgia / 宋体等系统字体（那是旧版 @import 异步加载的根因）。
//
// family 字符串必须与 tokens.ts 的 FONTS 字体栈完全一致。
// Fraunces / JetBrains Mono 是 variable font，单个 woff2 覆盖整段 weight 范围。
type FontDef = { family: string; weight: string; file: string };
const FONT_FILES: FontDef[] = [
  { family: "Fraunces", weight: "500 900", file: "fonts/Fraunces-VF-latin.woff2" },
  { family: "JetBrains Mono", weight: "500 700", file: "fonts/JetBrainsMono-VF-latin.woff2" },
  { family: "Noto Sans SC", weight: "400", file: "fonts/NotoSansSC-Regular.woff2" },
  { family: "Noto Sans SC", weight: "700", file: "fonts/NotoSansSC-Bold.woff2" },
  { family: "Noto Serif SC", weight: "400", file: "fonts/NotoSerifSC-Regular.woff2" },
  { family: "Noto Serif SC", weight: "700", file: "fonts/NotoSerifSC-Bold.woff2" },
];

const fontHandle = delayRender("loading-fonts");
(async () => {
  try {
    await Promise.all(
      FONT_FILES.map(async ({ family, weight, file }) => {
        const face = new FontFace(family, `url(${staticFile(file)}) format('woff2')`, {
          weight,
          style: "normal",
          display: "block",
        });
        await face.load();
        document.fonts.add(face);
      }),
    );
    continueRender(fontHandle);
  } catch (err) {
    cancelRender(err instanceof Error ? err : new Error(String(err)));
  }
})();

/** Validate and extract ScriptProps from raw props */
function validateScriptProps(props: Record<string, unknown>): ScriptProps {
  const segments = Array.isArray(props.segments) ? props.segments : [];
  return {
    width: typeof props.width === "number" ? props.width : VIDEO_DEFAULTS.width,
    height: typeof props.height === "number" ? props.height : VIDEO_DEFAULTS.height,
    fps: typeof props.fps === "number" ? props.fps : VIDEO_DEFAULTS.fps,
    bgColor: typeof props.bgColor === "string" ? props.bgColor : VIDEO_DEFAULTS.bgColor,
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
    p.totalDuration ||
    p.segments.reduce((sum: number, seg) => sum + (seg.duration ?? 0), 0) ||
    VIDEO_DEFAULTS.fallbackDurationSeconds;

  return {
    durationInFrames: Math.ceil(totalDuration * fps),
    width: p.width,
    height: p.height,
    props,
  };
};

/** 默认 props（CLI 模式下被 --props 覆盖，Studio 模式下被 calculateMetadata 返回的 props 覆盖） */
const defaultProps: ScriptProps = {
  width: VIDEO_DEFAULTS.width,
  height: VIDEO_DEFAULTS.height,
  fps: VIDEO_DEFAULTS.fps,
  bgColor: VIDEO_DEFAULTS.bgColor,
  title: "",
  totalDuration: VIDEO_DEFAULTS.fallbackDurationSeconds,
  segments: [],
  audioDir: "",
};

/** Wrapper that validates raw props before passing to HNTechPulseComposition */
const ValidatedComposition: React.FC<Record<string, unknown>> = (rawProps) => {
  const props = validateScriptProps(rawProps);
  return <HNTechPulseComposition {...props} />;
};

/**
 * Remotion v4 要求 Composition.component 接受 `Record<string, unknown>` 类型,
 * 而我们的具体组件 (CoverThumbnail / CardShellDemo) 都有强类型 props.
 * 这里用最小包装层把强类型组件适配成宽类型, 既保类型安全又不影响运行时.
 */
const CoverThumbnailWrapper: React.FC<Record<string, unknown>> = (rawProps) => {
  return (
    <CoverThumbnail {...(rawProps as unknown as React.ComponentProps<typeof CoverThumbnail>)} />
  );
};

const CardShellDemoWrapper: React.FC<Record<string, unknown>> = (rawProps) => {
  return <CardShellDemo {...(rawProps as unknown as React.ComponentProps<typeof CardShellDemo>)} />;
};

/** 根组件：Remotion registerRoot 要求无参数函数组件，props 通过 Composition 机制传递 */
export const Root: React.FC = () => {
  return (
    <>
      <Composition
        id="HNTechPulseComposition"
        component={ValidatedComposition}
        durationInFrames={VIDEO_DEFAULTS.durationInFrames}
        fps={VIDEO_DEFAULTS.fps}
        width={VIDEO_DEFAULTS.width}
        height={VIDEO_DEFAULTS.height}
        defaultProps={defaultProps}
        calculateMetadata={calcMeta}
      />
      <Composition
        id="CoverThumbnail"
        component={CoverThumbnailWrapper}
        durationInFrames={VIDEO_DEFAULTS.stillDurationInFrames}
        fps={VIDEO_DEFAULTS.fps}
        width={VIDEO_DEFAULTS.width}
        height={VIDEO_DEFAULTS.height}
        defaultProps={{
          backgroundImage: "cover_test.png",
          title: "开源、隐私、和一行没写的代码",
          subtitle: "Liquid AI 发布 1.5B MoE 模型，但许可证争议不断",
          dateLabel: "2026-05-31",
        }}
      />
      <Composition
        id="CardShellDemo-Fill"
        component={CardShellDemoWrapper}
        durationInFrames={VIDEO_DEFAULTS.demoDurationInFrames}
        fps={VIDEO_DEFAULTS.fps}
        width={VIDEO_DEFAULTS.width}
        height={VIDEO_DEFAULTS.height}
        defaultProps={{
          mode: "start",
          title: "今日回顾 · 2026-06-02",
          itemCount: 6,
        }}
      />
      <Composition
        id="CardShellDemo-Center"
        component={CardShellDemoWrapper}
        durationInFrames={VIDEO_DEFAULTS.demoDurationInFrames}
        fps={VIDEO_DEFAULTS.fps}
        width={VIDEO_DEFAULTS.width}
        height={VIDEO_DEFAULTS.height}
        defaultProps={{
          mode: "center",
          title: "今日回顾 · 2026-06-02",
          itemCount: 1,
        }}
      />
      <Composition
        id="CardShellDemo-Evenly"
        component={CardShellDemoWrapper}
        durationInFrames={VIDEO_DEFAULTS.demoDurationInFrames}
        fps={VIDEO_DEFAULTS.fps}
        width={VIDEO_DEFAULTS.width}
        height={VIDEO_DEFAULTS.height}
        defaultProps={{
          mode: "evenly",
          title: "今日回顾 · 2026-06-02",
          itemCount: 3,
        }}
      />
    </>
  );
};

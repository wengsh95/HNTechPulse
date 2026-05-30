/* ================================================================
   StaticRemotionProvider — 提供 Remotion hook 上下文，
   使卡片组件可以在 Player / Studio 之外独立静态渲染。

   卡片组件依赖的 hooks:
     useVideoConfig()  → 由 CompositionManager context 提供
     useCurrentFrame() → 由 TimelineContext 提供
     staticFile()      → 不依赖 context，直接返回路径

   通过 Internals.RemotionContextProvider 一次注入所有上下文。
   ================================================================ */

import React from "react";
import { Internals } from "remotion";

interface StaticRemotionProviderProps {
  /** 静态帧号（默认 35，此时所有进场动画已完成） */
  frame?: number;
  width?: number;
  height?: number;
  fps?: number;
  children: React.ReactNode;
}

/**
 * 提供完整的 Remotion 运行时上下文，用于卡片静态预览。
 * 包装了 CompositionManager / TimelineContext / CanUseRemotionHooks 等。
 */
export const StaticRemotionProvider: React.FC<StaticRemotionProviderProps> = ({
  frame = 35,
  width = 1920,
  height = 1080,
  fps = 24,
  children,
}) => {
  // Remotion 内部类型频繁变化，用 as any 绕过以保证兼容性
  const compositionContextValue = React.useMemo(
    () =>
      ({
        compositions: [
          {
            id: "static-preview",
            width,
            height,
            fps,
            durationInFrames: 300,
            defaultProps: {},
            calculateMetadata: null,
            component: (() => null) as unknown as React.ComponentType<unknown>,
            schema: null,
            folderName: null as string | null,
            parentFolderName: null as string | null,
            nonce: 0,
            stack: null,
          },
        ],
        canvasContent: {
          type: "composition" as const,
          compositionId: "static-preview",
        },
        currentCompositionMetadata: null,
        folders: [],
        setCanvasContent: () => {},
        setCompositions: () => {},
        setCurrentCompositionMetadata: () => {},
      }) as any,
    [width, height, fps],
  );

  const timelineContextValue = React.useMemo(
    () =>
      ({
        frame: { "static-preview": frame },
        playing: false,
        playbackRate: 1,
        imperativePlaying: { current: false },
        setFrame: () => {},
        setPlaying: () => {},
        setPlaybackRate: () => {},
        setImperativePlaying: () => {},
        rootId: "static-preview",
        audioAndVideoTags: { current: [] },
      }) as any,
    [frame],
  );

  const setTimelineContextValue = React.useMemo(
    () =>
      ({
        setTimelineState: () => {},
        setHasFiredDelayedRender: () => {},
        setFrame: () => {},
        setPlaying: () => {},
      }) as any,
    [],
  );

  return (
    <Internals.CanUseRemotionHooksProvider>
      <Internals.IsPlayerContextProvider>
        <Internals.CompositionManager.Provider value={compositionContextValue}>
          <Internals.TimelineContext.Provider value={timelineContextValue}>
            <Internals.SetTimelineContext.Provider value={setTimelineContextValue}>
              <div
                style={{
                  width: "100%",
                  aspectRatio: `${width}/${height}`,
                  position: "relative",
                  overflow: "hidden",
                  background: "#fefcf8",
                }}
              >
                {children}
              </div>
            </Internals.SetTimelineContext.Provider>
          </Internals.TimelineContext.Provider>
        </Internals.CompositionManager.Provider>
      </Internals.IsPlayerContextProvider>
    </Internals.CanUseRemotionHooksProvider>
  );
};

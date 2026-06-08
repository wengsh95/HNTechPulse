/* ================================================================
   CardShell — 三段式自适应卡片骨架

   灵感来源: any2html 的 .export-card 三段式布局 (header / content / footer)
   适配到 Remotion:
     - 显式声明三个 slot (header / children / footer)
     - children 区域根据 justify 自动对齐 (fill/center/evenly)
     - footer 始终通过 mt-auto 推到底部
     - chrome (顶部条 / 波形 / 页码) 内建, 全部 opt-in
     - 严格对称 gutter (左=右), 避免各卡各调

   用法对比:
     旧: <div style={{ flex: 1, justifyContent: "center" }}>...</div>
     新: <CardShell justify="center">{...}</CardShell>
   ================================================================ */

import React from "react";
import { useCurrentFrame, interpolate } from "remotion";
import type { ElementProps } from "./utils";
import { CardAudioWaveform } from "./CardAudioWaveform";
import {
  COLORS,
  CARD_REF,
  useDesign,
  FONTS,
  FW,
  CARD_LAYOUT,
  EASE_CARD,
  ANIM,
  SHADOWS,
  SURFACES,
  COMMON_LAYOUT,
  GRADIENTS,
} from "./design";

/** 内容区域在子 slot 内的垂直对齐方式 */
export type ContentJustify =
  | "start" // 内容从顶部开始, 多余空间留在底部 (默认)
  | "center" // 内容垂直居中, 适合内容少的卡片
  | "end" // 内容靠底, 适合有大 header 的卡片
  | "between" // 首尾贴边, 中间均分 (2-3 块时)
  | "evenly"; // 所有间隙等距 (含上下边距)

export interface CardShellProps {
  elementProps: ElementProps["elementProps"];

  /** 顶部 slot (品牌 mark / 章节标签 / 任意) */
  header?: React.ReactNode;
  /** 中间主内容 (核心) */
  children: React.ReactNode;
  /** 底部 slot (页码 / 落款 / 任意) — 自动 mt-auto 推到底 */
  footer?: React.ReactNode;

  /** 内容在 children 区域的垂直对齐 */
  justify?: ContentJustify;
  /** 内容区主轴方向 */
  direction?: "column" | "row";

  /** 严格对称的左右内边距 (px, 运行时缩放) — 优先级低于单独指定 */
  gutter?: number;
  /** 上下内边距 (px, 运行时缩放) */
  paddingTop?: number;
  paddingBottom?: number;
  /** 个别覆盖 (不推荐, 会破坏对称) */
  paddingLeft?: number;
  paddingRight?: number;

  /** 卡片内的最大内容宽度, 防止长文本撑爆 */
  contentMaxWidth?: number;

  // ── Chrome (顶部条 / 波形 / 页码, 全部 opt-in) ──
  showTopBar?: boolean;
  showWatermark?: boolean;
  showWaveform?: boolean;
  pageIndex?: number;
  totalPages?: number;

  /**
   * 章节上下文 (居中显示在 masthead 中间), 用于平衡左右视觉重量.
   * 推荐: cover="今日封面", event="EVENT 0X · 标题缩写", atmosphere="讨论".
   * 不传则居中区不渲染.
   */
  chapterLabel?: string;

  /**
   * 字幕总是显示 (HNTechPulseComposition 强制 standard mode).
   * 设为 true 时, content 区域底部会自动预留 subtitleBottom + 安全余量,
   * 避免卡片内容被底部字幕挡住.
   * 已经在内容里手动避开字幕的卡 (如 cover 头图、closing 大字) 应传 true.
   */
  reserveSubtitle?: boolean;

  /** 整体外层覆盖 */
  style?: React.CSSProperties;
  /** 内层 content 区域覆盖 */
  contentStyle?: React.CSSProperties;
}

/** justify → CSS justify-content 映射 */
const JUSTIFY_MAP: Record<ContentJustify, React.CSSProperties["justifyContent"]> = {
  start: "flex-start",
  center: "center",
  end: "flex-end",
  between: "space-between",
  evenly: "space-evenly",
};

export const CardShell: React.FC<CardShellProps> = ({
  elementProps,
  header,
  children,
  footer,
  justify = "start",
  direction = "column",
  gutter,
  paddingTop,
  paddingBottom,
  paddingLeft,
  paddingRight,
  contentMaxWidth: _contentMaxWidth,
  showTopBar = true,
  showWatermark = false,
  showWaveform = true,
  pageIndex = 0,
  totalPages = 0,
  reserveSubtitle = false,
  chapterLabel,
  style,
  contentStyle,
}) => {
  const frame = useCurrentFrame();
  const d = useDesign();

  // Padding 解析: 优先级 individual > gutter > CARD_LAYOUT.padding
  const pTop = d.scaled(paddingTop ?? CARD_LAYOUT.padding.top);
  const pBottom = d.scaled(paddingBottom ?? CARD_LAYOUT.padding.bottom);
  // 对称 gutter 是首选, 单边覆盖是 escape hatch
  const pLeft = d.scaled(paddingLeft ?? gutter ?? CARD_LAYOUT.padding.left);
  const pRight = d.scaled(paddingRight ?? gutter ?? CARD_LAYOUT.padding.right);

  // 整体卡片淡入
  const cardProgress = interpolate(frame, [ANIM.cardStart, ANIM.cardEnd], [0, 1], {
    easing: EASE_CARD,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const cardY = interpolate(cardProgress, [0, 1], [COMMON_LAYOUT.riseLarge, 0]);

  const dateStr = String(elementProps?.dateLabel ?? "");
  // chapterLabel 优先从 prop 读, fallback 从 elementProps 读 (SegmentRenderer 通过 extraProps 注入)
  const finalChapterLabel =
    chapterLabel ??
    String((elementProps as Record<string, unknown> | undefined)?.chapterLabel ?? "");

  return (
    <div
      style={{
        width: d.scaled(CARD_REF.width),
        height: "100%",
        position: "relative",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        // 对齐模板 .card: gradient overlay + bg color
        background: `linear-gradient(180deg, rgba(255,255,255,0.58), transparent 34%), ${COLORS.bg}`,
        borderRadius: d.scaled(CARD_LAYOUT.shell.radius),
        boxShadow: SHADOWS.card,
        opacity: cardProgress,
        transform: `translateY(${cardY}px)`,
        ...style,
      }}
    >
      {/* 卡片边框 (对齐模板 card::before) */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          border: SURFACES.cardBorder,
          borderRadius: "inherit",
          pointerEvents: "none",
          zIndex: 1,
        }}
      />

      {/* HN橙色渐变底部分割线 (对齐模板 card::after) */}
      <div
        style={{
          position: "absolute",
          left: pLeft,
          right: pRight,
          bottom: d.scaled(CARD_LAYOUT.shell.dividerBottom),
          height: d.scaled(CARD_LAYOUT.divider.height),
          background: GRADIENTS.divider,
          opacity: 0.55,
          pointerEvents: "none",
          zIndex: 1,
        }}
      />

      {/* pulse-dot keyframes */}
      <style>{`
        @keyframes hn-pulse-dot {
          0%, 100% { opacity: 0.36; transform: scale(1); }
          50% { opacity: 1; transform: scale(1.35); }
        }
      `}</style>
      {/* ── Chrome: 顶部 masthead (brand-strip 风格 — 对齐模板) ── */}
      {showTopBar && (
        <div
          style={{
            position: "absolute",
            top: d.scaled(CARD_LAYOUT.shell.topBarTop),
            left: pLeft,
            right: pRight,
            display: "flex",
            alignItems: "center",
            gap: d.scaled(CARD_LAYOUT.shell.dateGap),
            zIndex: 10, // above border overlay (z-index: 1)
            fontFamily: FONTS.mono,
            fontSize: d.fs.textXs,
            color: COLORS.muted,
            letterSpacing: "0.04em",
          }}
        >
          {/* live-dot + 品牌名 */}
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: d.scaled(CARD_LAYOUT.shell.brandGap),
              fontFamily: FONTS.mono,
              fontSize: d.fs.textSm,
              fontWeight: FW.bold,
              color: COLORS.fg,
            }}
          >
            <span
              style={{
                width: d.scaled(CARD_LAYOUT.shell.liveDotSize),
                height: d.scaled(CARD_LAYOUT.shell.liveDotSize),
                borderRadius: COMMON_LAYOUT.circleRadius,
                background: COLORS.brand,
                display: "inline-block",
                flexShrink: 0,
                animation: `hn-pulse-dot 1.8s ease-in-out 3 both`,
              }}
            />
            HN TechPulse
          </span>

          {/* "/" 分隔符 + 日期 */}
          {dateStr && (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: d.scaled(CARD_LAYOUT.shell.dateGap),
                color: COLORS.muted,
              }}
            >
              <span style={{ color: COLORS.inkFaint }}>/</span>
              {dateStr}
            </span>
          )}
        </div>
      )}

      {/* ── 居中: 章节上下文胶囊 (双层边框 + 暖棕点 + 衬线微标) ── */}
      {/* 已停用: 用户希望 header 保持极简, 不显示中央胶囊 */}
      {false && finalChapterLabel && (
        <div
          style={{
            position: "absolute",
            top: d.scaled(CARD_LAYOUT.shell.chapterLabelTop),
            left: "50%",
            transform: "translateX(-50%)",
            display: "flex",
            alignItems: "center",
            gap: d.scaled(CARD_LAYOUT.shell.chapterLabelGap),
            maxWidth: d.scaled(CARD_LAYOUT.shell.chapterLabelMaxWidth),
            padding: `${d.scaled(CARD_LAYOUT.shell.chapterLabelPaddingY)}px ${d.scaled(CARD_LAYOUT.shell.chapterLabelPaddingX)}px`,
            background: COLORS.surface,
            border: `1px solid ${COLORS.border}`,
            borderRadius: d.scaled(COMMON_LAYOUT.pillRadius),
            boxShadow: `0 1px 0 ${COLORS.surface} inset, 0 2px 6px ${COLORS.brand}11`,
            whiteSpace: "nowrap" as const,
            overflow: "hidden",
            zIndex: 11,
          }}
        >
          <span
            style={{
              width: d.scaled(CARD_LAYOUT.shell.chapterLabelDotSize),
              height: d.scaled(CARD_LAYOUT.shell.chapterLabelDotSize),
              borderRadius: "50%",
              background: COLORS.brand,
              boxShadow: `0 0 0 2px ${COLORS.brand}22`,
              flexShrink: 0,
            }}
          />
          <span
            style={{
              fontFamily: FONTS.serif,
              fontSize: d.fs.textXs,
              fontWeight: FW.bold,
              color: COLORS.brand,
              letterSpacing: "0.12em",
              textTransform: "uppercase" as const,
            }}
          >
            {finalChapterLabel}
          </span>
          <span
            style={{
              fontFamily: FONTS.mono,
              fontSize: d.fs.textXs,
              color: COLORS.brand,
              opacity: 0.6,
            }}
          >
            ↗
          </span>
        </div>
      )}

      {/* ── Chrome: 页码水印 ── */}
      {showWatermark && totalPages > 0 && (
        <div
          style={{
            position: "absolute",
            top: d.scaled(CARD_LAYOUT.watermark.top),
            right: d.scaled(CARD_LAYOUT.watermark.right),
            fontFamily: FONTS.mono,
            fontSize: d.fs.text6xl,
            fontWeight: FW.heavy,
            color: COLORS.dim,
            letterSpacing: "0.1em",
            zIndex: 5,
          }}
        >
          {pageIndex + 1} / {totalPages}
        </div>
      )}

      {/* ── Header slot (shrink-0) ── */}
      {header && (
        <div
          style={{
            flexShrink: 0,
            padding: `${d.scaled(CARD_LAYOUT.shell.headerSlotTop)}px ${pRight}px 0 ${pLeft}px`,
            ...(direction === "row" ? { display: "flex", flexDirection: "row" } : {}),
          }}
        >
          {header}
        </div>
      )}

      {/* ── Content slot (flex: 1, auto-aligned) ── */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          padding: (() => {
            // 顶部 padding: 有 header 让位 / 否则用 pTop
            const top = header
              ? d.scaled(CARD_LAYOUT.shell.headerContentTop)
              : pTop + (showTopBar ? d.scaled(CARD_LAYOUT.header.height + 18) : 0);
            // 底部 padding: 字幕总是显示, 给字幕让位 (除非 footer 自己会占满)
            // 字幕布局: bottom = subtitleBottom(100) + 8, 高度 ~50, 边距 ~12
            // 总共约 130-150px. 这里用 150 保证安全.
            const bottomReserve =
              reserveSubtitle && !footer
                ? Math.max(pBottom, d.scaled(CARD_LAYOUT.shell.subtitleReserve))
                : pBottom;
            return `${top}px ${pRight}px ${bottomReserve}px ${pLeft}px`;
          })(),
          display: "flex",
          flexDirection: direction,
          justifyContent: JUSTIFY_MAP[justify],
          alignItems: direction === "row" ? "stretch" : "stretch",
          gap: d.scaled(CARD_LAYOUT.shell.contentGap),
          position: "relative",
          maxWidth: "100%",
          ...contentStyle,
        }}
      >
        {children}
      </div>

      {/* ── Footer slot (mt-auto) ── */}
      {footer && (
        <div
          style={{
            marginTop: "auto", // ← 关键: 任何剩余空间都堆在 footer 上面
            flexShrink: 0,
            padding: `${d.scaled(CARD_LAYOUT.shell.footerTop)}px ${pRight}px ${pBottom}px ${pLeft}px`,
          }}
        >
          {footer}
        </div>
      )}

      {/* ── Chrome: 底部波形 (无 footer 时也独立) ── */}
      {showWaveform && !footer && (
        <div
          style={{
            position: "absolute",
            bottom: d.scaled(CARD_LAYOUT.waveform.bottom),
            left: 0,
            right: 0,
            display: "flex",
            justifyContent: "center",
          }}
        >
          <CardAudioWaveform src={elementProps?.audio_path as string | undefined} />
        </div>
      )}
    </div>
  );
};

/* ================================================================
   辅助组件: 内容分组容器 (不抢 flex 空间)
   关键: 不要 flex:1, 让 CardShell.contentArea 的 justifyContent 起作用
   ================================================================ */

export interface ContentFillProps {
  children: React.ReactNode;
  direction?: "column" | "row";
  gap?: number;
  maxWidth?: number;
  style?: React.CSSProperties;
}

/**
 * 内容分组容器 — 不会撑满父级, 仅控制子元素排列
 * 这是 CardShell 的推荐用法, 配合 justify="start|center|end|between|evenly" 一起工作
 */
export const Fill: React.FC<ContentFillProps> = ({
  children,
  direction = "column",
  gap = COMMON_LAYOUT.contentGap,
  maxWidth,
  style,
}) => {
  const d = useDesign();
  return (
    <div
      style={{
        display: "flex",
        flexDirection: direction,
        gap: d.scaled(gap),
        maxWidth: maxWidth ? d.scaled(maxWidth) : undefined,
        // 故意不加 flex: 1 — 留给父级 CardShell 的 justifyContent 分配空间
        ...style,
      }}
    >
      {children}
    </div>
  );
};

/** 等距分布的容器 (justifyContent: space-between, 适合 2-3 块) */
export const EvenSpread: React.FC<ContentFillProps> = ({
  children,
  direction = "column",
  gap = 0,
  style,
}) => {
  const d = useDesign();
  return (
    <div
      style={{
        flex: 1, // ← 这里反而需要 flex: 1, 让 space-between 真的起作用
        minHeight: 0,
        display: "flex",
        flexDirection: direction,
        justifyContent: "space-between",
        gap: d.scaled(gap),
        ...style,
      }}
    >
      {children}
    </div>
  );
};

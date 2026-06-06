/* ================================================================
   CoverThumbnail — 封面缩略图（静态单帧）

   布局：背景为 AI 生成的插画，上方叠加标题文字
   用于生成视频封面/缩略图，风格与视频一致

   ─────────────────────────────────────────────────────────────
   视觉调定参数 (Tuned 2026-06-05)
   ─────────────────────────────────────────────────────────────
   字号按 1920×1080 参考分辨率锁定（运行时 d.scaled() 缩放）：

     主标题 (title)        96 px  →  三段式排比单行
     日期 (dateLabel)      76 px  →  标题的 0.79 倍
     品牌条 (brand)        70 px  →  标题的 0.73 倍

   字号比例 1.0 : 0.79 : 0.73（黄金三段层级），已通过 B 站/YouTube
   缩略图 320×180 下可读性验证。**不要轻易改这些数字**。

   规则：
   - 仅渲染 3 个元素：日期 / 主标题 / 品牌条，从上到下 flex column
   - 不用副标题（缩略图下不可读，已删除）
   - 不用 emoji、不用「【】!?」
   - 渐变遮罩 `linear-gradient(to bottom, rgba(0,0,0,0.1) 0%, rgba(0,0,0,0.2) 50%, rgba(0,0,0,0.75) 100%)`

   标题格式由 `prompts/title.md` 控制：
   - 三段式排比（"X写代码、Y挖漏洞、Z关起来"）
   - 必出 3 个候选放 `title_candidates[]`，主推放 `title` 字段
   - 中文 12-25 字
   ================================================================ */

import React from "react";
import { Img, staticFile } from "remotion";
import { useDesign, FONTS, FW, COLORS } from "./design";

/** 封面字号（@1920×1080 参考）— 调定后不要改 */
const COVER_FS = {
  title: 96,
  dateLabel: 76,
  brand: 70,
  brandBarWidth: 7,
  brandBarHeight: 48,
  // 2026-06-06: 底部留白 20% (216px @ 1080p) 给 B 站 overlay (播放/时长/弹幕角标)
  // 之前 80px 太贴底, 模板里写 300px 太保守, 改 216
  contentBottom: 216,
  contentLeft: 80,
  contentRight: 80,
  contentGap: 20,
  brandGap: 18,
  brandMarginTop: 12,
} as const;

/** 品牌条文案 */
const BRAND_TEXT = "HN每日观察";

export interface CoverThumbnailProps {
  /** 背景插画路径（相对于 public/） */
  backgroundImage: string;
  /** 主标题 */
  title: string;
  /** 副标题（可选 — 保留 prop 兼容性，**当前版本不渲染**，见顶部注释） */
  subtitle?: string;
  /** 日期标签 */
  dateLabel?: string;
}

export const CoverThumbnail: React.FC<CoverThumbnailProps> = ({
  backgroundImage,
  title,
  subtitle: _subtitle, // 当前版本不渲染副标题
  dateLabel,
}) => {
  const d = useDesign();

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        position: "relative",
        overflow: "hidden",
        background: "#1a1a1a",
      }}
    >
      {/* 背景插画 */}
      <Img
        src={staticFile(backgroundImage)}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          objectFit: "cover",
        }}
      />

      {/* 渐变遮罩（底部加重，保证文字可读） */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          background: `linear-gradient(
            to bottom,
            rgba(0,0,0,0.1) 0%,
            rgba(0,0,0,0.2) 50%,
            rgba(0,0,0,0.75) 100%
          )`,
        }}
      />

      {/* 文字区域 */}
      <div
        style={{
          position: "absolute",
          bottom: d.scaled(COVER_FS.contentBottom),
          left: d.scaled(COVER_FS.contentLeft),
          right: d.scaled(COVER_FS.contentRight),
          display: "flex",
          flexDirection: "column",
          gap: d.scaled(COVER_FS.contentGap),
        }}
      >
        {/* 日期标签 */}
        {dateLabel && (
          <div
            style={{
              fontFamily: FONTS.mono,
              fontSize: d.scaled(COVER_FS.dateLabel),
              fontWeight: FW.bold,
              color: "#ffffff",
              letterSpacing: "0.05em",
              textTransform: "uppercase",
              textShadow: "0 2px 12px rgba(0,0,0,0.6)",
            }}
          >
            {dateLabel}
          </div>
        )}

        {/* 主标题 — 支持 "\n" 显式换行 (2026-06-06 起, B 站长标题缩略图下不糊) */}
        <h1
          style={{
            fontFamily: FONTS.sans,
            fontSize: d.scaled(COVER_FS.title),
            fontWeight: FW.heavy,
            lineHeight: 1.15,
            color: "#ffffff",
            margin: 0,
            whiteSpace: "pre-line",  // 保留 \n 自动换行；其他空白折叠
            textShadow: "0 2px 20px rgba(0,0,0,0.5), 0 1px 4px rgba(0,0,0,0.3)",
            maxWidth: "100%",
          }}
        >
          {title}
        </h1>

        {/* 品牌条 */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: d.scaled(COVER_FS.brandGap),
            marginTop: d.scaled(COVER_FS.brandMarginTop),
          }}
        >
          <div
            style={{
              width: d.scaled(COVER_FS.brandBarWidth),
              height: d.scaled(COVER_FS.brandBarHeight),
              borderRadius: d.scaled(2),
              background: COLORS.brand,
            }}
          />
          <span
            style={{
              fontFamily: FONTS.mono,
              fontSize: d.scaled(COVER_FS.brand),
              fontWeight: FW.bold,
              color: "#ffffff",
              letterSpacing: "0.08em",
              textShadow: "0 2px 12px rgba(0,0,0,0.6)",
            }}
          >
            {BRAND_TEXT}
          </span>
        </div>
      </div>
    </div>
  );
};

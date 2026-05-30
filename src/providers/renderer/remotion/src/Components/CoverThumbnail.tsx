/* ================================================================
   CoverThumbnail — 封面缩略图（静态单帧）

   布局：背景为 AI 生成的插画，上方叠加标题文字
   用于生成视频封面/缩略图，风格与视频一致
   ================================================================ */

import React from "react";
import { Img, staticFile } from "remotion";
import { useDesign, FONTS, FW, COLORS } from "./design";

export interface CoverThumbnailProps {
  /** 背景插画路径（相对于 public/） */
  backgroundImage: string;
  /** 主标题 */
  title: string;
  /** 副标题（可选） */
  subtitle?: string;
  /** 日期标签 */
  dateLabel?: string;
}

export const CoverThumbnail: React.FC<CoverThumbnailProps> = ({
  backgroundImage,
  title,
  subtitle,
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
          bottom: d.scaled(80),
          left: d.scaled(80),
          right: d.scaled(80),
          display: "flex",
          flexDirection: "column",
          gap: d.scaled(20),
        }}
      >
        {/* 日期标签 */}
        {dateLabel && (
          <div
            style={{
              fontFamily: FONTS.mono,
              fontSize: d.fs.body,
              fontWeight: FW.semibold,
              color: COLORS.accentLight,
              letterSpacing: "0.05em",
              textTransform: "uppercase",
            }}
          >
            {dateLabel}
          </div>
        )}

        {/* 主标题 */}
        <h1
          style={{
            fontFamily: FONTS.sans,
            fontSize: d.fs.hero,
            fontWeight: FW.heavy,
            lineHeight: 1.15,
            color: "#ffffff",
            margin: 0,
            textShadow: "0 2px 20px rgba(0,0,0,0.5), 0 1px 4px rgba(0,0,0,0.3)",
            maxWidth: "90%",
          }}
        >
          {title}
        </h1>

        {/* 副标题 */}
        {subtitle && (
          <p
            style={{
              fontFamily: FONTS.sans,
              fontSize: d.fs.subhead,
              fontWeight: FW.regular,
              lineHeight: 1.4,
              color: "rgba(255,255,255,0.85)",
              margin: 0,
              textShadow: "0 1px 12px rgba(0,0,0,0.4)",
              maxWidth: "80%",
            }}
          >
            {subtitle}
          </p>
        )}

        {/* 品牌条 */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: d.scaled(12),
            marginTop: d.scaled(8),
          }}
        >
          <div
            style={{
              width: d.scaled(4),
              height: d.scaled(28),
              borderRadius: d.scaled(2),
              background: COLORS.brand,
            }}
          />
          <span
            style={{
              fontFamily: FONTS.mono,
              fontSize: d.fs.body,
              fontWeight: FW.bold,
              color: "rgba(255,255,255,0.7)",
              letterSpacing: "0.08em",
            }}
          >
            HN每日观察
          </span>
        </div>
      </div>
    </div>
  );
};

/* ================================================================
   CardShellDemo — CardShell 3 种对齐模式的对比 demo

   渲染 3 个 1920x1080 静态帧:
     - FillDemo: 大量内容 + justify="start"     (内容自然撑开)
     - CenterDemo: 极少内容 + justify="center"   (内容垂直居中)
     - EvenlyDemo: 3 块内容 + justify="evenly"   (等距分布)

   用法:
     npx remotion still CardShellDemo-Fill     --props=...
     npx remotion still CardShellDemo-Center   --props=...
     npx remotion still CardShellDemo-Evenly   --props=...
   ================================================================ */

import React from "react";
import { useCurrentFrame, interpolate, AbsoluteFill } from "remotion";
import { COLORS, useDesign, FONTS, FW, CARD_LAYOUT } from "./design";
import { CardShell, Fill, type ContentJustify } from "./CardShell";

export interface CardShellDemoProps {
  mode: ContentJustify;
  title: string;
  /** 内容条数 */
  itemCount: number;
  /** 是否显示 mode 标签横幅 (用于对比图) */
  showModeBadge?: boolean;
}

const SAMPLE_ITEMS = [
  "Liquid AI 发布 1.5B MoE 模型，许可证争议持续发酵",
  "开源数据库 Litestream 作者宣布加入 Anthropic",
  "TypeScript 6.0 路线图曝光: 移除 enum、Go-style sum types",
  "Cloudflare 推出按 CPU 时长计费的容器服务",
  "Vercel 收购 Grep.app，开发者工具赛道再洗牌",
  "Rust 基金会发布 2026 治理改革草案，社区两极分化",
];

const SAMPLE_SIGNALS = [
  "许可证条款将营收千万的公司排除在外，引发'伪开源'质疑",
  "独立维护者可持续性问题再度被推上风口",
  "团队回应'不是 enum 不够好，是 union 表达力更强'",
  "正面对标 AWS Fargate，定价模型引发长文讨论",
  "搜索能力免费给个人用户，Pro 团队 20 美元/月",
  "Google/Amazon/Microsoft 罕见联合发声反对某条款",
];

export const CardShellDemo: React.FC<CardShellDemoProps> = ({
  mode,
  title,
  itemCount,
  showModeBadge = true,
}) => {
  const frame = useCurrentFrame();
  const d = useDesign();

  const titleProgress = interpolate(frame, [4, 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const bodyProgress = interpolate(frame, [10, 26], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 截取对应数量的 items
  const items = SAMPLE_ITEMS.slice(0, itemCount);
  const signals = SAMPLE_SIGNALS.slice(0, itemCount);

  return (
    <AbsoluteFill style={{ background: "#0d1117" }}>
      {/* 演示模式标签 */}
      {showModeBadge && (
        <div
          style={{
            position: "absolute",
            top: d.scaled(20),
            left: 0,
            right: 0,
            display: "flex",
            justifyContent: "center",
            gap: d.scaled(20),
            zIndex: 100,
            fontFamily: FONTS.mono,
          }}
        >
          <div
            style={{
              padding: `${d.scaled(6)}px ${d.scaled(20)}px`,
              background: COLORS.brand,
              color: "#fff",
              fontWeight: FW.bold,
              fontSize: d.fs.caption,
              letterSpacing: "0.1em",
              borderRadius: d.scaled(4),
            }}
          >
            justify=&quot;{mode}&quot; · {itemCount} items
          </div>
        </div>
      )}

      <CardShell
        elementProps={{ dateLabel: "2026-06-02" }}
        justify={mode}
        gutter={100}
        paddingTop={100}
        paddingBottom={100}
        showTopBar
        showWatermark={false}
        showWaveform={false}
      >
        <Fill gap={24} maxWidth={CARD_LAYOUT.content.maxWidth}>
          {/* Title */}
          <h1
            style={{
              fontSize: d.fs.headline,
              fontWeight: FW.heavy,
              lineHeight: 1.15,
              letterSpacing: "-0.015em",
              color: COLORS.fg,
              opacity: titleProgress,
              transform: `translateY(${interpolate(titleProgress, [0, 1], [12, 0])}px)`,
            }}
          >
            {title}
          </h1>

          {/* Divider */}
          <div
            style={{
              width: "100%",
              maxWidth: d.scaled(CARD_LAYOUT.divider.maxWidth),
              height: d.scaled(CARD_LAYOUT.divider.height),
              borderRadius: d.scaled(CARD_LAYOUT.divider.borderRadius),
              background: `linear-gradient(90deg, ${COLORS.brand}, ${COLORS.brandSoft}, transparent)`,
              opacity: titleProgress,
            }}
          />

          {/* Items */}
          {items.length > 0 && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: d.scaled(20),
                width: "100%",
                opacity: bodyProgress,
                transform: `translateY(${interpolate(bodyProgress, [0, 1], [12, 0])}px)`,
              }}
            >
              {items.map((item, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: d.scaled(6),
                    paddingBottom: d.scaled(14),
                    borderBottom: i < items.length - 1 ? `1px solid ${COLORS.border}` : undefined,
                  }}
                >
                  <span
                    style={{
                      fontSize: d.fs.body,
                      fontWeight: FW.heavy,
                      color: COLORS.fg,
                      lineHeight: 1.3,
                    }}
                  >
                    {item}
                  </span>
                  <span
                    style={{
                      fontSize: d.fs.bodySmall,
                      color: COLORS.muted,
                      lineHeight: 1.5,
                    }}
                  >
                    {signals[i]}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Footer line */}
          <p
            style={{
              fontSize: d.fs.bodySmall,
              color: COLORS.dim,
              marginTop: d.scaled(20),
              opacity: bodyProgress,
            }}
          >
            今天的 HN 速览就到这里，我们明天继续看哪些讨论值得停一下。
          </p>
        </Fill>
      </CardShell>
    </AbsoluteFill>
  );
};

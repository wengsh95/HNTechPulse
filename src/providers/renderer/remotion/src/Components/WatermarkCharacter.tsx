/* ================================================================
   WatermarkCharacter — 右下角小人水印组件
   ================================================================

   共用组件，用于在卡片右下角显示小人图片。
   所有卡片统一使用此组件，方便维护。
*/

import React from "react";
import { staticFile } from "remotion";
import { useTheme } from "./theme";

export const WatermarkCharacter: React.FC = () => {
  const d = useTheme();

  return (
    <img
      src={staticFile("46f7d3ff4a5c075370fbcaaccf5bca0d.jpg")}
      alt=""
      style={{
        position: "absolute" as const,
        bottom: 0,
        right: d.scaled(60),
        width: d.scaled(320),
        height: d.scaled(320),
        borderRadius: d.scaled(48),
        objectFit: "cover" as const,
        opacity: 0.85,
        zIndex: 5,
      }}
    />
  );
};

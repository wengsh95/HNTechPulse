/* ================================================================
   useStylePatch — 从 style_patches.json 读取元素样式覆盖

   卡片组件中使用:  const patch = useStylePatch("event", "event-headline");
   然后在 style={{ ...existing, ...patch }} 中展开即可。

   编辑器中通过 data-element 属性给元素命名，保存时按 cardType + elementName
   映射覆盖值。
   ================================================================ */

import { useMemo } from "react";

// Vite 支持直接 import JSON，HMR 也会在文件变化时热更新
import patchesRaw from "../../style_patches.json";

type PatchMap = Record<string, Record<string, Record<string, string>>>;

const patches = patchesRaw as PatchMap;

/**
 * 获取指定卡片类型 + 元素名称的样式覆盖
 * @returns 可展开到 React style 对象中的 CSS 属性
 */
export function useStylePatch(
  cardType: string,
  elementName: string,
): Record<string, unknown> {
  return useMemo(() => {
    const cardPatches = patches[cardType];
    if (!cardPatches) return {};
    const elPatch = cardPatches[elementName];
    if (!elPatch) return {};

    // 转换: 数字字符串 → number (方便 React inline style)
    const style: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(elPatch)) {
      const num = parseFloat(value);
      // 纯数字值且 key 需要 px 单位时保持字符串，React 对 fontSize/width 等会自动处理
      if (!isNaN(num) && String(num) === value.trim()) {
        style[key] = num;
      } else {
        style[key] = value;
      }
    }
    return style;
  }, [cardType, elementName]);
}

/**
 * 获取整个 patches 对象 (供编辑器使用)
 */
export function getAllPatches(): PatchMap {
  return patches;
}

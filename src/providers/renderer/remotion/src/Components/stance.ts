/* ================================================================
   Stance taxonomy — single source of truth.

   The Python pipeline emits one of the ``Stance`` values from
   cardTypes.ts. The renderer maps each canonical stance to a
   display label (Chinese) and a color from the design system.
   ================================================================ */

import type { Stance } from "./cardTypes";

export const STANCE_LABELS: Record<Stance, string> = {
  support: "支持",
  skeptic: "质疑",
  neutral: "中立",
  tease: "调侃",
  worry: "担忧",
};

export const STANCE_COLORS: Record<Stance, string> = {
  support: "#4f8761", // 模板 --color-green (stance support bar)
  skeptic: "#c69230", // 模板 --color-amber (stance skeptical bar)
  neutral: "#8a8075", // 模板 --color-gray (stance neutral bar)
  tease: "#9b7ec4",
  worry: "#ff6600",
};

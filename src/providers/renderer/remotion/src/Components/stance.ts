/* ================================================================
   Stance taxonomy — single source of truth.

   The Python pipeline emits one of the ``Stance`` values from
   cardTypes.ts. The renderer maps each canonical stance to a
   display label (Chinese) and a color from the design system.
   ================================================================ */

import { COLORS } from "./design";
import type { Stance } from "./cardTypes";

export const STANCE_LABELS: Record<Stance, string> = {
  support: "支持",
  skeptic: "质疑",
  neutral: "中立",
  tease: "调侃",
  worry: "担忧",
};

export const STANCE_COLORS: Record<Stance, string> = {
  support: COLORS.sage,
  skeptic: COLORS.warmGold,
  neutral: COLORS.dim,
  tease: COLORS.purple,
  worry: COLORS.warmBrown,
};

import React from "react";
import { interpolate, Easing } from "remotion";

import { COLORS, FONTS, FW } from "./design";

export interface DashboardEntry {
  rank?: number;
  original_title?: string;
  title?: string;
  title_translation?: string;
  title_cn?: string;
  score?: number;
  comment_count?: number;
  editor_angle?: string;
  why_it_matters?: string;
  next_watch?: string;
  category?: string;
  keywords?: string[];
}

export const medalSets = [
  { text: "#FFD60A", bg: "rgba(255,214,10,0.15)", ring: "rgba(255,214,10,0.35)" },
  { text: "rgba(245,245,247,0.70)", bg: "rgba(245,245,247,0.08)", ring: "rgba(245,245,247,0.18)" },
  { text: "#FF9F0A", bg: "rgba(255,159,10,0.12)", ring: "rgba(255,159,10,0.28)" },
];

export const MedalBadge: React.FC<{
  rank: number;
  size?: number;
  fontSize?: number;
}> = ({ rank, size = 28, fontSize = 14 }) => {
  const isMedal = rank <= 3;
  const medal = isMedal ? medalSets[rank - 1] : null;

  if (isMedal) {
    return (
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: medal!.bg,
          border: `1.5px solid ${medal!.ring}`,
          fontFamily: FONTS.mono,
          fontSize,
          fontWeight: FW.bold,
          color: medal!.text,
          lineHeight: 1,
        }}
      >
        {rank}
      </span>
    );
  }

  return (
    <span
      style={{
        fontFamily: FONTS.mono,
        fontSize: fontSize + 3,
        fontWeight: FW.medium,
        color: COLORS.textTertiary,
      }}
    >
      {rank}
    </span>
  );
};

export const PageIndicator: React.FC<{
  pages: unknown[][];
  currentPage: number;
}> = ({ pages, currentPage }) => (
  <div style={{ display: "flex", justifyContent: "center", gap: 8, marginTop: 16 }}>
    {pages.map((_, pi) => (
      <div
        key={pi}
        style={{
          width: pi === currentPage ? 24 : 8,
          height: 8,
          borderRadius: 4,
          backgroundColor: pi === currentPage ? COLORS.accent : "rgba(255,255,255,0.12)",
        }}
      />
    ))}
  </div>
);

export const CategoryBadge: React.FC<{
  category: string;
  maxWidth?: number;
}> = ({ category, maxWidth = 120 }) => (
  <div
    style={{
      fontFamily: FONTS.sans,
      fontSize: 12,
      fontWeight: 700,
      color: COLORS.accentLight,
      backgroundColor: COLORS.accentBg,
      borderRadius: 6,
      padding: "5px 10px",
      maxWidth,
      overflow: "hidden",
      whiteSpace: "nowrap",
      textOverflow: "ellipsis",
    }}
  >
    {category}
  </div>
);

export const KeywordTags: React.FC<{
  keywords: string[];
  max?: number;
  maxWidth?: number;
}> = ({ keywords, max = 2, maxWidth = 46 }) => (
  <div style={{ display: "flex", gap: 5 }}>
    {keywords.slice(0, max).map((kw) => (
      <span
        key={kw}
        style={{
          fontFamily: FONTS.sans,
          fontSize: 10,
          color: COLORS.textTertiary,
          maxWidth,
          overflow: "hidden",
          whiteSpace: "nowrap",
          textOverflow: "ellipsis",
        }}
      >
        {kw}
      </span>
    ))}
  </div>
);

export const rowEntryAnimation = (
  frame: number,
  rowStart: number,
  duration: number = 20,
) =>
  interpolate(frame, [rowStart, rowStart + duration], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

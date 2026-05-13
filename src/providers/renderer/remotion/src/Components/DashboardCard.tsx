import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

import { ElementProps } from "./utils";
import { COLORS, FONTS, glassCard, glassCardShadow, LAYOUT, S } from "./design";
import { DashboardEntry } from "./DashboardShared";
import { GuideDashboard } from "./GuideDashboard";
import { RankingDashboard } from "./RankingDashboard";

export const DashboardCard: React.FC<ElementProps> = ({ elementProps, width, height, duration }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const entries = (elementProps.entries as DashboardEntry[]) ?? [];
  const mode = elementProps.mode === "guide" ? "guide" : "ranking";
  const focusCount = Number(elementProps.focus_count) || 3;

  if (mode === "guide") {
    return (
      <GuideDashboard
        entries={entries}
        frame={frame}
        fps={fps}
        width={width}
        height={height}
        duration={duration}
        focusCount={focusCount}
      />
    );
  }

  return (
    <RankingDashboard
      entries={entries}
      frame={frame}
      fps={fps}
      width={width}
      height={height}
      duration={duration}
    />
  );
};

import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";

import { CueData } from "../types";
import { ElementProps, p, truncate, stripHtml } from "./utils";
import { COLORS, FONTS, LAYOUT, S } from "./design";

export const Subtitle: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cues = (elementProps.cues as CueData[]) ?? [];
  const fallbackText = truncate(stripHtml(p(elementProps, "text", "")), 120);

  const currentTime = frame / fps;

  let displayText = fallbackText;
  let opacity = 1;
  if (cues.length > 0) {
    let activeCue = cues.find(
      (c) => currentTime >= c.start_time - 0.05 && currentTime <= c.end_time + 0.05
    );
    if (!activeCue) {
      let minDist = Infinity;
      for (const c of cues) {
        const distToStart = Math.abs(currentTime - c.start_time);
        const distToEnd = Math.abs(currentTime - c.end_time);
        const dist = Math.min(distToStart, distToEnd);
        if (dist < minDist) {
          minDist = dist;
          activeCue = c;
        }
      }
    }
    if (activeCue) {
      displayText = activeCue.text;
    } else if (currentTime >= cues[cues.length - 1].end_time) {
      const fadeOutDuration = 0.5;
      const timeSinceEnd = currentTime - cues[cues.length - 1].end_time;
      if (timeSinceEnd < fadeOutDuration) {
        displayText = cues[cues.length - 1].text;
        opacity = 1 - timeSinceEnd / fadeOutDuration;
      } else {
        displayText = "";
        opacity = 0;
      }
    } else if (currentTime < cues[0].start_time) {
      displayText = cues[0].text;
    }
  }

  return (
    <div style={{
      ...S,
      left: "50%",
      bottom: 32,
      transform: "translateX(-50%)",
      backgroundColor: "rgba(9, 11, 20, 0.78)",
      backdropFilter: "blur(24px)",
      WebkitBackdropFilter: "blur(24px)",
      border: "1px solid rgba(255, 255, 255, 0.08)",
      borderRadius: 22,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "14px 24px",
      width: Math.min(width - LAYOUT.pageInset * 2, LAYOUT.subtitleMaxWidth),
      minHeight: 76,
      opacity,
    }}>
      <span style={{
        fontFamily: FONTS.sans,
        fontSize: 24,
        color: COLORS.text,
        textAlign: "center",
        lineHeight: 1.45,
        fontWeight: 500,
        letterSpacing: 0.1,
        textShadow: "0 1px 2px rgba(0,0,0,0.5)",
        maxWidth: "100%",
      }}>
        {displayText}
      </span>
    </div>
  );
};

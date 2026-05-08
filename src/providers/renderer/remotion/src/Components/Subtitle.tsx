import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";

import { CueData } from "../types";
import { ElementProps, p, truncate, stripHtml } from "./utils";
import { FONTS, S } from "./design";

export const Subtitle: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cues = (elementProps.cues as CueData[]) ?? [];
  const fallbackText = truncate(stripHtml(p(elementProps, "text", "")), 120);

  const currentTime = frame / fps;

  let displayText = fallbackText;
  let opacity = 1;
  if (cues.length > 0) {
    // Find the cue whose time range contains currentTime (with small tolerance)
    let activeCue = cues.find(
      (c) => currentTime >= c.start_time - 0.05 && currentTime <= c.end_time + 0.05
    );
    if (!activeCue) {
      // Between cues: find the nearest cue by distance to its boundaries
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
      bottom: 24,
      transform: "translateX(-50%)",
      backgroundColor: "rgba(0, 0, 0, 0.45)",
      backdropFilter: "blur(12px)",
      WebkitBackdropFilter: "blur(12px)",
      borderRadius: 20,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: "10px 24px",
      width: "94%",
      opacity,
    }}>
      <span style={{
        fontFamily: FONTS.sans,
        fontSize: 26,
        color: "#ffffff",
        textAlign: "center",
        lineHeight: 1.4,
        fontWeight: 500,
        letterSpacing: 0.2,
      }}>
        {displayText}
      </span>
    </div>
  );
};

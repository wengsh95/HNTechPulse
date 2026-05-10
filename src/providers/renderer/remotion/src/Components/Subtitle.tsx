import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";

import { CueData } from "../types";
import { ElementProps, p, truncate, stripHtml } from "./utils";
import { COLORS, FONTS, LAYOUT, S } from "./design";

export const Subtitle: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cues = (elementProps.cues as CueData[]) ?? [];
  const mode = p<"standard" | "minimal" | "hidden">(elementProps, "mode", "standard");
  const fallbackText = truncate(stripHtml(p(elementProps, "text", "")), mode === "minimal" ? 56 : 84);

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
      displayText = truncate(activeCue.text, mode === "minimal" ? 56 : 84);
    } else if (currentTime >= cues[cues.length - 1].end_time) {
      const fadeOutDuration = 0.5;
      const timeSinceEnd = currentTime - cues[cues.length - 1].end_time;
      if (timeSinceEnd < fadeOutDuration) {
        displayText = truncate(cues[cues.length - 1].text, mode === "minimal" ? 56 : 84);
        opacity = 1 - timeSinceEnd / fadeOutDuration;
      } else {
        displayText = "";
        opacity = 0;
      }
    } else if (currentTime < cues[0].start_time) {
      displayText = truncate(cues[0].text, mode === "minimal" ? 56 : 84);
    }
  }

  if (mode === "hidden" || !displayText) {
    return null;
  }

  const isMinimal = mode === "minimal";

  return (
    <div style={{
      ...S,
      left: "50%",
      bottom: isMinimal ? 28 : 30,
      transform: "translateX(-50%)",
      background: isMinimal
        ? "linear-gradient(90deg, rgba(7, 7, 18, 0), rgba(7, 7, 18, 0.28) 18%, rgba(7, 7, 18, 0.28) 82%, rgba(7, 7, 18, 0))"
        : "linear-gradient(90deg, rgba(7, 7, 18, 0), rgba(7, 7, 18, 0.40) 16%, rgba(7, 7, 18, 0.40) 84%, rgba(7, 7, 18, 0))",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: isMinimal ? "6px 24px" : "7px 28px",
      width: Math.min(width - LAYOUT.pageInset * 2.4, LAYOUT.subtitleMaxWidth),
      minHeight: isMinimal ? 38 : 46,
      opacity: opacity * (isMinimal ? 0.74 : 0.88),
    }}>
      <span style={{
        fontFamily: FONTS.sans,
        fontSize: isMinimal ? 17 : 19,
        color: COLORS.text,
        textAlign: "center",
        lineHeight: 1.36,
        fontWeight: 500,
        letterSpacing: 0,
        textShadow: "0 2px 10px rgba(0,0,0,0.62), 0 1px 2px rgba(0,0,0,0.76)",
        maxWidth: "100%",
        overflow: "hidden",
        display: "-webkit-box",
        WebkitLineClamp: 2,
        WebkitBoxOrient: "vertical" as const,
      }}>
        {displayText}
      </span>
    </div>
  );
};

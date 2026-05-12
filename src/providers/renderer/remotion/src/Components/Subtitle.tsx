import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";

import { CueData } from "../types";
import { ElementProps, p, stripHtml } from "./utils";
import { COLORS, FONTS, FW, LAYOUT, S } from "./design";

export const Subtitle: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cues = (elementProps.cues as CueData[]) ?? [];
  const mode = p<"standard" | "minimal" | "hidden">(elementProps, "mode", "standard");
  const fallbackText = stripHtml(p(elementProps, "text", ""));

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

  if (mode === "hidden" || !displayText) {
    return null;
  }

  const isMinimal = mode === "minimal";

  const subMaxWidth = Math.min(width - LAYOUT.pageInset * 2.4, 720);

  return (
    <div style={{
      ...S,
      left: "50%",
      bottom: isMinimal ? LAYOUT.subtitleBottomMinimal : LAYOUT.subtitleBottom,
      transform: "translateX(-50%)",
      background: isMinimal
        ? "linear-gradient(90deg, rgba(7, 7, 18, 0), rgba(7, 7, 18, 0.38) 16%, rgba(7, 7, 18, 0.38) 84%, rgba(7, 7, 18, 0))"
        : "linear-gradient(90deg, rgba(7, 7, 18, 0), rgba(7, 7, 18, 0.52) 14%, rgba(7, 7, 18, 0.52) 86%, rgba(7, 7, 18, 0))",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: isMinimal ? "10px 28px" : "10px 28px",
      width: subMaxWidth,
      minHeight: isMinimal ? 40 : 48,
      opacity: opacity * (isMinimal ? 0.72 : 0.88),
      borderRadius: 12,
    }}>
      <span style={{
        fontFamily: FONTS.sans,
        fontSize: 22,
        color: COLORS.text,
        textAlign: "center",
        lineHeight: 1.45,
        fontWeight: FW.semibold,
        letterSpacing: 0,
        textShadow: "0 2px 12px rgba(0,0,0,0.68), 0 1px 3px rgba(0,0,0,0.8)",
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

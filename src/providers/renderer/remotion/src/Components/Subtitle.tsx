import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";

import { CueData } from "../types";
import { ElementProps, p, stripHtml } from "./utils";
import { COLORS, FONTS, FW, useDesign, GRADIENTS, S } from "./design";

export const Subtitle: React.FC<ElementProps> = ({ elementProps, width, height: _height }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const d = useDesign();
  const cues = (elementProps.cues as CueData[]) ?? [];
  const mode = p<"standard" | "minimal" | "hidden">(elementProps, "mode", "standard");
  const fallbackText = stripHtml(p(elementProps, "text", ""));

  const currentTime = frame / fps;

  let displayText = fallbackText;
  let opacity = 1;
  let slideY = 0;
  if (cues.length > 0) {
    // Find the active cue whose time range contains currentTime
    let activeCue = cues.find(
      (c) => currentTime >= c.start_time - 0.05 && currentTime <= c.end_time + 0.05,
    );
    if (!activeCue) {
      // No active cue — check if we're in a gap between cues
      const lastCue = cues[cues.length - 1];
      const firstCue = cues[0];

      if (currentTime >= lastCue.end_time) {
        // After all cues — fade out the last cue
        const fadeOutDuration = 0.5;
        const timeSinceEnd = currentTime - lastCue.end_time;
        if (timeSinceEnd < fadeOutDuration) {
          displayText = lastCue.text;
          opacity = 1 - timeSinceEnd / fadeOutDuration;
          slideY = interpolate(opacity, [0, 1], [4, 0]);
        } else {
          displayText = "";
          opacity = 0;
        }
      } else if (currentTime < firstCue.start_time) {
        // Before first cue — show nothing
        displayText = "";
        opacity = 0;
      } else {
        // In a gap between cues — show nothing
        displayText = "";
        opacity = 0;
      }
    } else {
      displayText = activeCue.text;
      // Fade in at the start of each cue
      const cueElapsed = currentTime - activeCue.start_time;
      const cueFadeIn = interpolate(cueElapsed, [0, 0.15], [0, 1], {
        easing: Easing.bezier(0.16, 1, 0.3, 1),
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
      opacity = cueFadeIn;
      slideY = interpolate(cueFadeIn, [0, 1], [6, 0]);
    }
  }

  if (mode === "hidden" || !displayText) {
    return null;
  }

  const isMinimal = mode === "minimal";

  const subMaxWidth = Math.min(width - d.layout.pageInset * 3.2, d.scaled(isMinimal ? 560 : 640));

  return (
    <div
      style={{
        ...S,
        left: "50%",
        bottom:
          (isMinimal ? d.layout.subtitleBottomMinimal : d.layout.subtitleBottom) + d.scaled(8),
        transform: `translateX(-50%) translateY(${slideY}px)`,
        background: isMinimal ? GRADIENTS.subtitleMinimal : GRADIENTS.subtitleStandard,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: `${d.scaled(7)}px ${d.scaled(24)}px`,
        width: subMaxWidth,
        minHeight: isMinimal ? d.scaled(34) : d.scaled(42),
        opacity: opacity * (isMinimal ? 0.72 : 0.84),
        borderRadius: d.scaled(12),
      }}
    >
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: Math.round(d.fs.subtitle * (isMinimal ? 0.74 : 0.8)),
          color: isMinimal ? COLORS.textSecondary : COLORS.textBody,
          textAlign: "center",
          lineHeight: 1.35,
          fontWeight: FW.medium,
          letterSpacing: 0,
          maxWidth: "100%",
          overflow: "hidden",
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical" as const,
        }}
      >
        {displayText}
      </span>
    </div>
  );
};

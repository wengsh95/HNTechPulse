import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

import { CueData } from "../types";
import { ElementProps, p, stripHtml } from "./utils";
import { COLORS, EASE_CARD, FONTS, FW, useDesign, SUBTITLE_LAYOUT, SURFACES } from "./design";

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
    let activeCue = cues.find(
      (c) =>
        currentTime >= c.start_time - SUBTITLE_LAYOUT.cueToleranceSeconds &&
        currentTime <= c.end_time + SUBTITLE_LAYOUT.cueToleranceSeconds,
    );
    if (!activeCue) {
      const lastCue = cues[cues.length - 1];
      const firstCue = cues[0];

      if (currentTime >= lastCue.end_time) {
        const fadeOutDuration = SUBTITLE_LAYOUT.fadeOutSeconds;
        const timeSinceEnd = currentTime - lastCue.end_time;
        if (timeSinceEnd < fadeOutDuration) {
          displayText = lastCue.text;
          opacity = 1 - timeSinceEnd / fadeOutDuration;
          slideY = interpolate(opacity, [0, 1], [SUBTITLE_LAYOUT.exitSlideY, 0]);
        } else {
          displayText = "";
          opacity = 0;
        }
      } else if (currentTime < firstCue.start_time) {
        displayText = "";
        opacity = 0;
      } else {
        displayText = "";
        opacity = 0;
      }
    } else {
      displayText = activeCue.text;
      const cueElapsed = currentTime - activeCue.start_time;
      const cueFadeIn = interpolate(cueElapsed, [0, SUBTITLE_LAYOUT.fadeInSeconds], [0, 1], {
        easing: EASE_CARD,
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      });
      opacity = cueFadeIn;
      slideY = interpolate(cueFadeIn, [0, 1], [SUBTITLE_LAYOUT.enterSlideY, 0]);
    }
  }

  if (mode === "hidden" || !displayText) {
    return null;
  }

  const subMaxWidth = Math.min(width - d.layout.pageInset * 2, d.layout.subtitleMaxWidth);

  return (
    <div
      style={{
        position: "absolute",
        left: "50%",
        bottom: d.layout.subtitleBottom + d.scaled(SUBTITLE_LAYOUT.bottomOffset),
        transform: `translateX(-50%) translateY(${slideY}px)`,
        background: SURFACES.subtitle,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: `${d.scaled(SUBTITLE_LAYOUT.paddingY)}px ${d.scaled(SUBTITLE_LAYOUT.paddingX)}px`,
        width: subMaxWidth,
        minHeight: d.scaled(SUBTITLE_LAYOUT.minHeight),
        opacity: opacity * SUBTITLE_LAYOUT.opacity,
        borderRadius: d.scaled(SUBTITLE_LAYOUT.radius),
        border: `1px solid ${COLORS.border}`,
      }}
    >
      <span
        style={{
          fontFamily: FONTS.sans,
          fontSize: Math.round(d.fs.subtitle * SUBTITLE_LAYOUT.fontScale),
          color: COLORS.fg,
          textAlign: "center",
          lineHeight: SUBTITLE_LAYOUT.lineHeight,
          fontWeight: FW.medium,
          letterSpacing: 0,
          maxWidth: "100%",
          whiteSpace: "normal",
        }}
      >
        {displayText}
      </span>
    </div>
  );
};

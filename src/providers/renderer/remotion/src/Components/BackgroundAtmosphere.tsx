/**
 * BackgroundAtmosphere —— 背景氛围层
 *
 * Two atmospheric effects that add spatial depth without changing any layout:
 * 1. Gradient glow spots (渐变光斑) — large, very low-opacity radial gradients
 *    that slowly drift over time, creating a subtle living atmosphere.
 * 2. Micro dot grid (微网格) — barely-visible dot pattern across the entire
 *    canvas, giving a subtle tech/blueprint feel.
 */
import React from "react";
import { interpolate, useCurrentFrame } from "remotion";

import { BACKGROUND_LAYOUT, COMMON_LAYOUT, GRADIENTS } from "./design";

type GlowSpot = {
  /** Base position as fraction of canvas size (0-1) */
  x: number;
  y: number;
  /** Diameter in px */
  size: number;
  /** Radial gradient color (e.g. rgba(0,122,255,0.04)) */
  color: string;
  /** Drift frequency — higher = faster oscillation */
  freqX: number;
  freqY: number;
  /** Drift phase offset so spots move independently */
  phaseX: number;
  phaseY: number;
};

const GLOW_SPOTS: GlowSpot[] = [
  {
    x: 0.85,
    y: 0.12,
    size: 700,
    color: "rgba(255,102,0,0.04)", // HN orange glow
    freqX: 0.008,
    freqY: 0.006,
    phaseX: 0,
    phaseY: 0.5,
  },
  {
    x: 0.1,
    y: 0.82,
    size: 650,
    color: "rgba(155,126,196,0.04)",
    freqX: 0.006,
    freqY: 0.009,
    phaseX: 1.2,
    phaseY: 0,
  },
  {
    x: 0.15,
    y: 0.45,
    size: 600,
    color: "rgba(255,102,0,0.03)",
    freqX: 0.007,
    freqY: 0.005,
    phaseX: 2.5,
    phaseY: 1.8,
  },
];

export const BackgroundAtmosphere: React.FC<{
  width: number;
  height: number;
}> = ({ width, height }) => {
  const frame = useCurrentFrame();
  const scale = Math.min(width / BACKGROUND_LAYOUT.width, height / BACKGROUND_LAYOUT.height);
  const dotSize = Math.round(BACKGROUND_LAYOUT.dotGridSize * scale);

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        zIndex: 0,
      }}
    >
      {/* Glow spots */}
      {GLOW_SPOTS.map((spot, i) => {
        const driftX = interpolate(
          Math.sin(spot.freqX * frame + spot.phaseX),
          [-1, 1],
          [
            -BACKGROUND_LAYOUT.glowDriftAmplitude * scale,
            BACKGROUND_LAYOUT.glowDriftAmplitude * scale,
          ],
        );
        const driftY = interpolate(
          Math.sin(spot.freqY * frame + spot.phaseY),
          [-1, 1],
          [
            -BACKGROUND_LAYOUT.glowDriftAmplitude * scale,
            BACKGROUND_LAYOUT.glowDriftAmplitude * scale,
          ],
        );

        return (
          <div
            key={`glow-${i}`}
            style={{
              position: "absolute",
              left: spot.x * width - Math.round(spot.size * scale) / 2 + driftX,
              top: spot.y * height - Math.round(spot.size * scale) / 2 + driftY,
              width: Math.round(spot.size * scale),
              height: Math.round(spot.size * scale),
              borderRadius: COMMON_LAYOUT.circleRadius,
              background: `radial-gradient(circle, ${spot.color} 0%, transparent ${BACKGROUND_LAYOUT.glowTransparentStop}%)`,
              filter: `blur(${Math.round(BACKGROUND_LAYOUT.glowBlur * scale)}px)`,
              pointerEvents: "none",
            }}
          />
        );
      })}

      {/* Micro dot grid */}
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: "100%",
          height: "100%",
          backgroundImage: GRADIENTS.dotGrid,
          backgroundSize: `${dotSize}px ${dotSize}px`,
          pointerEvents: "none",
        }}
      />
    </div>
  );
};

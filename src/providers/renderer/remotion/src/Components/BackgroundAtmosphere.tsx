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

import { COLORS, GRADIENTS } from "./design";

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
    color: "rgba(0, 122, 255, 0.04)", // unique low-opacity accent glow
    freqX: 0.008,
    freqY: 0.006,
    phaseX: 0,
    phaseY: 0.5,
  },
  {
    x: 0.1,
    y: 0.82,
    size: 650,
    color: "rgba(191, 90, 242, 0.04)",
    freqX: 0.006,
    freqY: 0.009,
    phaseX: 1.2,
    phaseY: 0,
  },
  {
    x: 0.15,
    y: 0.45,
    size: 600,
    color: "rgba(255, 102, 0, 0.025)", // unique low-opacity brand glow
    freqX: 0.007,
    freqY: 0.005,
    phaseX: 2.5,
    phaseY: 1.8,
  },
];

/** Maximum drift amplitude in px */
const DRIFT_AMPLITUDE = 30;

export const BackgroundAtmosphere: React.FC<{
  width: number;
  height: number;
}> = ({ width, height }) => {
  const frame = useCurrentFrame();

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
          [-DRIFT_AMPLITUDE, DRIFT_AMPLITUDE],
        );
        const driftY = interpolate(
          Math.sin(spot.freqY * frame + spot.phaseY),
          [-1, 1],
          [-DRIFT_AMPLITUDE, DRIFT_AMPLITUDE],
        );

        return (
          <div
            key={`glow-${i}`}
            style={{
              position: "absolute",
              left: spot.x * width - spot.size / 2 + driftX,
              top: spot.y * height - spot.size / 2 + driftY,
              width: spot.size,
              height: spot.size,
              borderRadius: "50%",
              background: `radial-gradient(circle, ${spot.color} 0%, transparent 70%)`,
              filter: "blur(80px)",
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
          backgroundSize: "40px 40px",
          pointerEvents: "none",
        }}
      />
    </div>
  );
};

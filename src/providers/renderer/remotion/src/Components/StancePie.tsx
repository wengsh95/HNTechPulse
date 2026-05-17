import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";

import { COLORS, FONTS, FW, useDesign } from "./design";

export const STANCE_COLORS: Record<string, string> = {
  支持: COLORS.green,
  质疑: COLORS.orangeRed,
  中立: COLORS.gray,
  调侃: COLORS.yellow,
  担忧: COLORS.purple,
};

/** Donut chart with legend below. `size` is the donut diameter (excluding legend). */
export const StancePie: React.FC<{
  distribution: Record<string, number>;
  size: number;
  centerLabel?: string;
  stanceConcerns?: Record<string, string>;
}> = ({ distribution, size, centerLabel, stanceConcerns }) => {
  const frame = useCurrentFrame();
  const { fs } = useDesign();
  const pad = 8;
  const svgSize = size + pad * 2;
  const cx = svgSize / 2;
  const cy = svgSize / 2;
  const outerR = size / 2 - 4;
  const innerR = outerR * 0.55;
  const entries = Object.entries(distribution).filter(([, v]) => v > 0);

  const pieProgress = interpolate(frame, [8, 40], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  let cumulative = 0;
  const arcs = entries.map(([label, value], idx) => {
    const startAngle = cumulative * 2 * Math.PI;
    cumulative += value;
    const endAngle = cumulative * 2 * Math.PI;

    const revealedEndAngle = startAngle + (endAngle - startAngle) * pieProgress;
    const largeArc = revealedEndAngle - startAngle > Math.PI ? 1 : 0;

    const outerX1 = cx + outerR * Math.cos(startAngle - Math.PI / 2);
    const outerY1 = cy + outerR * Math.sin(startAngle - Math.PI / 2);
    const outerX2 = cx + outerR * Math.cos(revealedEndAngle - Math.PI / 2);
    const outerY2 = cy + outerR * Math.sin(revealedEndAngle - Math.PI / 2);
    const innerX1 = cx + innerR * Math.cos(startAngle - Math.PI / 2);
    const innerY1 = cy + innerR * Math.sin(startAngle - Math.PI / 2);
    const innerX2 = cx + innerR * Math.cos(revealedEndAngle - Math.PI / 2);
    const innerY2 = cy + innerR * Math.sin(revealedEndAngle - Math.PI / 2);

    const path = `M ${outerX1} ${outerY1} A ${outerR} ${outerR} 0 ${largeArc} 1 ${outerX2} ${outerY2} L ${innerX2} ${innerY2} A ${innerR} ${innerR} 0 ${largeArc} 0 ${innerX1} ${innerY1} Z`;
    const color = STANCE_COLORS[label] || COLORS.textSecondary;
    const pct = Math.round(value * 100);

    return { label, value, path, color, pct, idx };
  });

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        flexShrink: 0,
      }}
    >
      <div style={{ position: "relative", width: svgSize, height: svgSize }}>
        <svg width={svgSize} height={svgSize} viewBox={`0 0 ${svgSize} ${svgSize}`}>
          {arcs.map((arc) => (
            <path
              key={arc.idx}
              d={arc.path}
              fill={arc.color}
              stroke={COLORS.bgStroke}
              strokeWidth={1.5}
            />
          ))}
        </svg>
        {centerLabel && (
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              fontFamily: FONTS.mono,
              fontSize: fs.subhead,
              fontWeight: FW.heavy,
              color: COLORS.text,
              textAlign: "center",
              lineHeight: 1.2,
              pointerEvents: "none",
            }}
          >
            {centerLabel}
          </div>
        )}
      </div>

      {/* Legend below — one stance per row */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 10,
          marginTop: 14,
        }}
      >
        {arcs.map((arc) => {
          const concern = stanceConcerns?.[arc.label];
          return (
            <div
              key={`legend-${arc.idx}`}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-start",
                gap: 2,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <span
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: "50%",
                    backgroundColor: arc.color,
                    flexShrink: 0,
                  }}
                />
                <span
                  style={{
                    fontFamily: FONTS.mono,
                    fontSize: fs.bodySmall,
                    fontWeight: FW.heavy,
                    color: COLORS.text,
                  }}
                >
                  {arc.pct}%
                </span>
                <span
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: fs.bodySmall,
                    fontWeight: FW.semibold,
                    color: COLORS.textSecondary,
                  }}
                >
                  {arc.label}
                </span>
              </div>
              {concern && (
                <span
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: fs.caption,
                    fontWeight: FW.medium,
                    color: COLORS.textTertiary,
                    lineHeight: 1.4,
                    paddingLeft: 18,
                    maxWidth: 240,
                    overflowWrap: "anywhere",
                    wordBreak: "break-word",
                  }}
                >
                  {concern}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

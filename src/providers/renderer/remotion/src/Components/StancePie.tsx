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
  quotedStances?: string[];
}> = ({ distribution, size, centerLabel, stanceConcerns, quotedStances }) => {
  const frame = useCurrentFrame();
  const { fs, scaled } = useDesign();
  const pad = scaled(8);
  const svgSize = size + pad * 2;
  const cx = svgSize / 2;
  const cy = svgSize / 2;
  const outerR = size / 2 - scaled(4);
  const innerR = outerR * 0.55;
  const entries = Object.entries(distribution).filter(([, v]) => v > 0);
  const quotedSet = new Set(quotedStances ?? []);
  const hasUnquoted = quotedSet.size > 0 && entries.some(([label]) => !quotedSet.has(label));

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
    const quoted = quotedSet.size === 0 || quotedSet.has(label);

    return { label, value, path, color, pct, idx, quoted };
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
              fillOpacity={arc.quoted ? 1 : 0.42}
              stroke={COLORS.bgStroke}
              strokeWidth={scaled(1.5)}
              strokeDasharray={arc.quoted ? undefined : `${scaled(4)} ${scaled(3)}`}
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

      {/* Legend below — one stance per row, single-line concern note */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: scaled(6),
          marginTop: scaled(12),
          maxWidth: svgSize + scaled(80),
        }}
      >
        {arcs.map((arc) => {
          const concern = stanceConcerns?.[arc.label];
          return (
            <div
              key={`legend-${arc.idx}`}
              style={{
                display: "flex",
                alignItems: "center",
                gap: scaled(6),
                minWidth: 0,
              }}
            >
              <span
                style={{
                  width: scaled(10),
                  height: scaled(10),
                  borderRadius: scaled(2),
                  backgroundColor: arc.color,
                  opacity: arc.quoted ? 1 : 0.42,
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  fontFamily: FONTS.mono,
                  fontSize: fs.bodySmall,
                  fontWeight: FW.heavy,
                  color: COLORS.text,
                  flexShrink: 0,
                  minWidth: scaled(36),
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
                  flexShrink: 0,
                }}
              >
                {arc.label}
              </span>
              {concern && (
                <span
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: fs.caption,
                    fontWeight: FW.medium,
                    color: COLORS.textTertiary,
                    letterSpacing: 0.2,
                    overflow: "hidden",
                    whiteSpace: "nowrap",
                    textOverflow: "ellipsis",
                    flex: 1,
                    minWidth: 0,
                  }}
                >
                  · {concern}
                </span>
              )}
              {!arc.quoted && (
                <span
                  style={{
                    fontFamily: FONTS.sans,
                    fontSize: fs.caption,
                    fontWeight: FW.medium,
                    color: COLORS.textTertiary,
                    letterSpacing: 0.2,
                    flexShrink: 0,
                  }}
                >
                  未采纳
                </span>
              )}
            </div>
          );
        })}
      </div>
      {hasUnquoted && (
        <div
          style={{
            marginTop: scaled(10),
            fontFamily: FONTS.sans,
            fontSize: fs.caption,
            fontWeight: FW.medium,
            color: COLORS.textTertiary,
            letterSpacing: 0.2,
            textAlign: "center",
            maxWidth: svgSize,
          }}
        >
          引述按信息增量挑选
        </div>
      )}
    </div>
  );
};

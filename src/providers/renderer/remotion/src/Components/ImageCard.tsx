import React from "react";

import { ElementProps, p, truncate } from "./utils";
import { COLORS, FONTS, SHADOWS, S } from "./design";

export const ImageCard: React.FC<ElementProps> = ({ elementProps, width, height }) => {
  const imageSrc = p(elementProps, "image_src", "");
  const caption = p(elementProps, "caption", "");

  if (!imageSrc) return null;

  const pad = 80;
  const cardW = width - pad * 2;
  const cardH = Math.floor(height * 0.55);
  const topY = Math.floor(height * 0.15);

  return (
    <div style={{
      ...S, left: pad, top: topY, width: cardW, height: cardH,
      borderRadius: 24, overflow: "hidden",
      border: `1px solid ${COLORS.border}`,
      boxShadow: SHADOWS.card,
    }}>
      <img
        src={imageSrc}
        alt={caption}
        style={{
          width: "100%", height: "100%",
          objectFit: "cover" as const,
        }}
      />
      {caption && (
        <div style={{
          position: "absolute" as const, bottom: 0, left: 0, right: 0,
          background: "linear-gradient(to top, rgba(0,0,0,0.65) 0%, rgba(0,0,0,0.35) 60%, transparent 100%)",
          padding: "40px 28px 20px",
          fontFamily: FONTS.sans, fontSize: 24, color: "#ffffff",
          lineHeight: 1.4,
          fontWeight: 500,
        }}>
          {truncate(caption, 80)}
        </div>
      )}
    </div>
  );
};

import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate } from "remotion";

import { ElementProps, p, truncate } from "./utils";
import { COLORS, FONTS, SHADOWS, S } from "./design";

export const ImageCard: React.FC<ElementProps> = ({ elementProps, width, height, duration }) => {
  const imageSrc = p(elementProps, "image_src", "");
  const caption = p(elementProps, "caption", "");
  const imageType = p(elementProps, "image_type", "article");
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (!imageSrc) return null;

  const pad = 80;
  const cardW = width - pad * 2;
  const cardH = Math.floor(height * 0.55);
  const topY = Math.floor(height * 0.15);

  // Fade-out: start fading at 70% of duration, fully transparent at 95%
  const totalFrames = Math.max(1, Math.round((duration || 2.5) * fps));
  const fadeOut = interpolate(
    frame,
    [Math.floor(totalFrames * 0.7), Math.floor(totalFrames * 0.95)],
    [1, 0],
    { extrapolateLeft: "clamp" as const, extrapolateRight: "clamp" as const }
  );

  const isLogo = imageType === "logo";

  return (
    <div style={{
      ...S, left: pad, top: topY, width: cardW, height: cardH,
      borderRadius: 24, overflow: "hidden",
      border: `1px solid ${COLORS.border}`,
      boxShadow: SHADOWS.card,
      opacity: fadeOut,
    }}>
      {isLogo ? (
        <div style={{
          width: "100%", height: "100%",
          background: "linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <img
            src={imageSrc}
            alt={caption}
            style={{
              width: "40%", height: "40%",
              objectFit: "contain" as const,
              borderRadius: 16,
            }}
          />
        </div>
      ) : (
        <img
          src={imageSrc}
          alt={caption}
          style={{
            width: "100%", height: "100%",
            objectFit: "cover" as const,
          }}
        />
      )}
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

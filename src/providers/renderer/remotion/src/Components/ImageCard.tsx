import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing, staticFile } from "remotion";

import { ElementProps, p, truncate } from "./utils";
import { COLORS, FONTS, glassCardShadow, S } from "./design";

export const ImageCard: React.FC<ElementProps> = ({ elementProps, width, height, duration }) => {
  const imageSrc = p(elementProps, "image_src", "");
  const caption = p(elementProps, "caption", "");
  const imageType = p<string>(elementProps, "image_type", "article");
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const resolvedSrc = imageSrc ? staticFile(imageSrc) : "";

  if (!imageSrc) return null;

  const pad = 80;
  const cardW = width - pad * 2;
  const cardH = Math.floor(height * 0.55);
  const topY = Math.floor(height * 0.15);

  const totalFrames = Math.max(1, Math.round((duration || 2.5) * fps));
  const fadeIn = interpolate(frame, [0, 12], [0, 1], {
    easing: Easing.bezier(0.16, 1, 0.3, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
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
      borderRadius: 14, overflow: "hidden",
      border: "none",
      boxShadow: glassCardShadow,
      opacity: fadeIn * fadeOut,
    }}>
      {isLogo ? (
        <div style={{
          width: "100%", height: "100%",
          background: "rgba(255,255,255,0.04)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <img
            src={resolvedSrc}
            alt={caption}
            style={{
              width: "40%", height: "40%",
              objectFit: "contain" as const,
              borderRadius: 4,
            }}
          />
        </div>
      ) : (
        <img
          src={resolvedSrc}
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
          background: "linear-gradient(to top, rgba(13,13,15,0.92) 0%, rgba(13,13,15,0.65) 60%, transparent 100%)",
          padding: "40px 28px 20px",
          fontFamily: FONTS.sans, fontSize: 24, color: COLORS.text,
          lineHeight: 1.4,
          fontWeight: 500,
          opacity: interpolate(frame, [8, 22], [0, 1], {
            easing: Easing.bezier(0.16, 1, 0.3, 1),
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}>
          {truncate(caption, 80)}
        </div>
      )}
    </div>
  );
};

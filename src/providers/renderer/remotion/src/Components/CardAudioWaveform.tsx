/* ================================================================
   CardAudioWaveform — 卡片音频波形共用组件
   ================================================================

   共用组件，用于在卡片底部显示音频波形。
   所有卡片统一使用此组件，方便维护。
*/

import React from "react";
import { AudioWaveform } from "./AudioWaveform";
import { COLORS, useDesign } from "./design";

interface CardAudioWaveformProps {
  src?: string;
}

export const CardAudioWaveform: React.FC<CardAudioWaveformProps> = ({ src }) => {
  const d = useDesign();

  return (
    <AudioWaveform
      src={src}
      barCount={64}
      barWidth={12}
      barGap={5}
      maxHeight={60}
      color={COLORS.warmGold}
      leftOffset={d.scaled(32)}
    />
  );
};

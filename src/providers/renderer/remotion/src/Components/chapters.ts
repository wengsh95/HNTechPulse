import React, { createContext } from "react";

export type ChapterName = "cover" | "focus" | "atmosphere" | "closing";

const ChapterContext = createContext<ChapterName>("focus");

export const ChapterProvider: React.FC<{
  chapter: ChapterName;
  children: React.ReactNode;
}> = ({ chapter, children }) =>
  React.createElement(ChapterContext.Provider, { value: chapter }, children);

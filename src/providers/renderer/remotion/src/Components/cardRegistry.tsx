import React from "react";

import type { SceneElementData } from "../types";
import { AtmosphereCard, ClosingCard, CoverCard, EventCard } from "./Elements";
import type { ChapterName } from "./design";

export type CardRendererProps = {
  elementProps: Record<string, unknown>;
  duration: number;
  width: number;
  height: number;
};

export type CardElementType = "cover_card" | "event_card" | "atmosphere_card" | "closing_card";

export type CardRegistryEntry = {
  component: React.FC<CardRendererProps>;
  chapter: ChapterName;
  marksStory?: boolean;
};

export const CARD_REGISTRY = {
  cover_card: {
    component: (props) => <CoverCard {...props} />,
    chapter: "cover",
  },
  event_card: {
    component: (props) => <EventCard {...props} />,
    chapter: "focus",
    marksStory: true,
  },
  atmosphere_card: {
    component: (props) => <AtmosphereCard {...props} />,
    chapter: "atmosphere",
  },
  closing_card: {
    component: (props) => <ClosingCard {...props} />,
    chapter: "closing",
  },
} satisfies Record<CardElementType, CardRegistryEntry>;

export const getCardRegistryEntry = (elementType: string): CardRegistryEntry | undefined =>
  CARD_REGISTRY[elementType as CardElementType];

export const isStoryMarkerElement = (element: SceneElementData): boolean =>
  Boolean(getCardRegistryEntry(element.element_type)?.marksStory);

export const cardChapterForElementType = (elementType: string): ChapterName =>
  getCardRegistryEntry(elementType)?.chapter ?? "focus";

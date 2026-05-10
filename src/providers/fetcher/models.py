from dataclasses import dataclass
from typing import Optional


@dataclass
class HNStory:
    id: int
    title: str
    url: Optional[str]
    score: int
    descendants: int
    time: int
    text: Optional[str]
    by: Optional[str] = None


@dataclass
class HNComment:
    id: int
    author: str
    text: str
    time: int
    score: Optional[int] = None
    depth: Optional[int] = None

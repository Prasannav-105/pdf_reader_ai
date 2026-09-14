"""
Data models and schemas for AI Textbook Reader.
"""
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
import json

@dataclass
class SectionMetadata:
    book_id: str
    book_name: str
    unit: str = "General"
    chapter: str = "Chapter 1"
    section: str = "Overview"
    topic_title: str = ""
    start_page: int = 1
    end_page: int = 1
    chunk_index: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SectionMetadata':
        return cls(**data)

@dataclass
class TextbookChunk:
    chunk_id: str
    metadata: SectionMetadata
    original_text: str
    word_count: int = 0

    def __post_init__(self):
        if not self.word_count and self.original_text:
            self.word_count = len(self.original_text.split())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['metadata'] = self.metadata.to_dict()
        return d

@dataclass
class HierarchicalNode:
    node_id: str
    title: str
    level: str  # "unit", "chapter", "section", "subsection"
    start_page: int
    end_page: int
    children: List['HierarchicalNode'] = field(default_factory=list)
    chunk_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "title": self.title,
            "level": self.level,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "children": [c.to_dict() for c in self.children],
            "chunk_ids": self.chunk_ids
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'HierarchicalNode':
        children = [cls.from_dict(c) for c in d.get("children", [])]
        return cls(
            node_id=d["node_id"],
            title=d["title"],
            level=d["level"],
            start_page=d["start_page"],
            end_page=d["end_page"],
            children=children,
            chunk_ids=d.get("chunk_ids", [])
        )

@dataclass
class BookHierarchy:
    book_id: str
    book_name: str
    total_pages: int
    root_nodes: List[HierarchicalNode] = field(default_factory=list)
    total_sections: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "book_id": self.book_id,
            "book_name": self.book_name,
            "total_pages": self.total_pages,
            "root_nodes": [n.to_dict() for n in self.root_nodes],
            "total_sections": self.total_sections
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'BookHierarchy':
        return cls(
            book_id=d["book_id"],
            book_name=d["book_name"],
            total_pages=d["total_pages"],
            root_nodes=[HierarchicalNode.from_dict(n) for n in d.get("root_nodes", [])],
            total_sections=d.get("total_sections", 0)
        )

@dataclass
class MCQuestion:
    question: str
    options: List[str]  # ["A) ...", "B) ...", "C) ...", "D) ..."]
    correct_option: str  # "A", "B", "C", or "D"
    explanation: str
    page_reference: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'MCQuestion':
        return cls(**d)

@dataclass
class ShortQuestion:
    question: str
    model_answer: str
    key_points: List[str]
    page_reference: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ShortQuestion':
        return cls(**d)

@dataclass
class SectionLesson:
    book_name: str
    unit: str
    chapter: str
    section: str
    page_range: str
    teaching_content: str
    verbatim_quote: str = ""
    verbatim_page: int = 1
    mermaid_diagram: str = ""
    key_points: List[str] = field(default_factory=list)
    mcqs: List[MCQuestion] = field(default_factory=list)
    short_questions: List[ShortQuestion] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['mcqs'] = [m.to_dict() for m in self.mcqs]
        d['short_questions'] = [s.to_dict() for s in self.short_questions]
        return d

@dataclass
class UserNote:
    id: Optional[int]
    user_id: str
    book_id: str
    chapter: str
    section: str
    page_number: int
    note_text: str
    created_at: str

@dataclass
class UserHighlight:
    id: Optional[int]
    user_id: str
    book_id: str
    chapter: str
    section: str
    page_number: int
    highlight_text: str
    color: str = "yellow"
    created_at: str = ""

@dataclass
class UserBookmark:
    id: Optional[int]
    user_id: str
    book_id: str
    chapter: str
    section: str
    page_number: int
    title: str
    created_at: str

@dataclass
class ReadingProgress:
    user_id: str
    book_id: str
    last_chapter: str
    last_section: str
    last_page: int
    completed_sections: List[str] = field(default_factory=list)
    total_sections: int = 0
    quiz_scores: Dict[str, float] = field(default_factory=dict)

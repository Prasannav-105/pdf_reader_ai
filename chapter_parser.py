"""
chapter_parser.py: Hierarchical Knowledge Tree Builder.
Detects Units, Chapters, Sections, Subsections, and produces TextbookChunks.
"""
import os
import re
import json
import uuid
from typing import List, Dict, Tuple, Optional, Any
from models.schema import SectionMetadata, TextbookChunk, HierarchicalNode, BookHierarchy
from pdf_processor import PDFProcessor

class ChapterParser:
    """Builds hierarchical knowledge structures from textbooks."""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

    def parse_book(self, pdf_path: str, book_name: Optional[str] = None, force_reparse: bool = False) -> Tuple[BookHierarchy, List[TextbookChunk]]:
        """
        Parses a PDF into a BookHierarchy and a list of TextbookChunk objects.
        Uses persistent disk caching so 1000+ page books only parse once.
        """
        info = PDFProcessor.get_document_info(pdf_path)
        book_title = book_name or info["title"]
        # Generate stable book_id from filename
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', os.path.splitext(os.path.basename(pdf_path))[0])
        book_id = f"book_{safe_name}"

        cache_tree_path = os.path.join(self.data_dir, f"{book_id}_tree.json")
        cache_chunks_path = os.path.join(self.data_dir, f"{book_id}_chunks.json")

        if not force_reparse and os.path.exists(cache_tree_path) and os.path.exists(cache_chunks_path):
            try:
                with open(cache_tree_path, "r", encoding="utf-8") as f:
                    tree_dict = json.load(f)
                with open(cache_chunks_path, "r", encoding="utf-8") as f:
                    chunks_dict = json.load(f)
                
                hierarchy = BookHierarchy.from_dict(tree_dict)
                chunks = []
                for c in chunks_dict:
                    meta = SectionMetadata.from_dict(c["metadata"])
                    chunks.append(TextbookChunk(
                        chunk_id=c["chunk_id"],
                        metadata=meta,
                        original_text=c["original_text"],
                        word_count=c.get("word_count", 0)
                    ))
                return hierarchy, chunks
            except Exception:
                pass  # Corrupted cache, reparse

        # Perform parsing
        toc = PDFProcessor.extract_toc(pdf_path)
        total_pages = info["page_count"]

        if toc and len(toc) >= 3:
            hierarchy, chunks = self._parse_from_toc(pdf_path, book_id, book_title, toc, total_pages)
        else:
            hierarchy, chunks = self._parse_from_layout(pdf_path, book_id, book_title, total_pages)

        # Save to disk cache
        try:
            with open(cache_tree_path, "w", encoding="utf-8") as f:
                json.dump(hierarchy.to_dict(), f, indent=2, ensure_ascii=False)
            with open(cache_chunks_path, "w", encoding="utf-8") as f:
                json.dump([c.to_dict() for c in chunks], f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to cache book hierarchy: {e}")

        return hierarchy, chunks

    def _parse_from_toc(self, pdf_path: str, book_id: str, book_title: str, toc: List[Tuple[int, str, int]], total_pages: int) -> Tuple[BookHierarchy, List[TextbookChunk]]:
        """Builds hierarchy and chunks using the PDF Table of Contents."""
        # 1. Build tree nodes
        root_nodes: List[HierarchicalNode] = []
        node_stack: List[Tuple[int, HierarchicalNode]] = []  # (level, node)
        
        # Determine end_page for each TOC entry
        entries_with_range = []
        for i in range(len(toc)):
            lvl, title, start_p = toc[i]
            # End page is start of next entry at same or higher level, or total_pages
            end_p = total_pages
            for j in range(i + 1, len(toc)):
                next_lvl, _, next_start = toc[j]
                if next_start >= start_p:
                    end_p = max(start_p, next_start - 1)
                    break
            entries_with_range.append((lvl, title, start_p, end_p))

        # Build hierarchy tree
        total_sections = 0
        for lvl, title, s_page, e_page in entries_with_range:
            level_name = "unit" if lvl == 1 and len(toc) > 20 else ("chapter" if lvl <= 2 else "section")
            node_id = f"{book_id}_node_{uuid.uuid4().hex[:8]}"
            node = HierarchicalNode(
                node_id=node_id,
                title=title,
                level=level_name,
                start_page=s_page,
                end_page=e_page,
                children=[]
            )
            total_sections += 1

            # Adjust stack
            while node_stack and node_stack[-1][0] >= lvl:
                node_stack.pop()

            if not node_stack:
                root_nodes.append(node)
            else:
                node_stack[-1][1].children.append(node)

            node_stack.append((lvl, node))

        # 2. Extract and chunk text page-by-page mapping to active nodes
        chunks = self._chunk_document(pdf_path, book_id, book_title, entries_with_range, total_pages)
        hierarchy = BookHierarchy(
            book_id=book_id,
            book_name=book_title,
            total_pages=total_pages,
            root_nodes=root_nodes,
            total_sections=total_sections
        )
        return hierarchy, chunks

    def _parse_from_layout(self, pdf_path: str, book_id: str, book_title: str, total_pages: int) -> Tuple[BookHierarchy, List[TextbookChunk]]:
        """Fallback: Scans text headings using regex patterns and typography."""
        detected_sections = []
        current_unit = "Unit 1: Fundamentals"
        current_chapter = "Chapter 1"
        
        # Scan pages for headings
        for page_data in PDFProcessor.stream_page_text(pdf_path, 1, min(total_pages, 500)):
            p_num = page_data["page"]
            text = page_data["text"]

            for line in text.splitlines()[:6]:
                line = line.strip()
                if re.match(r'^(?:UNIT|PART)\s+[0-9IVXLCDM]+[:\s\-]+', line, re.I):
                    current_unit = line
                    detected_sections.append((1, line, p_num))
                    break
                elif re.match(r'^(?:CHAPTER|SECTION)\s+\d+[:\s\-]+', line, re.I):
                    current_chapter = line
                    detected_sections.append((2, line, p_num))
                    break
                elif re.match(r'^\d+\.\d+\s+[A-Z]', line):
                    detected_sections.append((3, line, p_num))
                    break

        if not detected_sections:
            # Synthetic 10-page chapters if completely unformatted
            for p in range(1, total_pages + 1, 15):
                chap_idx = (p // 15) + 1
                detected_sections.append((2, f"Chapter {chap_idx} (Pages {p}-{min(p+14, total_pages)})", p))

        # Convert to entries with range
        entries_with_range = []
        for i in range(len(detected_sections)):
            lvl, title, start_p = detected_sections[i]
            end_p = total_pages
            if i + 1 < len(detected_sections):
                end_p = max(start_p, detected_sections[i + 1][2] - 1)
            entries_with_range.append((lvl, title, start_p, end_p))

        root_nodes = []
        for lvl, title, s_page, e_page in entries_with_range:
            root_nodes.append(HierarchicalNode(
                node_id=f"{book_id}_node_{uuid.uuid4().hex[:8]}",
                title=title,
                level="chapter" if lvl <= 2 else "section",
                start_page=s_page,
                end_page=e_page,
                children=[]
            ))

        chunks = self._chunk_document(pdf_path, book_id, book_title, entries_with_range, total_pages)
        hierarchy = BookHierarchy(
            book_id=book_id,
            book_name=book_title,
            total_pages=total_pages,
            root_nodes=root_nodes,
            total_sections=len(root_nodes)
        )
        return hierarchy, chunks

    def _chunk_document(self, pdf_path: str, book_id: str, book_title: str, entries_with_range: List[Tuple[int, str, int, int]], total_pages: int) -> List[TextbookChunk]:
        """Creates 500-1000 word semantic chunks with attached metadata."""
        chunks: List[TextbookChunk] = []
        chunk_idx = 0

        # Helper to find active TOC entry for a given page
        def find_entry(page_num: int):
            matched = None
            for item in entries_with_range:
                _, title, s, e = item
                if s <= page_num <= e:
                    matched = item
            return matched or (2, "General Content", 1, total_pages)

        # Stream pages and group into chunks
        current_text = ""
        chunk_start_page = 1
        current_entry = None

        for page_data in PDFProcessor.stream_page_text(pdf_path, 1, total_pages):
            p_num = page_data["page"]
            text = page_data["text"]
            entry = find_entry(p_num)

            # If section changed and we have existing content, flush chunk
            if current_entry and entry != current_entry and len(current_text.split()) > 200:
                chunk_idx += 1
                _, entry_title, _, _ = current_entry
                meta = SectionMetadata(
                    book_id=book_id,
                    book_name=book_title,
                    unit="Textbook",
                    chapter=entry_title,
                    section=entry_title,
                    topic_title=entry_title,
                    start_page=chunk_start_page,
                    end_page=p_num - 1,
                    chunk_index=chunk_idx
                )
                chunks.append(TextbookChunk(
                    chunk_id=f"{book_id}_chunk_{chunk_idx:04d}",
                    metadata=meta,
                    original_text=current_text.strip()
                ))
                current_text = ""
                chunk_start_page = p_num

            if not current_text:
                chunk_start_page = p_num
            current_entry = entry
            current_text += f"\n\n[Page {p_num}]\n" + text

            # Flush if word count exceeds optimal chunk window (500 - 900 words)
            if len(current_text.split()) >= 700:
                chunk_idx += 1
                _, entry_title, _, _ = current_entry
                meta = SectionMetadata(
                    book_id=book_id,
                    book_name=book_title,
                    unit="Textbook",
                    chapter=entry_title,
                    section=f"{entry_title} (Part {chunk_idx})",
                    topic_title=entry_title,
                    start_page=chunk_start_page,
                    end_page=p_num,
                    chunk_index=chunk_idx
                )
                chunks.append(TextbookChunk(
                    chunk_id=f"{book_id}_chunk_{chunk_idx:04d}",
                    metadata=meta,
                    original_text=current_text.strip()
                ))
                current_text = ""
                chunk_start_page = p_num + 1

        # Flush remaining text
        if current_text.strip():
            chunk_idx += 1
            entry_title = current_entry[1] if current_entry else "Conclusion"
            meta = SectionMetadata(
                book_id=book_id,
                book_name=book_title,
                unit="Textbook",
                chapter=entry_title,
                section=entry_title,
                topic_title=entry_title,
                start_page=chunk_start_page,
                end_page=total_pages,
                chunk_index=chunk_idx
            )
            chunks.append(TextbookChunk(
                chunk_id=f"{book_id}_chunk_{chunk_idx:04d}",
                metadata=meta,
                original_text=current_text.strip()
            ))

        return chunks

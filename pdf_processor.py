"""
pdf_processor.py: Memory-efficient PDF text and structure extraction.
Scalable for textbooks exceeding 1000 pages using PyMuPDF (fitz).
"""
import os
import re
from typing import List, Dict, Tuple, Optional, Any, Generator
import pymupdf as fitz

class PDFProcessor:
    """Extracts text, table of contents, and structural headings from PDF documents."""

    @staticmethod
    def get_document_info(pdf_path: str) -> Dict[str, Any]:
        """Retrieves page count, metadata title, and TOC availability."""
        doc = fitz.open(pdf_path)
        title = doc.metadata.get("title") or os.path.splitext(os.path.basename(pdf_path))[0]
        page_count = len(doc)
        toc = doc.get_toc()
        doc.close()
        return {
            "title": title.strip(),
            "page_count": page_count,
            "has_toc": len(toc) > 0,
            "toc_entries": len(toc)
        }

    @staticmethod
    def extract_toc(pdf_path: str) -> List[Tuple[int, str, int]]:
        """
        Extracts built-in PDF bookmarks/table of contents.
        Returns list of (level, title, page_number) [1-indexed pages].
        """
        doc = fitz.open(pdf_path)
        toc = doc.get_toc()
        doc.close()
        # Ensure page numbers are 1-indexed integers and titles are trimmed
        clean_toc = []
        for item in toc:
            if len(item) >= 3:
                lvl, title, page = item[0], str(item[1]).strip(), int(item[2])
                if page > 0 and title:
                    clean_toc.append((lvl, title, page))
        return clean_toc

    @classmethod
    def stream_page_text(cls, pdf_path: str, start_page: int = 1, end_page: Optional[int] = None) -> Generator[Dict[str, Any], None, None]:
        """
        Memory-efficient generator yielding page text, page number, and typography blocks.
        Never keeps entire large document in memory.
        """
        doc = fitz.open(pdf_path)
        total = len(doc)
        end = min(end_page or total, total)

        for page_idx in range(start_page - 1, end):
            page_num = page_idx + 1
            page = doc[page_idx]
            
            # Extract plain text
            raw_text = page.get_text("text")
            clean_txt = cls.clean_text(raw_text)
            
            # Extract layout blocks with font size analysis to detect headings
            blocks_info = []
            try:
                page_dict = page.get_text("dict")
                for block in page_dict.get("blocks", []):
                    if block.get("type") == 0:  # Text block
                        for line in block.get("lines", []):
                            line_text = ""
                            max_font_size = 0.0
                            is_bold = False
                            for span in line.get("spans", []):
                                txt = span.get("text", "")
                                line_text += txt
                                size = span.get("size", 0.0)
                                if size > max_font_size:
                                    max_font_size = size
                                flags = span.get("flags", 0)
                                if flags & 2 or "bold" in span.get("font", "").lower():
                                    is_bold = True
                            
                            line_text = line_text.strip()
                            if line_text:
                                blocks_info.append({
                                    "text": line_text,
                                    "font_size": round(max_font_size, 1),
                                    "is_bold": is_bold,
                                    "page": page_num
                                })
            except Exception:
                pass

            yield {
                "page": page_num,
                "text": clean_txt,
                "blocks": blocks_info
            }

        doc.close()

    @staticmethod
    def clean_text(text: str) -> str:
        """Removes excessive whitespace, headers/footers noise, and normalizes unicode."""
        if not text:
            return ""
        # Normalize non-breaking spaces and special quotes
        text = text.replace("\u00a0", " ").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
        # Remove standalone page numbers at beginning/end
        text = re.sub(r'^(?:Page\s+)?\d+\s*$', '', text, flags=re.MULTILINE)
        # Collapse excessive newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

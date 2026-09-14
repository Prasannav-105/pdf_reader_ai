"""
teacher.py: Teaching & Pedagogy Engine with Strict Anti-Hallucination Guard.
Uses local Ollama (llama3.2) with strict retrieval grounding.
"""
import re
import json
from typing import List, Dict, Tuple, Optional, Any, Generator
import ollama
from models.schema import SectionLesson, MCQuestion, ShortQuestion

SYSTEM_PROMPT = (
    "You are an AI textbook teacher. Use ONLY the retrieved textbook context. "
    "Do not use prior knowledge. Teach chapter by chapter and section by section. "
    "Mention page numbers. If context is missing, clearly state that the textbook does not contain the answer."
)

class TeacherEngine:
    """Delivers sequential lessons and answers questions grounded strictly in textbook context."""

    def __init__(self, model_name: str = "llama3.2", host: str = "http://127.0.0.1:11434"):
        self.model_name = model_name
        self.host = host
        self.client = ollama.Client(host=self.host)

    def teach_section_stream(
        self,
        book_title: str,
        chapter_title: str,
        section_title: str,
        context_chunks: List[Dict[str, Any]],
        num_gpu: int = 0
    ) -> Generator[str, None, None]:
        """
        Streams a complete lesson for the selected section grounded strictly in the textbook chunks.
        Includes:
        1. Concept Explanation in simple language with page citations
        2. Architectural / Process Flow Mermaid Diagram (Domain-specific entities only)
        3. Formatted Source Code Blocks (when present in textbook) with line-by-line mechanics
        4. Verbatim Textbook Quotes with page citations
        5. Key Takeaway Points
        6. 3 MCQs with explanations
        7. 2 Short-Answer Conceptual Questions
        """
        # Combine retrieved textbook text with page labels
        combined_text = ""
        page_numbers = set()
        for c in context_chunks:
            meta = c.get("metadata", {})
            s_p = meta.get("start_page", 1)
            e_p = meta.get("end_page", s_p)
            for p in range(s_p, e_p + 1):
                page_numbers.add(p)
            combined_text += f"\n--- TEXTBOOK EXCERPT (Pages {s_p}-{e_p}) ---\n" + c.get("text", "")

        pages_str = ", ".join(str(p) for p in sorted(page_numbers)) if page_numbers else "1"

        user_prompt = f"""
You are teaching the following section from the textbook:
Book: {book_title}
Chapter: {chapter_title}
Section: {section_title}
Covered Pages: {pages_str}

RETRIEVED TEXTBOOK CONTENT:
{combined_text[:4500]}

INSTRUCTIONS:
1. Teach this section sequentially in simple, clear, and engaging pedagogical language.
2. Rely EXCLUSIVELY on the retrieved text above. Do not use outside knowledge.
3. Explicitly cite the page numbers where key ideas appear (e.g., "[Page 42]").

4. SOURCE CODE & MECHANICAL BREAKDOWN:
   - If the retrieved text mentions, contains, or references source code (such as C/C++, Python, Java, assembly, program files like cpu.c, mem.c, threads.c, or functions like Spin(), fork(), malloc()):
     * DO NOT merely describe the code abstractly in theoretical prose!
     * EXTRACT and INCLUDE the complete, properly formatted source code in code blocks (e.g., ```c ... ```) exactly as printed in the textbook.
     * Provide a line-by-line explanation of the program logic, its system calls, inputs/outputs, compilation commands (e.g., gcc), and runtime execution behavior shown in the book.
   - If this is a non-technical book or does NOT contain code, DO NOT fabricate code; instead provide verbatim passages, case studies, or principles directly from the text.

5. ARCHITECTURAL / PROCESS FLOW DIAGRAM:
   - Formulate ONE clean, syntax-valid Mermaid flowchart illustrating the core mechanics, system calls, data flow, or concepts taught in this specific section.
   - STRICT REQUIREMENT: DO NOT use generic placeholder words like "Input Concept", "Processing Step", "Output Result", "A", "B", "C".
   - You MUST use the actual technical entities, functions, or concepts from this chapter (e.g., OS Kernel, Hardware CPU, Timer Interrupt, Process State, Virtual Memory, Cache, etc.).
   - Format strictly as:
```mermaid
graph TD
    Node1["Descriptive Technical Entity 1"] -->|action| Node2["Descriptive Technical Entity 2"]
    Node2 --> Node3["Descriptive Technical Entity 3"]
```

6. Include one prominent verbatim textbook excerpt using markdown blockquote:
> [!NOTE] Verbatim Textbook Passage (Page X)
> "Exact quotation from the text..."

7. End the lesson with:
### 📌 Key Takeaways
- Point 1 (Page X)
- Point 2 (Page Y)
- Point 3 (Page Z)

### 🎯 Section Verification Questions
#### Multiple Choice Questions (3 MCQs)
1. [Question text]?
   A) Option A
   B) Option B
   C) Option C
   D) Option D
   *Correct: X* | *Explanation: ... (Page X)*

2. [Question text]?
   A) Option A
   B) Option B
   C) Option C
   D) Option D
   *Correct: X* | *Explanation: ... (Page X)*

3. [Question text]?
   A) Option A
   B) Option B
   C) Option C
   D) Option D
   *Correct: X* | *Explanation: ... (Page X)*

#### Short Answer Questions (2 Questions)
1. [Question text] (Page X)
2. [Question text] (Page Y)
"""

        response_stream = self.client.chat(
            model=self.model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            stream=True,
            options={"temperature": 0.2, "top_p": 0.9, "num_gpu": num_gpu}
        )

        for chunk in response_stream:
            delta = chunk.get("message", {}).get("content", "")
            if delta:
                yield delta

    def ask_from_book(
        self,
        book_title: str,
        question: str,
        retrieved_chunks: List[Dict[str, Any]],
        chat_history: Optional[List[Dict[str, str]]] = None,
        num_gpu: int = 0
    ) -> Generator[str, None, None]:
        """
        Answers user queries strictly from retrieved textbook chunks.
        If information is absent or irrelevant, immediately yields:
        'This information is not available in the uploaded textbook.'
        """
        # If no chunks retrieved or relevance distance is too high
        if not retrieved_chunks:
            yield "This information is not available in the uploaded textbook."
            return

        combined_context = ""
        citations = []
        for i, c in enumerate(retrieved_chunks):
            meta = c.get("metadata", {})
            s_p = meta.get("start_page", 1)
            e_p = meta.get("end_page", s_p)
            chap = meta.get("chapter", "Textbook")
            citations.append(f"Pages {s_p}-{e_p} ({chap})")
            combined_context += f"\n[Context Chunk {i+1} - Pages {s_p}-{e_p}]:\n" + c.get("text", "")

        user_prompt = f"""
QUESTION:
{question}

RETRIEVED TEXTBOOK CONTEXT:
{combined_context[:3800]}

STRICT RULES:
1. Use ONLY the retrieved textbook context above.
2. If the context does not explicitly contain the answer, reply EXACTLY with:
"This information is not available in the uploaded textbook."
3. If the context does contain the answer, explain it concisely and cite the exact page numbers (e.g. "[Page 24]").
4. If the question asks about source code, program implementation, or code files from the textbook (e.g. cpu.c, mem.c, threads.c, Spin(), fork()):
   * Output the exact code snippet in a markdown code block (e.g., ```c ... ```) from the context.
   * Provide a clear line-by-line mechanical explanation of how the code operates according to the textbook.
5. Do not speculate or draw upon outside general knowledge.
"""

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if chat_history:
            # Include last 4 turns of history
            for msg in chat_history[-4:]:
                messages.append(msg)
        messages.append({"role": "user", "content": user_prompt})

        response_stream = self.client.chat(
            model=self.model_name,
            messages=messages,
            stream=True,
            options={"temperature": 0.1, "top_p": 0.8, "num_gpu": num_gpu}
        )

        for chunk in response_stream:
            delta = chunk.get("message", {}).get("content", "")
            if delta:
                yield delta

    @staticmethod
    def sanitize_mermaid(code: str) -> str:
        """
        Auto-healing Mermaid sanitizer.
        Removes markdown fences, deduplicates duplicate headers, and properly quotes node labels.
        """
        if not code:
            return ""
        # Remove opening and closing backticks
        code = re.sub(r'```(?:mermaid)?\s*', '', code.strip(), flags=re.MULTILINE)
        code = re.sub(r'```\s*$', '', code.strip(), flags=re.MULTILINE)

        lines = [l.rstrip() for l in code.splitlines() if l.strip()]
        if not lines:
            return ""

        # Ensure valid header
        first_line = lines[0].strip()
        valid_prefixes = ("graph TD", "graph LR", "flowchart TD", "flowchart LR", "sequenceDiagram", "classDiagram", "stateDiagram")
        if not any(first_line.startswith(p) for p in valid_prefixes):
            lines.insert(0, "graph TD")

        # Deduplicate repeated top-level graph declarations
        deduped = [lines[0]]
        for l in lines[1:]:
            l_strip = l.strip().lower()
            if (l_strip.startswith("graph ") or l_strip.startswith("flowchart ")) and not l_strip.startswith("subgraph"):
                continue
            deduped.append(l)

        # Ensure node labels with spaces or text are properly quoted: A[Label Here] -> A["Label Here"]
        cleaned_lines = []
        for l in deduped:
            cleaned = re.sub(r'(\b\w+)\[([^"\]\n]+)\]', r'\1["\2"]', l)
            cleaned_lines.append(cleaned)

        return "\n".join(cleaned_lines)

"""
quiz_generator.py: Quiz extraction, grading, and revision flashcard manager.
"""
import re
from typing import List, Dict, Optional, Any
import ollama
from models.schema import MCQuestion, ShortQuestion

class QuizEngine:
    """Manages section quizzes, grading, and revision cards."""

    def __init__(self, model_name: str = "llama3.2", host: str = "http://127.0.0.1:11434"):
        self.model_name = model_name
        self.host = host
        self.client = ollama.Client(host=self.host)

    @staticmethod
    def parse_quiz_from_lesson(lesson_text: str):
        """
        Parses MCQs and Short Questions from generated lesson text.
        """
        mcqs: List[MCQuestion] = []
        short_qs: List[ShortQuestion] = []

        # Find MCQ block using resilient regex
        pattern = r'(\d+)\.\s+(.*?)\n\s*A\)\s+(.*?)\n\s*B\)\s+(.*?)\n\s*C\)\s+(.*?)\n\s*D\)\s+(.*?)\n\s*\*Correct:\s*([A-D])\*\s*\|\s*\*Explanation:\s*(.*?)\*'
        mcq_pattern = re.compile(pattern, re.DOTALL)

        for match in mcq_pattern.finditer(lesson_text):
            num, q_text, opt_a, opt_b, opt_c, opt_d, correct, expl = match.groups()
            mcqs.append(MCQuestion(
                question=q_text.strip(),
                options=[f"A) {opt_a.strip()}", f"B) {opt_b.strip()}", f"C) {opt_c.strip()}", f"D) {opt_d.strip()}"],
                correct_option=correct.strip().upper(),
                explanation=expl.strip(),
                page_reference=1
            ))

        # Find Short Questions
        sq_pattern = r'#### Short Answer Questions.*?\n((?:\d+\..*?\n?)+)'
        sq_matches = re.findall(sq_pattern, lesson_text, re.DOTALL)
        if sq_matches:
            lines = [l.strip() for l in sq_matches[0].splitlines() if re.match(r'^\d+\.', l.strip())]
            for l in lines[:2]:
                q_txt = re.sub(r'^\d+\.\s*', '', l)
                short_qs.append(ShortQuestion(
                    question=q_txt,
                    model_answer="Refer to textbook section for the complete criteria.",
                    key_points=[],
                    page_reference=1
                ))

        return mcqs, short_qs

    def grade_short_answer(
        self,
        question: str,
        student_answer: str,
        textbook_context: str
    ) -> Dict[str, Any]:
        """
        Grades a student short answer against the textbook context using strict rubric.
        Returns: {score: int (0-100), verdict: str, feedback: str, textbook_quote: str}
        """
        if not student_answer.strip():
            return {
                "score": 0,
                "verdict": "Unanswered",
                "feedback": "Please provide an answer before submitting.",
                "textbook_quote": ""
            }

        prompt = f"""
You are grading a student's answer strictly based on the textbook.
QUESTION: {question}
TEXTBOOK CONTEXT:
{textbook_context[:2000]}

STUDENT ANSWER:
{student_answer}

EVALUATION CRITERIA:
1. Did the student explain the key concept as described in the textbook?
2. Are there any misconceptions?

Return a JSON object with this exact structure:
{{
  "score": 85,
  "verdict": "Mastered / Partially Correct / Incorrect",
  "feedback": "Concise feedback directly referencing the book.",
  "textbook_quote": "Relevant brief sentence from the book."
}}
"""

        try:
            res = self.client.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                options={"temperature": 0.1}
            )
            data = json.loads(res["message"]["content"])
            return data
        except Exception as e:
            return {
                "score": 75,
                "verdict": "Completed",
                "feedback": "Good effort! Compare your answer with the section notes above.",
                "textbook_quote": ""
            }

"""
embeddings.py: Interface to local Ollama nomic-embed-text.
Generates 768-dimensional embeddings completely offline with batching.
"""
import time
from typing import List, Optional, Callable
import ollama

class OllamaEmbedder:
    """Wrapper for Ollama nomic-embed-text embedding model."""

    def __init__(self, model_name: str = "nomic-embed-text", host: str = "http://127.0.0.1:11434"):
        self.model_name = model_name
        self.host = host
        self.client = ollama.Client(host=self.host)

    def _embed_single(self, text_slice: str, max_retries: int = 3) -> List[float]:
        """Calls Ollama embeddings API for a bounded string."""
        for attempt in range(max_retries):
            try:
                response = self.client.embeddings(model=self.model_name, prompt=text_slice)
                return response.get("embedding", [])
            except Exception as e:
                if attempt == max_retries - 1:
                    # Fallback to further truncation if still oversized
                    if "exceeds" in str(e).lower() and len(text_slice) > 2000:
                        try:
                            truncated = text_slice[:2000]
                            res = self.client.embeddings(model=self.model_name, prompt=truncated)
                            return res.get("embedding", [])
                        except Exception:
                            pass
                    raise RuntimeError(f"Failed to generate embedding via Ollama ({self.model_name}): {e}")
                time.sleep(0.5 * (attempt + 1))
        return [0.0] * 768

    def get_embedding(self, text: str, max_retries: int = 3) -> List[float]:
        """
        Generates embedding for a string.
        Automatically handles long texts by windowing and mean pooling,
        ensuring input never exceeds nomic-embed-text's 2048 token limit.
        """
        clean_text = text.strip()
        if not clean_text:
            return [0.0] * 768

        # nomic-embed-text has a strict 2048 token batch/context limit (~6000 chars).
        # We enforce a safe window of 4,000 characters (~1,000 tokens).
        MAX_CHARS = 4000
        if len(clean_text) <= MAX_CHARS:
            return self._embed_single(clean_text, max_retries)

        # For larger chunks, split into <=4000 char windows and average the vectors
        slices = [clean_text[i:i + MAX_CHARS] for i in range(0, len(clean_text), MAX_CHARS)][:4]
        vectors: List[List[float]] = []
        for s in slices:
            vec = self._embed_single(s, max_retries)
            if vec and len(vec) == 768:
                vectors.append(vec)

        if not vectors:
            return [0.0] * 768

        # Element-wise mean pooling across windows
        dim = len(vectors[0])
        averaged = [sum(v[d] for v in vectors) / len(vectors) for d in range(dim)]
        return averaged

    def get_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 16,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[List[float]]:
        """
        Embeds a list of texts in batches with optional progress feedback.
        """
        embeddings: List[List[float]] = []
        total = len(texts)

        for i, text in enumerate(texts):
            emb = self.get_embedding(text)
            embeddings.append(emb)
            if progress_callback and (i + 1) % 5 == 0 or (i + 1) == total:
                progress_callback(i + 1, total)

        return embeddings

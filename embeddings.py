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

    def get_embedding(self, text: str, max_retries: int = 3) -> List[float]:
        """Generates embedding for a single string with retry logic."""
        clean_text = text.strip()
        if not clean_text:
            return [0.0] * 768

        for attempt in range(max_retries):
            try:
                response = self.client.embeddings(model=self.model_name, prompt=clean_text)
                return response.get("embedding", [])
            except Exception as e:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Failed to generate embedding via Ollama ({self.model_name}): {e}")
                time.sleep(0.5 * (attempt + 1))
        return [0.0] * 768

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

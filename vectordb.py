"""
vectordb.py: ChromaDB Persistent Vector Database Manager.
Stores chunk embeddings and metadata for strict retrieval and topic search.
"""
import os
import re
from typing import List, Dict, Optional, Any, Callable
import chromadb
from chromadb.config import Settings
from models.schema import TextbookChunk
from embeddings import OllamaEmbedder

class VectorDBManager:
    """Manages local ChromaDB collections per textbook."""

    def __init__(self, persist_dir: str = "./data/chroma_db"):
        self.persist_dir = persist_dir
        os.makedirs(self.persist_dir, exist_ok=True)
        # Initialize 100% offline ChromaDB client with telemetry disabled
        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )

    def _safe_collection_name(self, book_id: str) -> str:
        """Converts book_id to a valid ChromaDB collection name (3-63 characters, [a-zA-Z0-9_-])."""
        name = re.sub(r'[^a-zA-Z0-9_-]', '_', book_id)
        if not name[0].isalnum():
            name = "c_" + name
        if len(name) < 3:
            name = name + "_col"
        return name[:63]

    def get_or_create_collection(self, book_id: str):
        col_name = self._safe_collection_name(book_id)
        return self.client.get_or_create_collection(
            name=col_name,
            metadata={"hnsw:space": "cosine"}
        )

    def is_book_indexed(self, book_id: str) -> bool:
        """Checks if the book collection exists and contains indexed documents."""
        try:
            col_name = self._safe_collection_name(book_id)
            cols = [c.name for c in self.client.list_collections()]
            if col_name in cols:
                col = self.client.get_collection(col_name)
                return col.count() > 0
            return False
        except Exception:
            return False

    def index_chunks(
        self,
        book_id: str,
        chunks: List[TextbookChunk],
        embedder: OllamaEmbedder,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> int:
        """
        Indexes a list of TextbookChunk objects into ChromaDB.
        Skips indexing if chunks are already present.
        """
        collection = self.get_or_create_collection(book_id)
        existing_count = collection.count()
        if existing_count >= len(chunks) and len(chunks) > 0:
            return existing_count

        total = len(chunks)
        batch_size = 25
        indexed_total = 0

        for start_idx in range(0, total, batch_size):
            end_idx = min(start_idx + batch_size, total)
            batch = chunks[start_idx:end_idx]

            docs = [c.original_text for c in batch]
            ids = [c.chunk_id for c in batch]
            metadatas = [{
                "book_id": c.metadata.book_id,
                "book_name": c.metadata.book_name,
                "unit": c.metadata.unit,
                "chapter": c.metadata.chapter,
                "section": c.metadata.section,
                "topic_title": c.metadata.topic_title or c.metadata.chapter,
                "start_page": c.metadata.start_page,
                "end_page": c.metadata.end_page,
                "chunk_index": c.metadata.chunk_index
            } for c in batch]

            # Generate embeddings for the batch
            embeddings = []
            for item_idx, d in enumerate(docs):
                emb = embedder.get_embedding(d)
                embeddings.append(emb)
                if progress_callback:
                    curr = start_idx + item_idx + 1
                    progress_callback(curr, total, f"Embedding chunk {curr}/{total}...")

            collection.add(
                ids=ids,
                documents=docs,
                embeddings=embeddings,
                metadatas=metadatas
            )
            indexed_total += len(batch)

        return indexed_total

    def query_similar(
        self,
        book_id: str,
        query_text: str,
        embedder: OllamaEmbedder,
        n_results: int = 5,
        chapter_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Performs semantic similarity retrieval.
        Returns matched documents with metadata and cosine distances.
        """
        collection = self.get_or_create_collection(book_id)
        query_vec = embedder.get_embedding(query_text)

        where_clause = None
        if chapter_filter:
            where_clause = {"chapter": chapter_filter}

        res = collection.query(
            query_embeddings=[query_vec],
            n_results=min(n_results, max(collection.count(), 1)),
            where=where_clause
        )

        results = []
        if res and res.get("documents") and res["documents"][0]:
            docs = res["documents"][0]
            metas = res["metadatas"][0] if res.get("metadatas") else [{}] * len(docs)
            distances = res["distances"][0] if res.get("distances") else [0.0] * len(docs)
            ids = res["ids"][0] if res.get("ids") else [""] * len(docs)

            for doc, meta, dist, cid in zip(docs, metas, distances, ids):
                results.append({
                    "chunk_id": cid,
                    "text": doc,
                    "metadata": meta,
                    "distance": round(dist, 4),
                    "relevance_score": round(1.0 - dist, 4) if dist is not None else 1.0
                })

        return results

    def get_section_chunks(self, book_id: str, chapter_title: str) -> List[Dict[str, Any]]:
        """Fetches all chunks belonging to a chapter/section ordered by chunk_index."""
        collection = self.get_or_create_collection(book_id)
        res = collection.get(
            where={"chapter": chapter_title}
        )

        results = []
        if res and res.get("documents"):
            docs = res["documents"]
            metas = res["metadatas"]
            ids = res["ids"]

            for cid, doc, meta in zip(ids, docs, metas):
                results.append({
                    "chunk_id": cid,
                    "text": doc,
                    "metadata": meta
                })

            results.sort(key=lambda x: x["metadata"].get("chunk_index", 0))

        return results

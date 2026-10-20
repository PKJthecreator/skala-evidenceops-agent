"""6개 런북을 Ollama 임베딩으로 검색한다. 별도 DB나 추가 의존성 없음."""
import asyncio
import math
import os
from pathlib import Path


def normalized(vector: list[float]) -> list[float]:
    if not vector or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector):
        raise ValueError("유효하지 않은 임베딩")
    norm = math.sqrt(sum(v * v for v in vector))
    if not norm or not math.isfinite(norm):
        raise ValueError("임베딩 크기가 유효하지 않음")
    return [v / norm for v in vector]


class RunbookSearch:
    def __init__(self, directory: Path | None = None):
        directory = directory or Path(__file__).resolve().parent.parent / "data" / "runbooks"
        # ponytail: 소수 런북을 메모리에 보관; 문서 갱신은 재시작, 문서가 많아지면 영속 색인.
        self.documents = []
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            self.documents.append({"doc_id": path.stem, "title": text.splitlines()[0].lstrip("# "), "text": text})
        self.vectors = []
        self.lock = asyncio.Lock()
        self.url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/embed"
        self.model = os.getenv("EMBED_MODEL", "bge-m3")
        self.min_score = float(os.getenv("RUNBOOK_MIN_SCORE", "0.55"))

    async def search(self, query: str) -> list[dict]:
        import httpx

        if not self.documents:
            return []
        async with asyncio.timeout(float(os.getenv("EMBED_TIMEOUT", "60"))):
            async with self.lock:
                inputs = [query] if self.vectors else [doc["text"] for doc in self.documents] + [query]
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(self.url, json={"model": self.model, "input": inputs, "truncate": False})
                    response.raise_for_status()
                    embeddings = response.json()["embeddings"]
                if len(embeddings) != len(inputs):
                    raise ValueError("임베딩 개수가 입력과 다름")
                vectors = [normalized(vector) for vector in embeddings]
                query_vector = vectors[-1]
                document_vectors = self.vectors or vectors[:-1]
                if any(len(v) != len(query_vector) for v in document_vectors):
                    raise ValueError("임베딩 차원이 다름")
                self.vectors = document_vectors
                ranked = sorted(
                    ({**doc, "score": sum(a * b for a, b in zip(vector, query_vector))}
                     for doc, vector in zip(self.documents, self.vectors)),
                    key=lambda doc: (-doc["score"], doc["doc_id"]))
                # ponytail: 대상별 대표 런북 1개; 복합 장애 누락이 확인되면 복수 선택을 평가한다.
                return [doc for doc in ranked[:1] if doc["score"] >= self.min_score]

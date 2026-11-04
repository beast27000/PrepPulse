"""Download the pinned Python CPU embedding model; no LM Studio dependency."""
import os

os.environ.setdefault("PREPPULSE_EMBED_REVISION", "614241f622f53c4eeff9890bdc4f31cfecc418b3")

from preppulse_rag.python_embeddings import PythonEmbeddings

if __name__ == "__main__":
    vectors = PythonEmbeddings().embed_documents(["Synthetic HbA1c history: 7.2 percent."])
    print(f"Pinned multilingual E5 ready: {len(vectors[0])} dimensions on CPU")

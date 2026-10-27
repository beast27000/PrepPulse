from typing import Any

from pymongo import ASCENDING, MongoClient

from preppulse_db.schemas import DocumentChunk, PatientDocument, Stage2StructuredEntities

# ==============================================================================
# TEAMMATE HANDOFF USAGE:
# 1. Teammate A: Call `store.write_chunk(chunk)` to save section chunks into `document_chunks`.
# 2. Teammate B: Call `store.get_chunks(document_id)` to read chunks, run LLM extraction,
#    and then call `store.write_stage2(document_id, extracted_dict)` to update `patient_documents`.
# ==============================================================================

# ---------- master mongo store ----------


class MongoStore:
    # Manages MongoDB connections, indexing, and multi-stage document persistence

    def __init__(
        self,
        uri: str = "mongodb://localhost:27017",
        db_name: str = "preppulse",
        server_timeout_ms: int = 3000,
    ) -> None:
        # Initializes client configuration with fast timeout for offline resilience
        self.uri = uri
        self.db_name = db_name
        self.server_timeout_ms = server_timeout_ms
        self._client: MongoClient | None = None
        self._db = None

    def connect(self) -> None:
        # Connects to local MongoDB and initializes performance indexes
        if self._client is not None:
            return
        self._client = MongoClient(self.uri, serverSelectionTimeoutMS=self.server_timeout_ms)
        self._db = self._client[self.db_name]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        # Creates unique and compound indexes for document retrieval
        docs = self._db["patient_documents"]
        docs.create_index([("document_id", ASCENDING)], unique=True)
        docs.create_index([("patient_id", ASCENDING), ("visit_date", ASCENDING)])
        docs.create_index([("document_type", ASCENDING)])

        chunks = self._db["document_chunks"]
        chunks.create_index([("chunk_id", ASCENDING)], unique=True)
        chunks.create_index([("document_id", ASCENDING)])
        chunks.create_index([("patient_id", ASCENDING)])

    @property
    def db(self):
        # Returns active database reference, auto-connecting if needed
        if self._db is None:
            self.connect()
        return self._db

    # ---------- stage 1: document operations ----------

    def write_stage1(self, document: PatientDocument | dict[str, Any]) -> str:
        # Upserts compound document with Stage 1 raw OCR payload
        doc_dict = document.model_dump() if isinstance(document, PatientDocument) else dict(document)
        doc_id = doc_dict["document_id"]
        self.db["patient_documents"].update_one(
            {"document_id": doc_id},
            {"$set": doc_dict},
            upsert=True,
        )
        return doc_id

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        # Retrieves document by unique document ID
        return self.db["patient_documents"].find_one({"document_id": document_id}, {"_id": 0})

    def list_documents(self, patient_id: str | None = None) -> list[dict[str, Any]]:
        # Lists documents optionally filtered by patient ID
        query = {"patient_id": patient_id} if patient_id else {}
        return list(self.db["patient_documents"].find(query, {"_id": 0}).sort("visit_date", ASCENDING))

    def count_documents(self, patient_id: str | None = None) -> int:
        # Returns count of documents in store
        query = {"patient_id": patient_id} if patient_id else {}
        return self.db["patient_documents"].count_documents(query)

    # ---------- stage 2: structured entity updates ----------

    def write_stage2(
        self,
        document_id: str,
        stage2_entities: Stage2StructuredEntities | dict[str, Any],
    ) -> bool:
        # Updates Stage 2 structured facts on an existing document (accepts arbitrary extra fields)
        entities_dict = (
            stage2_entities.model_dump()
            if isinstance(stage2_entities, Stage2StructuredEntities)
            else dict(stage2_entities)
        )
        res = self.db["patient_documents"].update_one(
            {"document_id": document_id},
            {
                "$set": {
                    "stage_2_structured_entities": entities_dict,
                    "status": "stage_2_complete",
                }
            },
        )
        return res.matched_count > 0

    # ---------- stage 2 intermediate: chunk operations ----------

    def write_chunk(self, chunk: DocumentChunk | dict[str, Any]) -> str:
        # Upserts a chunk record produced by Teammate A
        chunk_dict = chunk.model_dump() if isinstance(chunk, DocumentChunk) else dict(chunk)
        chunk_id = chunk_dict["chunk_id"]
        self.db["document_chunks"].update_one(
            {"chunk_id": chunk_id},
            {"$set": chunk_dict},
            upsert=True,
        )
        return chunk_id

    def get_chunks(self, document_id: str) -> list[dict[str, Any]]:
        # Retrieves all chunks for a given document
        return list(self.db["document_chunks"].find({"document_id": document_id}, {"_id": 0}))

    # ---------- cleanup & maintenance ----------

    def clear_database(self) -> None:
        # Drops all collections in target database for test teardown
        self.db["patient_documents"].drop()
        self.db["document_chunks"].drop()

    def close(self) -> None:
        # Closes underlying MongoClient connection
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None

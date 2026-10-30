"""
PrepPulse preprocessing layer (Stage 2 + Stage 3).

Reads Stage 1 OCR from MongoDB, compiles it into verified, provenance-tagged
structured clinical facts (Stage 2), and standardizes them into FHIR R4
(Stage 3), writing both back to the same `patient_documents` collection.

Public API:
    from preppulse_preprocessing import Pipeline, Store, load_settings
"""
from preppulse_preprocessing.config import Settings, load_settings
from preppulse_preprocessing.pipeline import Pipeline
from preppulse_preprocessing.store import Store

__all__ = ["Pipeline", "Settings", "Store", "load_settings"]
__version__ = "0.1.0"

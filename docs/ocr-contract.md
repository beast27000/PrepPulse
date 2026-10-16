# OCR contract

## Coordinate convention

All output boxes use a top-left origin and are normalized to inclusive `[0, 1000]` space:

`normalized = round(1000 * source_coordinate / source_dimension)`

`source_bbox` and page dimensions are retained so consumers can precisely map a normalized
box into a PDF.js viewport. Do not renormalize a normalized box.

## Metadata authority

The patient-pack manifest is authoritative for `patient_id`, `document_type`, and encounter
dates. OCR-derived values are evidence only and must not overwrite supplied metadata.

## Lab tables

Each cell has `row_index`, `column_index`, `text`, `bbox`, and contributing `token_ids`.
Semantic labels (`analyte`, `observed_value`, `unit`, `reference_range`, `flag`) are assigned
only when a header confidently identifies the column. Unknown headers remain structurally
preserved rather than guessed.

## RAG and agent citation rule

Every future chunk or claim must retain `patient_id`, `document_id`, `page_number`, `bbox`,
and exact source text. A chunk without that provenance is invalid for clinical use.

# Product overview

This guide gives the fuller product rationale and workflow. The root README is a shorter introduction.

## The product problem

A patient may arrive with years of laboratory reports, handwritten or scanned prescriptions, discharge summaries, outpatient notes, and records from different facilities. The clinical story is spread across these documents. A recent number may be easy to find while the earlier comparison, a medication discrepancy, or the reason for a hospital stay is buried elsewhere.

PrepPulse organizes this material around a permanent patient identity. Documents can be appended over multiple visits. The doctor can review a focused brief, inspect older history, ask questions about the record, generate supported measurement charts, and approve a care plan that remains available at the next consultation.

The intended workflow has three connected parts:

1. **Prepare the record:** register or select the patient, upload files, extract text and source geometry, and build the reviewable record.
2. **Support the consultation:** show a source-linked brief, retrieve relevant history, compare documented measurements, and let the doctor inspect original evidence.
3. **Preserve continuity:** sign instructions, retain a dated care plan and visit snapshot, and collect caregiver-reported completion and notes.

This document describes the local implementation in the UI and main branches. The separately maintained deployment branch has its own service topology and deployment guide. PrepPulse is an assistive workflow and is not a validated diagnostic device or a certified hospital information system.

# PrepPulse working agreement

## Read first

Read this file before acting on every user request in this repository.

## Planning before code

- Do not create, modify, delete, or refactor application code until a scoped implementation
  plan has been presented to the project owner and explicitly approved.
- Documentation-only changes may proceed when directly requested, but must accurately reflect
  the current repository state.

## Version-control policy

- Never make application-code changes outside version control.
- Keep code changes reviewable, tested in proportion to their risk, committed with a clear
  message, and pushed only with the project owner's authorization.
- While the OCR foundation is being stabilised, its current repository is the working base.
- Once the OCR/backend base is declared stable by the project owner, build additions such as
  agents, RAG, UI, or other major features in separate repositories. Integrate them into this
  repository only through a deliberate, reviewed merge after the owner approves the plan.

## Living project documentation

- Keep `README.md` and `TO_DO.md` current whenever an implementation status, architectural
  decision, dependency, or project scope changes.
- `TO_DO.md` is the source of truth for completed work, work in progress, planned work, and
  known limitations.

## Scope

- PrepPulse is an assistive clinical chart-review system. Preserve source provenance and do
  not represent generated output as autonomous clinical diagnosis or treatment advice.

# PrepPulse documentation

These guides document the deployed PrepPulse product. The root [README](../README.md) introduces the product and links to its deployed website.

| Document | Subject |
| --- | --- |
| [Product overview](product/PRODUCT_OVERVIEW.md) | Purpose, roles, patient history and clinical boundaries |
| [Architecture](product/ARCHITECTURE.md) | Azure runtime, data flow, storage and security boundaries |
| [Frontend](product/FRONTEND.md) | Doctor, administrator and caregiver workspaces |
| [Backend](product/BACKEND.md) | API, durable workers, MongoDB, FHIR and private documents |
| [AI and retrieval](product/AI_AND_RAG.md) | Model routing, review stages, RAG, evidence, charts and language features |
| [Setup and operations](product/SETUP.md) | Deployed environment, configuration, release and recovery |
| [Deployment runbook](../deployment/README.md) | Detailed Azure resource and operating procedures |
| [Verification](../deployment/VERIFICATION.md) | Release checks, measured results and remaining limitations |

The runbook contains the exact infrastructure commands and environment setup. Keep provider credentials and private patient information out of documentation and Git.

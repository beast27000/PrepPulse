# Setup and operations

## Use the deployed website

Open [PrepPulse](https://preppulse-pilot-b8bc.centralindia.cloudapp.azure.com/) and sign in with an administrator-provisioned account. There is no public registration flow. The pilot is configured with synthetic demonstration records and must not be treated as approved for real patient information.

## Reproduce the deployed environment

The full infrastructure and release procedure is in the [Azure deployment runbook](../../deployment/README.md). This guide summarizes its sequence; the runbook is authoritative for commands and current resource names.

### Prerequisites

You need an Azure subscription with sufficient VM quota and credit, Azure CLI, an SSH key, a Linux x64 host or VM, Docker and Docker Compose, Python 3.11, Node.js/npm for the frontend build, and a domain or DNS name for HTTPS. AI requires a valid funded Sarvam key. Azure Translator and Speech require provisioned resources and credentials. Azure OpenAI requires an approved model deployment; the pilot account is currently blocked from deploying its model.

### Provision and configure

1. Review `infra/main.bicep` and create a private parameter file for the target resource group, region, SSH public key, administrator object ID and allowed SSH source address.
2. Run Azure validation and what-if before creating infrastructure. The deployment provisions the VM, network rules, persistent disk, Key Vault and private backup storage.
3. Configure the deployed application environment from `deployment/server.env.example`. Put secrets in Key Vault and the root-owned server environment file. Never commit private values, print keys in terminal logs, or copy credentials into issue trackers.
4. Provision Azure Translator and Speech separately. Configure Sarvam as the primary clinical model and Azure OpenAI as the secondary route only when a real approved model deployment is available.
5. Upload an allowlisted release package to the VM, run `deployment/setup_vm.sh`, and start the Docker Compose services. Configure DNS before Caddy requests its HTTPS certificate.
6. Create administrator access using the private bootstrap procedure. Add doctors and caregivers through the administrator workspace.
7. Validate public health, login, role boundaries, document preview, a synthetic upload, processing state, chat citations, translation and backup before inviting users.

Exact commands, example environment variables and migration safeguards are in [deployment/README.md](../../deployment/README.md#reproduce-the-deployed-runtime). Do not rerun the initial import against a populated live database. Do not run destructive audit/reset scripts against deployed data.

## Provider configuration

The deployed runtime expects provider secrets only on the server. `Main_Sarvam_AI_Credits` is the selected Sarvam credential. The actual Azure OpenAI endpoint, deployment name and key must refer to an approved, working deployment. Translator and Speech use their own Azure resources. The E5 model is downloaded and cached by the server-side Python embedding component. Provider order and administrator routing controls are described in the runbook. Never put a provider secret in frontend build variables because those values are public to browser users.

Application-level estimated spending reservations are separate from provider billing. Monitor Azure Cost Management and provider dashboards. A configured spending cap is not a guarantee about shared-account usage or invoices.

## Releases and rollback

Build and package an allowlisted release, copy it to the VM over SSH, and recreate only the application containers. Persistent `/data` and `/etc/preppulse` contents must remain independent from source releases. Keep the session secret stable unless intentionally invalidating sessions. Before rollout, preserve the last known-good application bundle and verify the latest backup. After rollout, check health, login, upload, evidence preview, chat and worker state. Use the runbook for package and Compose commands.

## Backup and restore

The daily backup service captures MongoDB and private application files, encrypts the archive, uploads it to private Azure Blob storage and verifies its checksum. Keep an encryption key copy outside the resource group. Restore verification targets a separate database and must not overwrite live data. A backup timer is not proof of a successful backup; review service logs and perform periodic restore drills.

## Verification and current limitations

See the [release verification report](../../deployment/VERIFICATION.md) for actual completed checks. The Azure OpenAI model deployment remains blocked. One scanned synthetic label was misread by OCR and correctly omitted from structured measurements. The pilot has one clinical worker, no completed five-day soak, no high-availability configuration and no security certification for real patient deployment. Azure credit, provider quotas and service availability can change the site's availability.

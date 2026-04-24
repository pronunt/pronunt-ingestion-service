# pronunt-ingestion-service

Fetches pull requests from GitHub and publishes ingestion events.

## Stack

* FastAPI
* Docker Hardened Images with multi-stage builds
* Kubernetes raw manifests in `k8s/`
* Helm chart in `helm/`
* GitHub Actions workflow in `.github/workflows/`

## Branching

This repository follows trunk-based development with `main` as the long-lived branch.


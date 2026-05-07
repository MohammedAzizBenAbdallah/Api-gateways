# GitOps Layout — Deterministic Enterprise AI Orchestration Platform

This directory implements a production-ready GitOps workflow using **Kustomize overlays** and **Argo CD** for declarative, Git-driven deployments across three environments.

## Directory Structure

```
gitops/
├── argocd/
│   ├── project-ai-gateway.yaml    # ArgoCD AppProject (scoped permissions)
│   ├── app-dev.yaml               # Dev: auto-sync, self-heal, prune
│   ├── app-staging.yaml           # Staging: auto-sync, self-heal, prune
│   └── app-prod.yaml              # Prod: manual sync only (approval required)
├── base/
│   ├── kustomization.yaml         # Shared resources across all environments
│   └── pdbs.yaml                  # PodDisruptionBudgets (FastAPI, Kong DP)
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml     # 1 replica, dev-latest tags
    │   └── patch-deployments.yaml
    ├── staging/
    │   ├── kustomization.yaml     # 2 replicas, release candidate tags
    │   └── patch-deployments.yaml
    └── prod/
        ├── kustomization.yaml     # 4 replicas, immutable SHA256 digests
        └── patch-deployments.yaml # Resource limits enforced
```

## Environment Comparison

| Aspect             | Dev              | Staging          | Prod                      |
|--------------------|------------------|------------------|---------------------------|
| Replicas (FastAPI) | 1                | 2                | 4                         |
| HPA Max            | 3                | 6                | 12                        |
| Image Strategy     | `dev-latest` tag | `v1.0.0-rc.1`   | Immutable `sha256` digest |
| ArgoCD Sync        | Auto + SelfHeal  | Auto + SelfHeal  | **Manual only**           |
| OPA Fallback       | allowed          | allowed          | **disabled**              |
| Resource Limits    | none             | none             | enforced                  |

## Promotion Flow

```
dev (auto-sync from main)
 └──> staging (auto-sync, RC tags)
       └──> prod (manual approval, immutable digests)
```

Promotions happen through Git pull requests that update image tags/digests in the overlay `kustomization.yaml` files.

## Local Render Checks

Validate manifests before pushing:

```bash
kustomize build k8s/gitops/overlays/dev --load-restrictor LoadRestrictionsNone
kustomize build k8s/gitops/overlays/staging --load-restrictor LoadRestrictionsNone
kustomize build k8s/gitops/overlays/prod --load-restrictor LoadRestrictionsNone
```

## Argo CD Bootstrap

1. Install Argo CD in the `argocd` namespace.
2. Apply project and applications:

```bash
kubectl apply -f k8s/gitops/argocd/project-ai-gateway.yaml
kubectl apply -f k8s/gitops/argocd/app-dev.yaml
kubectl apply -f k8s/gitops/argocd/app-staging.yaml
kubectl apply -f k8s/gitops/argocd/app-prod.yaml
```

## Security Notes

- Prod uses **immutable image digests** to prevent tag mutation attacks.
- ArgoCD AppProject restricts cluster resources to Namespaces, PDBs, and NetworkPolicies only.
- Prod sync is **manual** — requires explicit approval via ArgoCD UI or CLI.
- Secrets should be managed via External Secrets Operator + HashiCorp Vault in production.

# Kubernetes GitOps Platform on GKE

Two Python microservices deployed to **GKE Autopilot** with **Helm** and **Argo CD**, monitored
by **Prometheus** and **Grafana**. Git is the only way to change what runs in the cluster:
CI builds images and commits the new tag, and Argo CD syncs the cluster to match.

```
 developer ── git push ──► GitHub
                              │
          GitHub Actions ─────┤ test ─► helm lint + kubeconform ─► build ─► Trivy ─► push
          (WIF, no JSON key)  │                                                  │
                              │◄──── commit image tag to deploy/prod/*.yaml ─────┘
                              │
                     Argo CD (in cluster) watches main
                              │ sync (prune + self-heal)
                              ▼
   ┌──────────────── GKE Autopilot ─────────────────────────────┐
   │  ns shop:        orders ──HTTP──► catalog                  │
   │                  (HPA, PDB, non-root, read-only rootfs)    │
   │  ns monitoring:  Prometheus ◄─ ServiceMonitors             │
   │                  Alertmanager ─► Slack                     │
   │                  Grafana (RED dashboard)                   │
   └────────────────────────────────────────────────────────────┘
```

## Services

| Service | Endpoints | Notes |
|---|---|---|
| `catalog` | `GET /products`, `GET /products/{id}` | `FAULT_RATE` env var injects 5xx errors to test alerting |
| `orders` | `POST /orders`, `GET /orders` | Looks up price and stock in `catalog`. `/readyz` fails if catalog is unreachable, so Kubernetes stops sending it traffic |

Both export RED metrics on `/metrics`: `http_requests_total` and the
`http_request_duration_seconds` histogram, labelled by route template so cardinality stays low.

## Repo layout

```
services/{catalog,orders}/   FastAPI app, tests, multi-stage Dockerfile (uv, non-root)
charts/microservice/         one Helm chart for both services
deploy/prod/*.yaml           per-service values; CI updates image.tag here
argocd/root-app.yaml         app-of-apps, the only thing applied by hand
argocd/apps/                 catalog, orders, kube-prometheus-stack, alert rules + dashboard
monitoring/                  PrometheusRule, Grafana dashboard ConfigMap, stack values
terraform/                   GKE Autopilot, Artifact Registry, Workload Identity Federation
.github/workflows/ci.yml     test → lint manifests → build → scan → push → bump tag
```

## What the chart enforces

- `maxUnavailable: 0` rolling updates, readiness gates, PodDisruptionBudget (`minAvailable: 1`)
- HPA on CPU, 2 to 6 replicas (orders up to 10), spread across zones
- `runAsNonRoot`, UID 10001, `readOnlyRootFilesystem`, all capabilities dropped, seccomp `RuntimeDefault`
- A `ServiceMonitor` per service, so Prometheus finds new services with no extra config
- Rendering fails if `image.tag` is missing

## Alerts (`monitoring/alert-rules.yaml`)

| Alert | Fires when | Severity |
|---|---|---|
| `HighErrorRate` | more than 5% of requests are 5xx for 5 minutes | critical |
| `HighLatencyP95` | p95 latency above 500 ms for 10 minutes | warning |
| `ServiceDown` | a pod target is down for 2 minutes | critical |
| `PodRestartingOften` | more than 3 restarts in 30 minutes | warning |

Recording rules precompute rate, error ratio and p95 per service. The alerts and the Grafana
dashboard both read from those recording rules.

## Security choices

- **No service account keys.** GitHub Actions authenticates to GCP with Workload Identity
  Federation. Only `refs/heads/main` of this repo can get a token.
- **CI cannot touch the cluster.** The CI service account can only push to one Artifact Registry
  repo. Deploying is Argo CD's job, pulling from Git.
- **Images are scanned.** Trivy fails the build on fixable HIGH or CRITICAL CVEs.
- **Drift is reverted.** `selfHeal: true` undoes manual `kubectl edit` changes.

## Run locally

```bash
cd services/catalog && uv sync && uv run pytest -q
cd ../orders && uv sync && uv run pytest -q

# both services together
docker network create shop
docker build -t catalog services/catalog && docker build -t orders services/orders
docker run -d --name catalog --network shop catalog
docker run -d --name orders --network shop -p 8080:8080 -e CATALOG_URL=http://catalog:8080 orders
curl -X POST localhost:8080/orders -H 'content-type: application/json' -d '{"product_id":1,"quantity":2}'
```

## Deploy to GCP

```bash
# 1. Infra
cd terraform && terraform init && terraform apply -var project_id=$PROJECT
$(terraform output -raw get_credentials)
# Add the three values from `terraform output github_variables` as GitHub repo variables

# 2. Argo CD
kubectl create namespace argocd
kubectl apply -n argocd --server-side -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.1.5/manifests/install.yaml

# 3. Slack webhook for Alertmanager (kept out of Git)
kubectl create namespace monitoring
kubectl -n monitoring create secret generic alertmanager-slack --from-literal=url=$SLACK_WEBHOOK

# 4. Hand over to GitOps
kubectl apply -n argocd -f argocd/root-app.yaml
```

From here, merging to `main` is the deploy. To roll back, `git revert` the `deploy:` commit.

To test alerting, set `FAULT_RATE: "0.3"` in `deploy/prod/catalog.yaml` and push. About 5 minutes
later `HighErrorRate` fires in Slack. Revert the change and the alert resolves.

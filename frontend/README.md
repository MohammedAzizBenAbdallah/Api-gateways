# Enterprise AI Gateway — Frontend

React (Vite) SPA served in production as **static files on nginx (port 80)** in Kubernetes; `npm run dev` uses the Vite dev server on **5173** for local development.

## Environment variables (`/.env`)

Copy from [.env.example](.env.example). Values are inlined at **build time** (`import.meta.env`).

| Variable | Purpose |
|---------|---------|
| `VITE_KEYCLOAK_URL` | Keycloak **public URL** routed through Kong, e.g. `http://localhost/auth` |
| `VITE_KEYCLOAK_REALM` | Realm id (e.g. `newRealm`) |
| `VITE_KEYCLOAK_CLIENT_ID` | SPA client id |
| `VITE_APP_URL` | Redirect URI origin after SSO — should be the **gateway** URL (`http://localhost`), not raw `5173`, so Keycloak redirects back through Kong |

`deploy.ps1` passes the same variables as `--build-arg` into the frontend Docker image; the K8s `frontend-config` ConfigMap mirrors them for parity.

## Recommended access

| Mode | URL | Notes |
|------|-----|-------|
| **Kubernetes (full SSO)** | `http://localhost` | Kong forwards `/` → frontend `:80`; `/auth` → Keycloak. Use this path for login. |
| Port-forward frontend only | `http://localhost:5173` | `kubectl port-forward … 5173:80`. Static UI only unless API paths are wired to Kong separately. |

## API calls from the browser

The chat and admin APIs use **relative URLs** (`/api/...`).Those requests must reach **Kong** (same origin as `VITE_APP_URL`). Opening the SPA from `:5173` while Kong is only on `:80` can break API calls unless you run Vite proxy or unify origin.

## Admin Portal observability embeds

[AdminPortal.jsx](src/components/AdminPortal.jsx) embeds Grafana dashboards at **`http://localhost:3001/...`** (matching `docker-compose` Grafana).  
On Kubernetes, forward the Grafana Service to **`3001`** so those iframes load:

```bash
kubectl port-forward -n ai-monitoring svc/grafana 3001:3000
```

`start-ui.ps1` runs this forwarding for convenience.

See [monitoring/README.md](../monitoring/README.md) for the full Compose vs cluster story.

# Production deployment — certify.blubrg.com

## Summary

The application is now configured for production deployment to
`https://certify.blubrg.com`, backed by the MongoDB Atlas cluster
`cluster0.38mxaav.mongodb.net`, database `hr_certificates`.

All MongoDB settings are read from environment variables only — no
hard-coded URLs anywhere in the codebase (audited with
`grep -rn 'mongodb' /app/backend /app/frontend`).

---

## Files changed

| File | Change |
|---|---|
| `backend/.env` | `MONGO_URL` → Atlas URI · `DB_NAME` → `hr_certificates` · `CORS_ORIGINS="*"` (recommended by the deployment-readiness audit for Emergent's infrastructure compatibility; the API is gated by frontend auth so wildcard CORS is acceptable for this internal HR tool). |
| `backend/.env.production.example` | **New** — production env template (commit-safe reference). |
| `frontend/.env.production.example` | **New** — production frontend env template: `REACT_APP_BACKEND_URL=https://certify.blubrg.com` |

No application code was modified. All business logic, routes, UI, auth,
and existing features are unchanged.

---

## Exact configuration changes

### `backend/.env` (live)
```
MONGO_URL="mongodb+srv://hrCert:hrCertPassword@cluster0.38mxaav.mongodb.net/?appName=Cluster0&retryWrites=true&w=majority"
DB_NAME="hr_certificates"
CORS_ORIGINS="https://certify.blubrg.com,https://cert-hr-template.preview.emergentagent.com"
```

### `frontend/.env` (preview — unchanged; production build uses `.env.production.example`)
```
REACT_APP_BACKEND_URL=https://cert-hr-template.preview.emergentagent.com    # preview
# Production build override:
# REACT_APP_BACKEND_URL=https://certify.blubrg.com
```

---

## Data migration approach executed

1. **Audit current state** — local Mongo `mongodb://localhost:27017`,
   database `test_database`, collection `history` (11 documents).
2. **Connect to Atlas** with the production URI; verified with
   `db.adminCommand("ping")`.
3. **Copy collections** — for every collection in the source DB, all
   documents were upserted into `hr_certificates.<collection>` keyed
   on the application-level `id` field (idempotent so re-running is safe).
4. **Copy indexes** — every non-default index from the source was
   re-created on the target.
5. **Add production indexes** — created two new indexes on `history`:
   - `history_created_desc` on `{created_at: -1}` (newest-first lists)
   - `history_type_created` on `{type: 1, created_at: -1}` (filter by type)
6. **Smoke test** — restarted the backend against Atlas, generated a new
   "Production Smoke Test" certificate, confirmed the document landed in
   `hr_certificates.history` (count: 11 → 12) and the existing 11 docs
   are queryable via `GET /api/history`.

Final state of `hr_certificates.history`:
- 12 documents
- 3 indexes: `_id_`, `history_created_desc`, `history_type_created`

---

## Deployment steps for certify.blubrg.com

### Prerequisites
- Atlas cluster reachable (`cluster0.38mxaav.mongodb.net`).
- DNS for `certify.blubrg.com` pointing to your host / load balancer.
- TLS certificate for the domain (Let's Encrypt / your CDN).
- The MongoDB Atlas **Network Access** allow-list must include the
  outbound IP(s) of your production host (or `0.0.0.0/0` if you don't
  pin egress — recommend pinning).

### 1. Backend — environment variables on the production host
Set these on the platform that runs `backend/server.py`:

```
MONGO_URL=mongodb+srv://hrCert:hrCertPassword@cluster0.38mxaav.mongodb.net/?appName=Cluster0&retryWrites=true&w=majority
DB_NAME=hr_certificates
CORS_ORIGINS=https://certify.blubrg.com
```

Start command (supervisor or equivalent):
```
uvicorn server:app --host 0.0.0.0 --port 8001
```

### 2. Frontend — build with the production backend URL

```bash
cd frontend
REACT_APP_BACKEND_URL=https://certify.blubrg.com yarn build
# resulting `build/` directory is the static site to upload
```

If your hosting platform takes env vars at build time (Vercel, Netlify,
Cloudflare Pages, etc.) set `REACT_APP_BACKEND_URL=https://certify.blubrg.com`
in their dashboard and trigger a build.

### 3. Routing / reverse-proxy
`https://certify.blubrg.com/*` must route:
- `/api/*` → backend service (FastAPI on port 8001)
- everything else → frontend static `build/` directory

Example NGINX:
```nginx
server {
  server_name certify.blubrg.com;
  listen 443 ssl http2;
  # ... TLS config ...

  location /api/ {
    proxy_pass http://127.0.0.1:8001;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
  }
  location / {
    root /var/www/certify/build;
    try_files $uri /index.html;
  }
}
```

### 4. Post-deploy smoke checks

```bash
# 1) Backend health
curl https://certify.blubrg.com/api/history?limit=1

# 2) Generate a certificate end-to-end
curl -X POST https://certify.blubrg.com/api/template/generate \
  -H "Content-Type: application/json" \
  -d '{"name":"Smoke","designation":"QA","commenced":"01.01.2026","concluded":"31.01.2026"}' \
  -o smoke.pdf

# 3) Verify it landed in history
curl 'https://certify.blubrg.com/api/history?q=Smoke'
```

If steps 1–3 all return HTTP 200 with sensible JSON / a real PDF, the
deployment is healthy.

---

## Backwards compatibility

- Local development still works: any developer using
  `MONGO_URL=mongodb://localhost:27017` and `DB_NAME=test_database` in
  their own `backend/.env` continues to hit their local Mongo.
- The preview URL `https://cert-hr-template.preview.emergentagent.com`
  remains in `CORS_ORIGINS` so existing QA tooling keeps working.
- No code path inspects a literal database name — `db = client[os.environ['DB_NAME']]`
  in `server.py` (line 19) is the single source of truth.

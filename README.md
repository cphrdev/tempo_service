# Tempo Preflight API

A read-only transaction simulation and risk-analysis API paid per request through the
[Machine Payments Protocol](https://mpp.dev). Each successful call costs **0.01 USDC.e**
on Tempo mainnet and sends payment directly to the configured recipient address.

The service never asks for a private key and never broadcasts the submitted transaction.

## What it analyzes

- `eth_call` simulation and revert detection
- Gas estimation
- Whether the target is a contract
- ERC-20 `transfer`, `approve`, and `transferFrom` calldata
- `setApprovalForAll` calldata
- Unlimited allowances and unknown contract calls
- A machine-readable `safe`, `warning`, or `dangerous` verdict

This is heuristic analysis, not a security audit or guarantee.

## Run locally

Requirements: Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
# Fill PAYMENT_DESTINATION and MPP_SECRET_KEY, then:
set -a; source .env; set +a
uv sync
uv run uvicorn app.main:app --reload
```

Free checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/
```

Paid call with Tempo Wallet CLI:

```bash
TEMPO_MAX_SPEND=0.01 tempo request -X POST \
  http://localhost:8000/v1/transaction/preflight \
  --json '{
    "from":"0x1111111111111111111111111111111111111111",
    "to":"0x2222222222222222222222222222222222222222",
    "value":"0x0",
    "data":"0x"
  }'
```

First verify the 402 challenge without paying:

```bash
curl -i -X POST http://localhost:8000/v1/transaction/preflight \
  -H 'content-type: application/json' \
  -d '{"from":"0x1111111111111111111111111111111111111111","to":"0x2222222222222222222222222222222222222222"}'
```

## Run behind nginx over HTTPS

`docker-compose.yml` runs the FastAPI app together with an nginx front end that
terminates TLS on port 443 and proxies to uvicorn on port 8000. Port 80 only
serves ACME challenges and redirects to HTTPS; the app port is never published
to the host.

```bash
cp .env.example .env          # fill PAYMENT_DESTINATION and MPP_SECRET_KEY
./scripts/generate-self-signed-cert.sh localhost
docker compose up --build
```

```bash
curl -k https://localhost/health
```

`-k` is only needed for the self-signed development certificate. Set
`MPP_REALM` in `.env` to the public hostname (for example `api.example.com`)
so MPP challenges advertise the right realm — the port-8000 default in
`.env.example` is for running uvicorn directly.

The self-signed certificate makes browsers show a "not secure" warning. That is
expected — the connection is encrypted, but no certificate authority vouches for
it. Use it for local development only.

### Trusted certificates in production

Browsers stop warning once a real certificate authority issues the certificate.
`scripts/issue-letsencrypt-cert.sh` does this via Let's Encrypt, using the ACME
challenge path nginx already serves on port 80.

Prerequisites: a domain whose DNS points at the server (Let's Encrypt cannot
issue for a bare IP address), port 80 open to the internet, and the stack
running. nginx needs some certificate just to start, so generate a self-signed
one first on a fresh server, then replace it:

```bash
./scripts/generate-self-signed-cert.sh api.example.com
```

```bash
docker compose up -d --build
```

```bash
./scripts/issue-letsencrypt-cert.sh api.example.com you@example.com
```

That obtains the certificate, installs it as `nginx/certs/fullchain.pem` and
`privkey.pem`, and reloads nginx. Running it accepts the Let's Encrypt Terms of
Service. Also set `server_name` in
[nginx/conf.d/default.conf](nginx/conf.d/default.conf) to your domain instead of
the `_` catch-all.

Certificates expire after 90 days. Schedule renewal in root's crontab:

```bash
17 3,15 * * * /root/projects/tempo_service/scripts/renew-letsencrypt-cert.sh api.example.com >> /var/log/certbot-renew.log 2>&1
```

Certbot only acts within 30 days of expiry, so running it twice daily is
harmless. Certificates and keys in `nginx/certs` are gitignored. To reload nginx
by hand after replacing a certificate:

```bash
docker compose exec nginx nginx -s reload
```

## Test

```bash
uv sync --dev
uv run pytest
```

## Deploy on Render

1. Push this repository to GitHub.
2. In Render, create a Blueprint from the repository; `render.yaml` defines the service.
3. Set `PAYMENT_DESTINATION` to the Tempo address that should receive revenue.
4. Render generates `MPP_SECRET_KEY`; never expose or commit it.
5. After deployment, set `MPP_REALM` to the deployed hostname if it is not detected.
6. Check `/health`, inspect a raw 402 response, run `tempo request --dry-run`, and only
   then make a real request with `TEMPO_MAX_SPEND=0.01`.

## Publish to the MPP ecosystem

Once the production endpoint is stable and accepts real payments:

1. Add an OpenAPI URL (`https://YOUR_HOST/openapi.json`) to your service documentation.
2. Register the live service with [MPPScan](https://www.mppscan.com/).
3. Submit it to the curated [MPP service directory](https://mpp.dev/services). The directory
   requires a live, production-ready service and reviews usefulness and novelty.

## Production checklist

- Use a dedicated receiving wallet, not a personal high-value wallet.
- Pin dependency versions after the first verified deployment.
- Add persistent request/payment audit logs without storing submitted calldata indefinitely.
- Add rate limiting and abuse controls before public promotion.
- Configure uptime monitoring and RPC failover.
- Publish terms, privacy policy, and a support contact.
- Have a recovery/refund policy for paid calls that fail because the RPC provider is unavailable.


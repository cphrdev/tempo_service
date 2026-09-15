# Tempo Weekly Lottery API

An MPP-native weekly lottery for Tempo wallets. Every successful call to
`POST /v1/lottery/enter` costs **0.05 USDC.e** and creates one ticket for the
verified payer address. At the configured weekly cutoff, one ticket wins 90% of
that period's pool; 10% remains in the service wallet.

> **Legal warning:** a paid entry, random winner, and cash prize can constitute a
> regulated lottery or gambling product. Do not operate this publicly or accept
> mainnet funds until qualified counsel confirms that it is lawful in every
> jurisdiction served and that licensing, age/geolocation, AML, sanctions,
> consumer-protection, tax, and responsible-gaming obligations are satisfied.

## API

- `POST /v1/lottery/enter` — one MPP-paid ticket (`0.05 USDC.e`)
- `GET /v1/lottery/status` — current close time, ticket count, pool, projected prize
- `GET /v1/lottery/draws` — public draw and payout audit trail
- `GET /health` — free health check
- `GET /docs` — OpenAPI UI

Example entry:

```bash
TEMPO_MAX_SPEND=0.05 tempo request -X POST \
  https://YOUR_DOMAIN/v1/lottery/enter
```

The MPP payer address becomes the entrant and potential payout address. No JSON
body is required.

## Draw integrity

The default cutoff is Sunday at 20:00 UTC. It is configurable with
`DRAW_WEEKDAY_UTC` (`Monday=0`, `Sunday=6`) and `DRAW_HOUR_UTC`.

For a closed period, the scheduler:

1. Loads every unique verified MPP payment receipt recorded for that period.
2. Uses the hash of the first Tempo block at or after the published cutoff.
3. Sorts ticket payment transaction hashes.
4. Computes `SHA-256("tempo-lottery-v1|cutoff|block-hash|ticket-hashes...")`.
5. Converts the seed to an integer and takes modulo ticket count.
6. Transfers `floor(pool × 9000 / 10000)` USDC.e to the selected payer.

The draw endpoint exposes the block, hash, seed, winning ticket, pool, and payout
transaction so anyone can reproduce the selection.

SQLite enforces one ticket per payment transaction and one draw per period. Once
a draw is selected, the scheduler will not automatically retry it after a payout
error; this prevents a crash around broadcast time from paying twice. An operator
must reconcile the on-chain state before handling a failed draw.

## Wallet requirements

Use a new dedicated low-balance service wallet:

- `PAYMENT_DESTINATION` is its public address and receives ticket payments.
- `LOTTERY_PAYOUT_PRIVATE_KEY` signs the weekly prize transfer.
- The two values must refer to the same secp256k1 account.
- A passkey-only Tempo wallet cannot perform unattended server payouts with this implementation.
- Never use a personal or high-value wallet and never commit the key.

`MPP_SECRET_KEY` signs MPP challenges; it is not a wallet key. Generate it with:

```bash
openssl rand -hex 32
```

## Local setup

```bash
cp .env.example .env
# Fill the three secret/account values in .env.
# Keep LOTTERY_ENABLED=false during setup.
uv sync --dev
uv run pytest
uv run uvicorn app.main:app --reload
```

Confirm the unpaid request advertises exactly `50000` base units (`0.05 USDC.e`):

```bash
curl -i -X POST http://localhost:8000/v1/lottery/enter
```

Inspect the current pool:

```bash
curl http://localhost:8000/v1/lottery/status
```

Test selection without writing a draw or paying:

```bash
uv run python -m app.draw --dry-run
```

## Run behind nginx over HTTPS

Docker Compose runs the API, the single draw scheduler, and nginx. Nginx exposes
ports 80/443; the application remains private on the Compose network. The API
and scheduler share the persistent `lottery-data` volume.

For a local HTTPS test, generate a temporary self-signed certificate:

```bash
cp .env.example .env
# Fill PAYMENT_DESTINATION, MPP_SECRET_KEY, and LOTTERY_PAYOUT_PRIVATE_KEY.
./scripts/generate-self-signed-cert.sh localhost
docker compose up -d --build
curl -k https://localhost/health
```

`-k` is only for the self-signed development certificate. For production, put
the real certificate and key in `nginx/certs/fullchain.pem` and
`nginx/certs/privkey.pem`, change `server_name` in
`nginx/conf.d/default.conf`, and set `MPP_REALM` to the public hostname.

Certificate files are ignored by Git. Reload nginx after renewal:

```bash
docker compose exec nginx nginx -s reload
```

## VPS deployment

Install Docker and Docker Compose, clone this repository, create `.env`, install
the TLS certificate described above, then:

```bash
docker compose up -d --build
docker compose logs -f app scheduler nginx
```

The named Docker volume `lottery-data` stores the ticket/draw database. Back it
up regularly; losing it loses the ticket ledger. Run exactly one scheduler.

Before enabling public access:

1. Obtain legal approval and implement required jurisdiction/age restrictions.
2. Test end-to-end on a non-production environment with disposable funds.
3. Confirm the service wallet can make a TIP-20 transfer and pay its network fee.
4. Confirm a raw request returns a 402 challenge for `0.05 USDC.e` on chain 4217.
5. Make one real capped entry and verify it appears in `/v1/lottery/status`.
6. Back up the persistent volume and configure monitoring/alerts.
7. Publish official rules, eligibility, refund/failure policy, privacy policy, and support contact.

Set `LOTTERY_ENABLED=true` only after completing the checklist. With its default
value of `false`, the API returns `503` and cannot accept paid entries.

Only after the live service is stable should it be registered with
[MPPScan](https://www.mppscan.com/) or submitted to the
[MPP service directory](https://mpp.dev/services).

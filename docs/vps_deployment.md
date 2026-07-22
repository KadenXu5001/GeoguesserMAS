# VPS Deployment Plan

## Goal and budget

Deploy the existing GeoGuessr application to one Ubuntu 24.04 VPS with the least operational
complexity practical while keeping total recurring project spend at or below $15 per month. The
budget includes the VPS, Google Cloud usage, and paid model calls, so provider selection and
application-level model spending controls are part of the deployment gate.

## Authoritative architecture

- One Ubuntu 24.04 VPS.
- Docker Engine with the Docker Compose plugin.
- An `app` container containing the production Node.js server and Python MAS runtime.
- A `mongodb` container reachable only on the private Compose network, with a named persistent
  volume and authentication enabled.
- A `caddy` container as the only public entry point on ports 80 and 443, with persistent Caddy data
  and configuration volumes.
- The existing private `gs://worldwide_images_geotrainer` bucket remains the media source of truth.
  For the first VPS release, synchronize the immutable runtime media to a persistent read-only VPS
  directory and mount it into `app`; do not make the bucket public.
- Nightly MongoDB dumps are encrypted or otherwise access-controlled and uploaded to a dedicated
  backup prefix in the existing Google Cloud Storage bucket with retention pruning.
- LangSmith remains mandatory for production MAS traces.

Caddy runs in Docker Compose. Do not also install and manage a second host-level Caddy service.
Only Docker, the Compose plugin, Git, firewall/security tooling, and the small backup/media-sync
client belong on the host.

## Constitutional constraints

The hosting change does not alter MAS behavior. Production must continue to enforce:

- one isolated MAS invocation per run and the existing timeout-only retry rule;
- a 215-second child-process deadline;
- at most 15 seconds for termination and synchronous trace cleanup after that deadline;
- no replacement run after the outer deadline;
- the three-minute and $0.50 per-run capacity limits; and
- mandatory synchronous LangSmith trace delivery with raw image bytes redacted.

Caddy must not impose an upstream timeout shorter than 240 seconds. Docker shutdown handling must
stop new traffic, terminate or supervise active MAS children, allow the required trace-cleanup
grace, close MongoDB clients, and then exit. A forced shutdown must log the observability failure.

## Capacity and cost guardrails

A 2 GiB VPS is the minimum candidate, not an assumed proof of capacity. Node, MongoDB, the Python
runtime, and a live MAS process must be measured together. Configure swap for installation/build
headroom, keep concurrent MAS executions at one, and reject rather than queue unbounded work. If a
representative run approaches the memory limit or invokes the OOM killer, move to a low-cost 4 GiB
plan or stop for a budget decision.

Before ordering a server, confirm that its monthly price leaves a model-usage reserve under the $15
total cap. A $12 VPS leaves too little safe margin for routine paid inference. Persist a monthly
model-cost ledger, stop starting runs before the configured monthly ceiling, and retain provider
quotas and billing alerts as secondary controls.

As verified from official provider pricing on 2026-07-21, the current recommendation is Hetzner
CX33 (4 GiB) in Nuremberg at $9.99 per month plus $0.60 for primary IPv4, excluding tax. This leaves
materially more room than DigitalOcean's $12 Basic 1 vCPU / 2 GiB plan and provides twice the RAM.
Keep the application monthly MAS ceiling at $3 initially and lower it if tax plus measured GCS
charges would otherwise bring the total projection above $15. Do not order the server until the
user approves this exact provider, plan, region, and price.

## Phase 1: Provision the VPS

1. Choose DigitalOcean or Hetzner based on current total monthly price, region, included transfer,
   IPv4 cost, disk, and a minimum of 2 GiB RAM. Prefer a lower-cost 4 GiB option when it fits the
   budget.
2. Create one Ubuntu 24.04 server using SSH-key authentication only.
3. Record the provider, plan, region, public IP, server identifier, and verified monthly price in
   `Cloud envs.md`; never record private SSH keys.
4. Verify SSH access using a non-root sudo user.
5. Apply provider-side firewall rules for SSH from the administrator's trusted source when
   practical, plus public TCP 80 and 443.

**Gate:** key-based SSH works, the server identity and cost are recorded, and no application or
database port is publicly exposed.

## Phase 2: Secure and prepare the host

1. Update system packages and enable unattended security updates.
2. Install Docker Engine from Docker's supported Ubuntu repository, the Docker Compose plugin, and
   Git.
3. Add the deployment user to the Docker group only if the operational convenience is accepted as
   root-equivalent access.
4. Configure UFW to deny incoming traffic by default and allow only SSH, HTTP, and HTTPS.
5. Disable password authentication and direct root SSH login after confirming a second working SSH
   session.
6. Configure swap and basic disk/log rotation.
7. Install and authenticate the selected GCS sync/backup client with a dedicated least-privilege
   identity. Prefer Workload Identity Federation; if a service-account key is unavoidable, keep it
   outside the repository with restrictive permissions and a documented rotation/revocation path.

**Gate:** Docker and Compose work, host hardening is verified without losing SSH access, and the
GCS identity can read runtime media and write only the backup prefix.

## Phase 3: Finish production application readiness

1. Add process-level tests for `PORT`, `0.0.0.0`, `/healthz`, SIGTERM, MongoDB client closure, and
   active MAS child cleanup.
2. Persist active rounds in MongoDB with ownership, creation/expiration timestamps, an atomic
   one-time guess update, and a TTL index.
3. Add authentication and ownership checks for paid endpoints.
4. Add Mongo-backed per-user and per-IP throttling, a per-instance MAS concurrency limit of one,
   and a global monthly model-spend stop.
5. Complete a local production-image smoke test against the Compose MongoDB service.
6. Verify focused Node/Python tests and `git diff --check`.

**Gate:** persistent state and paid endpoints are protected, all constitutional runtime guarantees
remain enforced, and the production image passes locally.

## Phase 4: Define the Compose deployment

Create a production Compose configuration with:

- `app`: built from the repository Dockerfile, `restart: unless-stopped`, internal port 3000,
  MongoDB and media mounts, a health check, explicit resource/log limits, and no host port;
- `mongodb`: pinned MongoDB 8 image, authentication, named data volume, health check, backup access,
  and no published port; and
- `caddy`: pinned Caddy 2 image, ports 80/443, persistent `/data` and `/config` volumes, the
  `Caddyfile`, and dependency on a healthy app.

Keep production secrets in a root-owned VPS environment file outside Git. Commit only placeholders
and documented variable names. Pin image versions rather than relying on `latest`.

The Caddyfile must name the production domain, proxy to `app:3000`, preserve the real client IP
contract used by throttling, and allow the constitutional request duration. Caddy automatically
obtains HTTPS certificates only after DNS resolves to the VPS and ports 80/443 are reachable.

**Gate:** `docker compose config` is valid, MongoDB is private, Caddy is the only published service,
volumes survive recreation, and secrets are absent from the image and repository.

## Phase 5: Deploy and connect external services

1. Clone the repository into a fixed deployment directory on the VPS.
2. Place the production environment file and GCS credentials/configuration outside the checkout.
3. Synchronize `runtime-private/` from the existing bucket into the persistent media directory and
   verify counts plus representative SHA-256 hashes.
4. Start the stack with `docker compose up -d --build`.
5. Run MongoDB initialization for validators and indexes, then import the verified local database.
6. Configure Gemini, LangSmith, and only the other API credentials actually required by production.
7. Point the domain's A/AAAA records to the VPS and verify Caddy-managed HTTPS.

**Gate:** the public HTTPS health endpoint succeeds, authenticated application flows work, private
images render from the GCS-backed mirror, and MongoDB records match the source counts and samples.

## Phase 6: Backups, hardening, and acceptance

1. Add a root-owned backup script and systemd timer that runs `mongodump --archive --gzip`, uploads
   a uniquely dated object to the dedicated private GCS backup prefix, and prunes according to the
   recorded retention policy.
2. Never place MongoDB credentials or a service-account private key in command output, Git, the
   container image, or world-readable files.
3. Perform and document one restore drill into a disposable database before accepting backups.
4. Verify UFW, SSH settings, automatic updates, container restart policies, disk usage, log
   rotation, and the monthly cost stop.
5. Restart the VPS and prove that HTTPS returns, MongoDB data persists, and media remains available.
6. Run a representative production MAS request and inspect its LangSmith trace and cleanup behavior.

**Gate:** HTTPS and media work after reboot, MongoDB survives container and VPS restarts, a backup
has been restored successfully, paid endpoints are protected, and projected recurring spend is at
or below $15 per month.

## Routine deployment

After reviewing incoming changes and migrations:

```bash
git pull --ff-only
docker compose up -d --build
docker compose ps
```

Do not use an unqualified `git pull`, and take a database backup before a release containing a
schema or migration change. Roll back by redeploying the previously recorded Git commit and image,
not by deleting persistent volumes.

## Committed deployment artifacts

- `compose.yaml` is the production stack. `compose.mongodb-dev.yaml` retains the unauthenticated,
  host-published MongoDB workflow for local development only.
- `.env.production.example` is the production variable inventory. Copy it to
  `/etc/geotrainer/production.env`, replace every placeholder, set owner `root:root`, and set mode
  `0600`. Use URL-safe generated MongoDB passwords; do not commit the populated file.
- `deploy/Caddyfile` leaves `/healthz` public and requires Caddy Basic Auth for everything else.
  Generate the password hash with the pinned Caddy image and escape every `$` as `$$` in the
  Compose environment file.
- `deploy/scripts/sync_media.sh` synchronizes both private media namespaces into the persistent
  host mirror. Run it through `bash` after authenticating the least-privilege GCS identity, then
  run `verify_media_sync.sh` to compare cloud/local counts and verify every content-addressed local
  object against the SHA-256 digest in its filename.
- `deploy/scripts/check_vps_readiness.sh` is the single pre-start gate. It verifies private GCS
  access, runs the incremental media sync and full integrity check, and validates the production
  Compose configuration.
- `deploy/scripts/backup_mongodb.sh`, `deploy/scripts/restore_drill.sh`, and the systemd unit/timer
  implement streamed nightly backup, non-empty uploaded-object verification, and explicit
  disposable restore verification. The restore drill compares every collection count and a stable
  representative `_id`. Configure GCS lifecycle retention on the backup prefix rather than
  granting the host identity broad delete access solely for pruning.
- `deploy/scripts/import_mongodb.sh` performs an explicitly confirmed, checksum-verified initial
  production import, reruns validators/indexes, and restarts the app. `database_inventory.sh`
  produces the canonical collection-count and representative-record inventory for comparison.
- `deploy/scripts/verify_public_deployment.sh` proves public HTTPS, public health, anonymous denial,
  authenticated access, and key browser security headers without putting the password in a process
  argument. Its curl config must be root-owned and mode `0600`.

Prepare and start a new host checkout with:

```bash
sudo install -d -m 0700 /etc/geotrainer
sudo install -m 0600 .env.production.example /etc/geotrainer/production.env
getent group geotrainer-media >/dev/null || sudo groupadd --gid 2000 geotrainer-media
sudo install -d -o root -g geotrainer-media -m 0750 /srv/geotrainer/media
sudo bash deploy/scripts/check_vps_readiness.sh
sudo docker compose --env-file /etc/geotrainer/production.env up -d --build
sudo docker compose --env-file /etc/geotrainer/production.env ps
```

Keep `GEOTRAINER_MEDIA_GID` equal to the numeric GID created on the host. Compose adds that group to
the non-root app process, allowing it to read the `root:<media-group>` `0640` files through the
read-only bind mount without making the private media world-readable.

Install the backup timer only after a manual upload and restore drill succeed:

```bash
sudo install -m 0600 deploy/backup.env.example /etc/geotrainer/backup.env
sudo install -m 0644 deploy/systemd/geotrainer-mongodb-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now geotrainer-mongodb-backup.timer
sudo systemctl list-timers geotrainer-mongodb-backup.timer
```

## Initial MongoDB migration and comparison

Before uploading the local database, capture its inventory and compressed archive from the machine
that currently hosts it. The example assumes the existing unauthenticated localhost database; use
a protected MongoDB tools configuration when the source itself requires credentials.

```bash
MONGO_APP_DATABASE=geoguesser mongosh mongodb://127.0.0.1:27017/geoguesser \
  --quiet --file deploy/mongodb/inventory.js > source-inventory.json
mongodump --uri mongodb://127.0.0.1:27017 --db geoguesser \
  --archive=geoguesser.archive.gz --gzip
sha256sum geoguesser.archive.gz > geoguesser.archive.gz.sha256
gcloud storage cp geoguesser.archive.gz \
  gs://worldwide_images_geotrainer/backups/mongodb/migration/geoguesser.archive.gz
```

On the VPS, supply the recorded digest and explicit database confirmation:

```bash
export ALLOW_REPLACE_DATABASE=geoguesser
sudo --preserve-env=ALLOW_REPLACE_DATABASE bash deploy/scripts/import_mongodb.sh \
  gs://worldwide_images_geotrainer/backups/mongodb/migration/geoguesser.archive.gz \
  REPLACE_WITH_RECORDED_SHA256
sudo bash deploy/scripts/database_inventory.sh > production-inventory.json
diff --unified source-inventory.json production-inventory.json
```

Do not proceed if the inventories differ. Remove the migration object according to the recorded
retention policy after the off-host nightly backup and restore drill have independently succeeded.

## Public acceptance command

After DNS resolves and Caddy has obtained a trusted certificate:

```bash
sudo install -m 0600 deploy/curl-auth.conf.example /etc/geotrainer/curl-auth.conf
sudoedit /etc/geotrainer/curl-auth.conf
sudo GEOTRAINER_PUBLIC_URL=https://YOUR_DOMAIN \
  bash deploy/scripts/verify_public_deployment.sh
```

Then restart MongoDB and the VPS separately, rerunning the public acceptance command and database
inventory after each restart. A representative paid MAS request must additionally demonstrate the
215-second/15-second child boundary, peak memory, monthly ledger update, and a complete redacted
LangSmith trace before the deployment gate is closed.

The local production smoke test on 2026-07-21 verified a successful image build, Compose schema
initialization, public health `200`, anonymous application `401`, authenticated application `200`,
Mongo-backed round survival across a MongoDB container restart, TTL indexes, graceful app SIGTERM
with exit code 0, and a compressed dump/restore with matching representative counts. Idle local
usage was approximately 24 MiB app, 191 MiB MongoDB, and 12 MiB Caddy. Peak MAS memory and public
HTTPS remain VPS acceptance checks.

On 2026-07-22, a native Linux-volume permission check additionally proved that the non-root app
process with supplementary GID `2000` can read root-owned `0640` media while the bind mount remains
read-only. The complete test baseline was 172 Python tests and 30 Node tests, plus a successful
production frontend build.

## Deferred improvements

- Move MongoDB to Atlas only if the monthly budget increases and managed operation becomes more
  valuable than the additional cost.
- Add external uptime and resource alerts.
- Add CI/CD after the manual deployment and rollback path are proven.
- Replace the synchronized media mirror with direct signed-URL or workload-federated GCS access if
  the code change later reduces operational burden.

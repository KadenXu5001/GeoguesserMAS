# Google Cloud Deployment Plan

> **Superseded on 2026-07-21.** The active deployment target is the single-VPS architecture in
> [`vps_deployment.md`](vps_deployment.md). Retain this document as historical context for the
> completed Google Cloud Storage work; do not create Cloud Run, Artifact Registry, Cloud Build, or
> MongoDB Atlas resources from this plan unless the deployment decision changes again.

## Recommended architecture

Deploy the application using:

- **Cloud Run** for the Node web server and Python MAS runtime;
- **Artifact Registry** for the application container image;
- **Cloud Build** for repeatable builds and deployments;
- **Cloud Storage** for private panorama and rendered-view media;
- **MongoDB Atlas on Google Cloud** for MongoDB data;
- **Secret Manager** for API keys and database credentials;
- **Cloud Logging and Monitoring** for platform telemetry; and
- **LangSmith** for the mandatory production MAS traces.

This is the lowest-change path for the current application. Replacing MongoDB with Firestore or
rewriting the object-store layer around a different API would create substantially more migration
work.

## How to use this plan

The requirement sections below explain what the deployment must contain; they are not an execution
order. Perform deployment work only through the **Sequential deployment checklist** later in this
document. That checklist is dependency-ordered so it can be followed from top to bottom without
requiring a Cloud Run service before its container image exists.

## Current readiness assessment

The application should not receive public production traffic in its present form. The working tree
contains part of the required Cloud Run readiness work, but the remaining application safeguards,
data migration, infrastructure, and end-to-end validation must be completed in checklist order.

### 1. Make the HTTP server compatible with Cloud Run

The working tree now includes Cloud Run port and host handling, `/healthz`, and `SIGTERM` shutdown
handling. Focused tests and a production-container smoke test must still verify that the server:

- use the Cloud Run-provided `PORT` environment variable, with a local fallback;
- listen on `0.0.0.0`;
- expose a lightweight `/healthz` endpoint; and
- shut down cleanly on `SIGTERM`, including closing MongoDB connections.

### 2. Add container and deployment definitions

The working tree now includes a multi-stage `Dockerfile` and `.dockerignore`. They must be validated
before an image is pushed. The production image must contain:

- a supported Node runtime and production Node dependencies;
- Python 3.11 or newer and the pinned Python dependencies;
- the built Vite frontend;
- `src/`, the production scripts, reference snapshots, and dataset definitions;
- a non-root runtime user; and
- a start command that runs `node web/server.js`.

Use a multi-stage build so frontend build dependencies do not unnecessarily inflate the runtime
image. Add a `.dockerignore` that excludes local environments, caches, artifacts, secrets, legacy
media, and the local object-store contents.

### 3. Move media to Cloud Storage

The current `.local-data` object store contains approximately **1.44 GB across 2,110 files**.
Cloud Run's ordinary container filesystem is ephemeral, so these objects must not be written into
or maintained inside a running container.

The storage requirement spans several deployment phases. Create the private bucket and grant the
runtime service account bucket-level `roles/storage.objectViewer` before verifying the upload. The
bucket root must contain `runtime-private/` and `source-private/`; it must not flatten either
namespace into a root-level `countries/` directory. Mount the verified bucket read-only at
`/mnt/geoguesser` and set `LOCAL_OBJECT_STORE_ROOT=/mnt/geoguesser` only while creating the Cloud Run
service, after its container image has been pushed.

A Cloud Storage volume mount is appropriate here because both Node and Python currently consume
media using filesystem paths. A future optimization may serve panorama media with short-lived
signed URLs, but that is not required for the first release.

### 4. Move MongoDB to Atlas

The local `compose.yaml` MongoDB service is for development only. MongoDB must not run inside the
Cloud Run service.

For production:

1. Create a MongoDB Atlas cluster on Google Cloud in the same region as Cloud Run.
2. Create a least-privilege application database user.
3. Export the local database and restore it into Atlas.
4. Run the repository's MongoDB initialization so validators and indexes exist.
5. Store the Atlas connection string in Secret Manager as `MONGODB_URI`.
6. Restrict Atlas network access. Do not leave `0.0.0.0/0` enabled for production.

Private networking is preferred for production. Public TLS access may be acceptable for a brief,
controlled staging deployment if strong credentials and a restricted egress address are used.

### 5. Persist active rounds

Active rounds currently live in an in-memory JavaScript `Map`. That state is lost when an instance
restarts, and a request routed to another Cloud Run instance cannot see it.

Persist the following round state in MongoDB:

- round ID;
- panorama/source identity;
- creation and expiration times;
- answered status; and
- submitted and correct-country results.

Add a TTL index so abandoned rounds expire automatically. Until this is implemented, a staging
service may use one maximum instance, but even that configuration cannot protect rounds from an
instance restart.

### 6. Protect paid analysis

The analysis endpoint can trigger a paid MAS run and must not be left as an unrestricted public
endpoint.

Before public launch, add:

- application authentication or an equivalent access control;
- per-user and per-IP rate limits;
- a server-side limit on concurrent MAS subprocesses;
- conservative Cloud Run maximum-instance settings;
- model-provider quota limits where available; and
- billing budgets and alerts.

Budgets and alerts are monitoring controls, not hard spending caps. The runtime-enforced MAS cost
ceiling remains the authoritative per-run control.

## Initial Cloud Run configuration

Use the following as a conservative starting point and adjust it using observed production data:

| Setting                              | Initial value                                    |
| ------------------------------------ | ------------------------------------------------ |
| CPU                                  | 2 vCPU                                           |
| Memory                               | 4 GiB                                            |
| Execution environment                | Generation 2                                     |
| Request timeout                      | 240 seconds                                      |
| Minimum instances                    | 0 for staging; 1 if cold starts are unacceptable |
| Maximum instances                    | 1 until rounds are persistent; then 3-5          |
| Container concurrency                | 4-8                                              |
| Concurrent MAS analyses per instance | 1                                                |
| Cloud Storage mount                  | Read-only                                        |

The request timeout allows the constitutional three-minute MAS ceiling plus bounded synchronous
LangSmith trace flushing. The application must still stop model and tool calls at the internal
three-minute or $0.50 boundary; the Cloud Run timeout is not a replacement for that enforcement.

## Secrets and configuration

Store these values in Secret Manager when they are required by the deployed runtime:

- `GEMINI_API_KEY`;
- `LANGSMITH_API_KEY`;
- `MONGODB_URI`;
- `MAPILLARY_ACCESS_TOKEN`, if production ingestion is enabled; and
- `ANTHROPIC_API_KEY`, if the production model configuration uses it.

Keep non-sensitive configuration as normal environment variables, including:

- `MONGODB_DATABASE`;
- `LANGSMITH_PROJECT`;
- `LANGSMITH_ENDPOINT`;
- model names; and
- cache-version identifiers.

Use a dedicated Cloud Run service account. Grant it only permission to read the required secrets,
read the media bucket, and write platform logs. Do not copy `.env` into the container image.

## Sequential deployment checklist

Follow these phases in order. Do not perform a later phase merely because its console page is
available; each phase ends with the prerequisites for the next one.

### Phase 1: Verify the project foundation

1. Confirm that `gen-lang-client-0756913587` is the intended staging project and that billing is
   enabled.
2. Enable the Cloud Run, Cloud Build, Artifact Registry, Secret Manager, and Cloud Storage APIs.
3. Use `us-east1` for regional Google Cloud resources.
4. Verify that the runtime service account
   `geotrainerserviceaccount@gen-lang-client-0756913587.iam.gserviceaccount.com` exists.
5. Do not create or download a service-account JSON key; Cloud Run will attach this identity
   directly.

**Gate:** the project, billing, APIs, region, and runtime identity are verified.

### Phase 2: Finish bucket IAM and media migration

1. Confirm the existing private `worldwide_images_geotrainer` bucket is in `us-east1`.
2. On that bucket, grant the runtime service account only
   `roles/storage.objectViewer`; do not grant a project-wide storage administration role.
3. Upload the local `.local-data/runtime-private/` directory so the bucket contains
   `runtime-private/` at its root.
4. Upload the local `.local-data/source-private/` directory so the bucket contains
   `source-private/` at its root.
5. Verify 1,668 `runtime-private` files and 442 `source-private` files, for 2,110 total objects.
6. Compare sample local and uploaded SHA-256 object names or hashes.
7. After the correct namespaces are verified, remove any accidental root-level `countries/`
   duplicate.
8. Do not mount the bucket yet; no Cloud Run service or image is required for this phase.

**Gate:** the bucket has least-privilege read access and the two exact, verified namespaces.

### Phase 3: Finish application and database readiness

1. Run focused tests for the implemented `PORT`, `0.0.0.0`, `/healthz`, and graceful-shutdown
   behavior.
2. Persist active round state in MongoDB and add the TTL index.
3. Add authentication, per-user and per-IP throttling, and a per-instance MAS concurrency limit.
4. Create a MongoDB Atlas cluster on Google Cloud in the selected compatible region.
5. Create a least-privilege Atlas application database user and choose the production network
   access strategy. Do not leave `0.0.0.0/0` enabled for production.
6. Export the local database, restore it into Atlas, and run the repository's MongoDB
   initialization for validators and indexes.
7. Compare collection counts and representative records before proceeding.
8. Validate the `Dockerfile` and `.dockerignore` with the focused application tests and a local
   production-container smoke test.

**Gate:** the application is container-ready, persistent state and paid endpoints are protected,
and Atlas contains the verified database.

### Phase 4: Create deploy-time resources

1. Create a Docker repository in Artifact Registry in `us-east1`.
2. Create Secret Manager secrets for `GEMINI_API_KEY`, `LANGSMITH_API_KEY`, and `MONGODB_URI`, plus
   the optional provider secrets actually used by the selected production configuration.
3. Grant the runtime service account `roles/secretmanager.secretAccessor` on each required secret,
   not broadly across unrelated secrets.
4. Create billing budgets, alerts, and applicable provider quota limits.

**Gate:** the image repository, secret references, and cost-monitoring controls exist.

### Phase 5: Build and push the image

1. Build the production image from the validated `Dockerfile`.
2. Run the full local production-container smoke test against non-production dependencies.
3. Tag the passing image with an immutable release identifier rather than relying only on
   `latest`.
4. Authenticate Docker or Cloud Build to Artifact Registry and push the immutable tag.
5. Verify the exact image URI and digest in Artifact Registry.

**Gate:** an immutable, tested image is available in Artifact Registry. Only now proceed to Cloud
Run.

### Phase 6: Create the staging Cloud Run service

1. Create a Cloud Run **service** in `us-east1` using the verified Artifact Registry image.
2. Attach
   `geotrainerserviceaccount@gen-lang-client-0756913587.iam.gserviceaccount.com` as the runtime
   service identity.
3. Mount the entire `worldwide_images_geotrainer` bucket read-only at `/mnt/geoguesser`.
4. Set `LOCAL_OBJECT_STORE_ROOT=/mnt/geoguesser`.
5. Expose required Secret Manager values to their matching runtime environment variables and set
   the required non-sensitive environment variables.
6. Apply the initial CPU, memory, Generation 2, 240-second request timeout, concurrency, and health
   check settings from this document.
7. Keep maximum instances at 1 until persistent round-state behavior has passed staging tests;
   raise it only after that gate succeeds.
8. Deploy the staging revision. Because this is a dedicated staging project/service, do not route
   production users to it.

**Gate:** a staging revision is running with the intended identity, storage mount, configuration,
secrets, and resource limits.

### Phase 7: Verify staging and promote deliberately

Verify all of the following before any production traffic is allowed:

- the health endpoint succeeds;
- a round can be created and retrieved;
- the panorama and four cardinal views load;
- a guess can be submitted only once;
- an uncached analysis completes within the runtime ceiling;
- a repeated analysis uses the permitted persisted result rather than rerunning the MAS;
- concurrent duplicate analysis requests do not start duplicate work;
- active rounds survive an instance restart and multiple instances;
- LangSmith receives the required redacted trace and synchronous flush result;
- trace failures are clearly reported as observability failures;
- no secret or raw base64 image is present in platform logs; and
- application and provider spending alerts work.

Then inspect platform IAM, logs, revision settings, the image digest, and the LangSmith trace one
final time. Promote the verified image and configuration through an explicit production deployment;
do not rebuild a different image during promotion.

## Constitutional acceptance criteria

Deployment is acceptable only if it preserves all production invariants in `CONSTITUTION.md`,
including:

- all four cardinal images and the structured extraction reach the multimodal supervisor;
- extraction remains the required single-use phase 0 tool call;
- at least one permitted specialist runs on every production MAS invocation;
- deterministic reference knowledge remains backed by the versioned local snapshot and never by
  live web browsing during inference;
- tool ordering, retry restrictions, specialist limits, and cache-read limits remain enforced in
  runtime middleware;
- the hard three-minute or $0.50 ceiling remains enforced before further API calls;
- LangSmith tracing remains mandatory for production runs;
- raw base64 image data remains redacted from uploaded traces;
- trace delivery is flushed synchronously before the MAS process exits; and
- any future authentication UI or other visible frontend change is specified in
  `FRONTEND_DESIGN.md` before implementation.

Cloud Run scaling, request timeouts, retries, and health checks must never be used to bypass or
weaken these invariants.

## Completion gate for implementation

Before considering the deployment work complete:

- run the Python test suite;
- run the Node server tests;
- build the production frontend;
- run a local production-container smoke test;
- run staging smoke tests against real Cloud Storage, Atlas, model, and LangSmith dependencies;
- confirm that the implementation matches `CONSTITUTION.md`; and
- ensure `git diff --check` passes.

## References

- [Cloud Run container runtime contract](https://docs.cloud.google.com/run/docs/container-contract)
- [Cloud Run Cloud Storage volume mounts](https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts)
- [Cloud Run secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [Cloud Run request timeouts](https://docs.cloud.google.com/run/docs/configuring/request-timeout)
- [Cloud Run health checks](https://docs.cloud.google.com/run/docs/configuring/healthchecks)
- [Cloud Run concurrency](https://docs.cloud.google.com/run/docs/about-concurrency)
- [Cloud Build deployment to Cloud Run](https://docs.cloud.google.com/build/docs/deploying-builds/deploy-cloud-run)
- [MongoDB Atlas connections with Google Cloud](https://www.mongodb.com/docs/atlas/manage-connections-google-cloud/)

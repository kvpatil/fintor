# Deploying Fintor

Target is **Google Cloud Run**: one container, scales to zero, and the free tier covers
demo traffic. Nothing in the image is GCP-specific — it runs the same on AWS App Runner
or anywhere that injects `$PORT`.

```bash
docker build -t fintor .
docker run -e PORT=8080 -p 8080:8080 -e OPENAI_API_KEY=sk-... fintor
```

Measured: **1.11 GB** image, health green ~20 s after start.

---

## 1. Build and push

```bash
PROJECT=your-project-id
REGION=us-central1

gcloud artifacts repositories create fintor --repository-format=docker --location=$REGION
gcloud builds submit --tag $REGION-docker.pkg.dev/$PROJECT/fintor/app
```

## 2. Secrets

Never pass these as plain `--set-env-vars`; they end up in the service description and
in deployment logs.

```bash
printf 'sk-...'            | gcloud secrets create openai-key      --data-file=-
printf 'a-long-random-str' | gcloud secrets create fintor-password --data-file=-
openssl rand -hex 32       | gcloud secrets create fintor-session  --data-file=-
```

| Secret | Why |
|---|---|
| `OPENAI_API_KEY` | Without it the app still runs, in offline mode with canned answers |
| `FINTOR_DEMO_PASSWORD` | **Required in public.** `config.yaml` ships `fintor` as a published default and the README states it, so an un-overridden deployment is open to anyone who read it. Setting this also stops the sign-in screen pre-filling. |
| `FINTOR_SESSION_SECRET` | Signs the session cookie. Optional — it falls back to a password-derived key — but set it so you can rotate one without the other. |
| `LANGFUSE_*` | Optional. Absent keys mean tracing is simply off. |

## 3. Deploy

```bash
gcloud run deploy fintor \
  --image $REGION-docker.pkg.dev/$PROJECT/fintor/app \
  --region $REGION --allow-unauthenticated \
  --session-affinity \
  --no-cpu-throttling \
  --timeout 3600 \
  --memory 2Gi --cpu 2 \
  --min-instances 0 --max-instances 2 \
  --set-secrets OPENAI_API_KEY=openai-key:latest,\
FINTOR_DEMO_PASSWORD=fintor-password:latest,\
FINTOR_SESSION_SECRET=fintor-session:latest
```

Every flag earns its place:

| Flag | Why, specifically |
|---|---|
| `--session-affinity` | Streamlit is a stateful websocket app. `st.session_state` holds the signed-in persona and the transcript, and it lives in one process. Without affinity the app does not work at all. |
| `--no-cpu-throttling` | `state.py` runs `asyncio.run()` per turn. Cloud Run throttles CPU between requests by default, which stalls a graph mid-run. |
| `--timeout 3600` | The default 300 s closes the websocket every five minutes and the UI reconnects. |
| `--memory 2Gi` | The container writes four SQLite files to an in-memory overlay, on top of the model and the index. |
| `--max-instances 2` | A cost ceiling, not a performance setting. See below. |

## 4. Cost, and why `--max-instances` is the real control

The app has a budget kill switch — `CostMeter`, default `$0.50` — but **it is per
container process, not per user**. `get_deps()` is `@st.cache_resource`, so one meter is
shared by everyone on an instance and it resets when the instance recycles.

So the ceiling is `max-instances × FINTOR_SESSION_BUDGET_USD`, re-armed on every cold
start. For a public URL, bound it in three places:

1. `--max-instances 2`
2. `FINTOR_SESSION_BUDGET_USD` set deliberately
3. **A GCP billing budget with an email alert** — the only backstop that survives a bug
   in the app's own meter. Do not skip this one.

Compute itself should be near zero: scale-to-zero plus the free tier.

## 5. What this deployment does not do

Stated plainly, because the gap between a demo and a service is where the interesting
work is.

- **Caches and conversation history are per instance and lost on recycle.** The four
  SQLite files live on the container filesystem. Losing them costs cache hits and
  transcript continuity, not correctness. Deliberately **not** a GCS FUSE mount: SQLite's
  WAL mode is unsafe over network filesystems and corrupts.
- **The six personas are global.** `thread_id` is `persona::<id>`, so two visitors signed
  in as `maya` share one conversation thread. Fine for a demo with sample accounts;
  the first thing to fix for real users.
- **Login throttling is per browser session**, so a new tab resets it.
- **The session cookie is not HttpOnly.** `st.context.cookies` is read-only, so a JS shim
  sets it. Acceptable for six synthetic accounts behind a shared password; wrong for
  real ones.

The next step, if usage justifies it: Memorystore behind the existing `CacheBackend`
port, Cloud SQL for checkpoints, and per-user threads.

## 6. Verifying a deployment

```bash
curl -s -o /dev/null -w '%{http_code}\n' $URL/_stcore/health   # 200
```

`/_stcore/health` answers as soon as the server binds — **before** the container is
built and the model loads. A green probe means the process is up, not that the app
works. Confirm by signing in and asking a question.

Two checks worth repeating after any change to auth or the image:

- **Restart the service, refresh the browser — you should still be signed in.** This
  regressed once: the cookie's signing key was derived from a per-process random salt,
  so every restart silently logged everyone out.
- **Block egress to huggingface.co and start the container.** It must boot. The
  embedding model is baked into the image at `/opt/models` precisely so a third party's
  availability is not in the startup path.

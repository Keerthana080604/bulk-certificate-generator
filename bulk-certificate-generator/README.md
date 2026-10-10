# Bulk Certificate Generator API

A backend API that accepts **one request containing many recipients**, generates an individual PDF certificate for every valid recipient from one predefined template, tracks the job, and lets the client check progress and download the results.

Built with FastAPI, SQLAlchemy 2, SQLite and ReportLab. Everything described here is implemented and covered by the automated tests (69 tests).

## Features

- Bulk job creation in a single `POST` (up to 500 recipients per request).
- Two-level validation: bad request -> rejected; bad recipient -> recorded as `FAILED`, the rest continue.
- Background generation with per-recipient status, so one failure never stops the batch.
- Job status with pending / processing / successful / failed counts and progress percentage.
- Per-job results listing and PDF download.
- Atomic PDF writes (temp file + rename), so a partial file is never served.
- Startup sweep that marks jobs interrupted by a restart as failed (visible, not silent).

## Technology stack

Python 3.11+ (developed on 3.12), FastAPI, SQLite, SQLAlchemy 2.x, Pydantic v2, ReportLab, Pytest + FastAPI TestClient, `logging`.

## Architecture

```
Client
  | POST /api/certificate-jobs/
  v
FastAPI route --- Pydantic validates the envelope --(invalid)--> 422, nothing stored
  |
  v
Job service: validate each recipient, detect duplicates
  |  ONE DB transaction: insert job + all records
  |  (PENDING, or FAILED with an error for invalid recipients)
  v
BackgroundTasks.add_task(process_job) --> 202 {job_id, status, total, status_url}

process_job (its OWN DB session), for each PENDING record:
    PROCESSING + commit
    try:   render PDF to <id>.pdf.tmp -> os.replace -> <id>.pdf
           SUCCESS + pdf filename + commit
    except: delete partial files, FAILED + error + commit
  finally: job status computed from records, completed_at set, commit

Client polls  GET /api/certificate-jobs/{id}/               (counts via GROUP BY)
Client lists  GET /api/certificate-jobs/{id}/certificates/
Client gets   GET /api/certificates/{certificate_id}/download/
```

## Project structure

```
bulk-certificate-generator/
|-- app/
|   |-- main.py          # create_app(): wiring, lifespan (create tables, startup recovery)
|   |-- api/             # HTTP only: routes, status codes, dependencies
|   |-- core/            # config (limits, settings) and logging setup
|   |-- db/              # engine, session factory, Base, SQLite pragmas
|   |-- models/          # SQLAlchemy tables + status enums
|   |-- schemas/         # Pydantic request/response models
|   `-- services/        # validation, job creation, PDF, processor, status rules, recovery
|-- generated_certificates/   # PDF output (contents git-ignored)
|-- examples/sample_request.json
|-- docs/INTERVIEW_PREP.md
|-- tests/
|-- requirements.txt  pytest.ini  .gitignore  README.md
```

There is no `templates/` folder: the template is drawn in code in `app/services/pdf.py`.

## Setup (Windows PowerShell)

```powershell
cd bulk-certificate-generator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# If activation is blocked:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
python -m pip install --upgrade pip
pip install -r requirements.txt
```

macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

## Run the application

```powershell
uvicorn app.main:app --reload
```

- Interactive docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health
- `app.db` and `generated_certificates/` are created automatically.

Optional environment variables: `DATABASE_URL` (default `sqlite:///./app.db`), `CERTIFICATE_OUTPUT_DIR` (default `generated_certificates`).

> Run **one** server process (no `--workers N`): background tasks and the startup sweep assume a single process (see limitations).

## Run the tests

```powershell
python -m pytest            # all tests
python -m pytest -v         # one line per test
python -m pytest tests/test_processing.py -k failure
```

Each test uses its own temporary SQLite file and output folder. Generation failures are simulated by monkeypatching the PDF function, so results are deterministic. `TestClient` finishes background tasks before returning, so tests do not need sleeps. A passing run ends with `69 passed`.

## Submit a request

`examples/sample_request.json` (one recipient has an invalid email on purpose):

```json
{
  "event_name": "Python Workshop",
  "organization": "ABC Institute",
  "issue_date": "2026-10-10",
  "recipients": [
    {"name": "Keerthana Bammidi", "email": "keerthana@example.com", "certificate_title": "Certificate of Completion"},
    {"name": "Rahul Kumar", "email": "rahul@example.com", "certificate_title": "Certificate of Participation"},
    {"name": "Bad Email Person", "email": "not-an-email", "certificate_title": "Certificate of Participation"}
  ]
}
```

```powershell
# Windows PowerShell: use curl.exe (plain "curl" is an alias for Invoke-WebRequest)
curl.exe -X POST http://127.0.0.1:8000/api/certificate-jobs/ -H "Content-Type: application/json" -d "@examples/sample_request.json"

curl.exe http://127.0.0.1:8000/api/certificate-jobs/<job_id>/
curl.exe http://127.0.0.1:8000/api/certificate-jobs/<job_id>/certificates/
curl.exe -o certificate.pdf http://127.0.0.1:8000/api/certificates/<certificate_id>/download/
```

(macOS/Linux: same commands with `curl`.)

## API reference

| Method | Path | Success | Errors |
|---|---|---|---|
| POST | `/api/certificate-jobs/` | 202 | 422 |
| GET | `/api/certificate-jobs/{job_id}/` | 200 | 404 |
| GET | `/api/certificate-jobs/{job_id}/certificates/` | 200 | 404 |
| GET | `/api/certificates/{certificate_id}/download/` | 200 (`application/pdf`, attachment) | 404 |

**POST response (202)**

```json
{
  "job_id": "463c5ab7-27a2-44bf-ad47-854f323a0a26",
  "status": "QUEUED",
  "total_recipients": 3,
  "invalid_recipients": 1,
  "status_url": "http://127.0.0.1:8000/api/certificate-jobs/463c5ab7-27a2-44bf-ad47-854f323a0a26/"
}
```

**GET job status (200)**, abridged

```json
{
  "job_id": "463c5ab7-...",
  "status": "COMPLETED_WITH_ERRORS",
  "total_recipients": 3, "pending": 0, "processing": 0, "successful": 2, "failed": 1,
  "progress_percent": 100.0,
  "created_at": "2026-10-10T14:46:23.602674",
  "completed_at": "2026-10-10T14:46:23.641274",
  "recipients": [
    {"certificate_id": "a343a8d1-...", "name": "Keerthana Bammidi", "status": "SUCCESS",
     "error_message": null, "download_url": "http://127.0.0.1:8000/api/certificates/a343a8d1-.../download/"},
    {"certificate_id": "8ef8a729-...", "name": "Bad Email Person", "status": "FAILED",
     "error_message": "email is not a valid address", "download_url": null}
  ]
}
```

Timestamps are UTC (SQLite stores no time zone, so they carry no `Z` suffix).

### Status definitions

| Recipient status | Meaning |
|---|---|
| `PENDING` | Valid, waiting to be processed |
| `PROCESSING` | Being generated right now |
| `SUCCESS` | PDF fully written, filename stored |
| `FAILED` | Validation or generation failed; `error_message` is set |

| Job status | Meaning |
|---|---|
| `QUEUED` | Accepted; the background task has not started |
| `PROCESSING` | Started; some recipients still `PENDING`/`PROCESSING` |
| `COMPLETED` | Nothing unfinished; all `SUCCESS` |
| `COMPLETED_WITH_ERRORS` | Nothing unfinished; at least one `SUCCESS` and one `FAILED` |
| `FAILED` | Nothing unfinished and no `SUCCESS` (also used if the job crashes or is interrupted before any success) |

**Progress %** = `(SUCCESS + FAILED) / total * 100`. Failed recipients count as processed, so a finished job always reads 100%.

## Validation and error handling

| Level | Examples | Behaviour |
|---|---|---|
| Request | missing/blank/too-long `event_name` or `organization`, bad `issue_date`, empty or >500 recipients, wrong JSON types | `422`, **no job created** |
| Recipient | missing/blank name, invalid email, too-long field, blank title, characters the PDF font can't draw, duplicate | Job accepted; that recipient stored as `FAILED` with a clear message; the rest are processed |

Why this split: the assignment wants valid recipients to still get certificates and invalid ones to be identifiable in the job status. Rejecting 499 good recipients over one typo would contradict that.

- **Limits** (`app/core/config.py`): batch 500, name 100, email 254, title 100, event/organization 150.
- **Duplicates:** same email (case-insensitive) + same certificate title within one request. First valid occurrence wins; later ones fail with "duplicate recipient". The same person with a different title is allowed. Duplicates across separate requests are not detected.
- **Missing `certificate_title`** defaults to "Certificate of Completion"; a blank string is an error.
- **Font limitation:** the template uses built-in Latin fonts, so names with characters outside Windows-1252 (e.g. Telugu, Hindi, Chinese) are rejected per recipient instead of being printed as garbage. Supporting them needs a bundled TTF font.
- **All recipients invalid:** the job is still created (`202`) and is immediately `FAILED`, giving the client an audit trail.
- **Generation failures:** caught per recipient; the partial file is deleted, the record becomes `FAILED` with `Certificate generation failed: <ExceptionType>: <message>`, and processing continues. Full tracebacks go to the log. (A public deployment should show a generic message to clients.)
- **PDF safety:** written to `<id>.pdf.tmp`, then `os.replace()` to `<id>.pdf`; the record turns `SUCCESS` only afterwards.

## Background-processing design and limitations

**Choice:** FastAPI `BackgroundTasks` with state in SQLite. `POST` returns `202` quickly instead of holding the connection open while hundreds of PDFs render, and the client polls the status endpoint. Simple to run locally with no extra services.

**Design points**
- The task opens its **own DB session** (the request session closes when the response is sent).
- It **commits after every recipient**: failures stay isolated, progress is live, a crash loses at most one recipient.
- Counts are **derived** with `GROUP BY status`, never cached, so they cannot drift.

**Limitations (honest list)**
- Tasks run in the web-server process memory. **A restart or crash loses the in-flight work, and nothing resumes it.** It is not a durable or distributed queue.
- Mitigation: on startup, jobs still `QUEUED`/`PROCESSING` are swept: unfinished recipients become `FAILED` ("Interrupted by server restart...") and the job is finalized. This makes the outcome visible; it does **not** resume the work. A leftover `*.pdf.tmp` from a crash is harmless (never served) but not auto-deleted.
- The sweep assumes a single server process; with several workers it could mark another worker's live job as interrupted.
- Processing is sequential and CPU-bound inside the server's thread pool; it does not scale to very large volumes.
- Future: Celery + Redis (or RQ/Arq) for durable, retryable, parallel work.

## Database design

```
generation_jobs (1) ----< (many) certificate_records
```

- `generation_jobs`: `id` (UUID4 PK), `event_name`, `organization`, `issue_date`, `status` (indexed), `total_recipients`, `created_at`, `completed_at`.
- `certificate_records`: `id` (UUID4 PK, also the public certificate ID), `job_id` (FK -> `generation_jobs.id`, indexed), `position`, `recipient_name`, `recipient_email`, `certificate_title`, `status` (indexed), `pdf_path` (filename only), `error_message`, `created_at`, `completed_at`.
- Success/failure counts are **not stored**: they are calculated from the records. `total_recipients` is stored because it never changes. `status`/`completed_at` are written once at finalization.
- SQLite runs with `PRAGMA foreign_keys=ON` and WAL mode (readers are not blocked while the background task writes).
- Tables are created with `create_all` at startup. There are no migrations; a schema change on an existing `app.db` needs the file deleted or Alembic added.

## Security considerations

- **Implemented:** UUID4 identifiers (unguessable, important with no auth); the client never supplies a path (filename is built from the server-generated UUID, and the download re-resolves it inside the output directory); identical 404 for unknown, unsuccessful and missing-file certificates; ReportLab draws text literally (no markup injection); field-length and batch limits; secrets are git-ignored and none are required.
- **Not implemented (assignment says auth is not required):** a public deployment should add authentication/authorization (API keys or OAuth, per-organization ownership of jobs), rate limiting, request-size limits, signed expiring download URLs, HTTPS, and generic client-facing error messages.
- Recipient names/emails are personal data; a real system needs a retention policy.

## Local file storage limitations

PDFs live on the server's local disk: lost with the machine, not shared between multiple servers, no cleanup/retention policy. Future: store in S3/GCS/Azure Blob, keep the object key in `pdf_path`, and serve through short-lived signed URLs.

## Learning outcomes

Designing an async-style API (`202` + polling), choosing a validation policy deliberately, SQLAlchemy sessions/transactions/relationships, failure isolation with per-item commits, atomic file writes, deriving state instead of duplicating it, and writing deterministic tests with temporary databases and monkeypatched failures.

## Future scope

Celery + Redis with retries and parallel workers; object storage with signed URLs; authentication and per-tenant ownership; Alembic migrations; PostgreSQL; Unicode TTF font support; CSV upload; email delivery of certificates; webhook/callback on job completion; a periodic task that detects stale jobs while the server is running; cross-request duplicate detection (unique constraint) or an idempotency key.

## Submit to GitHub

```powershell
git init
git add .
git commit -m "Bulk Certificate Generator API"
git branch -M main
# Create an EMPTY public repo on github.com first (no README/.gitignore), then:
git remote add origin https://github.com/<your-username>/bulk-certificate-generator.git
git push -u origin main
```

With the GitHub CLI instead: `gh repo create bulk-certificate-generator --public --source=. --remote=origin --push`

Before pushing, run `git status` and confirm `.venv/`, `app.db` and generated PDFs are not listed.

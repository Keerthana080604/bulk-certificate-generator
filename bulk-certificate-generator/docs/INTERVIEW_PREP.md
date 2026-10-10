# Interview Preparation

Honest framing: this is a well-structured assignment-level project, not a production system. Say what it does, what it doesn't, and what you'd change. That is more convincing than overselling.

## The four Stage 1 self-test questions

1. **Why does the background task need its own session?** The request's session is closed when the response is sent. A session is also not safe to share across threads. The task opens its own, uses it, and closes it.
2. **Why commit after every recipient?** Failure isolation (a failure affects only that recipient), live progress for pollers, and a crash loses at most one recipient instead of the whole batch.
3. **`FAILED` vs `COMPLETED_WITH_ERRORS`?** `FAILED`: nothing succeeded. `COMPLETED_WITH_ERRORS`: at least one success and at least one failure. A client can act on the difference (retry everything vs. retry the failures).
4. **Server restarts mid-run?** In-process tasks are lost. Records stay `PENDING`/`PROCESSING`. On next startup the sweep marks them `FAILED` ("interrupted") and finalizes the job. Nothing resumes automatically.

## 60-90 second explanation

"This is a Bulk Certificate Generator API in FastAPI with SQLite and ReportLab. A client sends one POST with an event, an organization, a date and up to 500 recipients. I validate the request envelope strictly, so a missing event name returns 422 and creates nothing. Recipient content is validated leniently: a bad email or a duplicate is stored as a FAILED record with a clear error, and everyone else still gets a certificate.

The API returns 202 with a job ID and a status URL, and a FastAPI background task processes recipients one by one in its own database session, committing after each one. It renders the PDF to a temp file and atomically renames it, so a half-written file can never be served. A failure for one recipient is caught, logged and recorded, and the loop continues.

The status endpoint derives counts with a GROUP BY on the records instead of storing counters, so they can't drift, and computes progress as done over total. Job status is COMPLETED, COMPLETED_WITH_ERRORS or FAILED depending on the outcomes. Certificates are downloaded by an unguessable UUID, and only for SUCCESS records.

The main limitation is that BackgroundTasks lives in process memory, so a restart loses in-flight work. I added a startup sweep that marks interrupted jobs as failed so it's visible, and the README says plainly that real durability needs Celery and Redis. I tested it with 69 Pytest tests using temporary databases and mocked failures."

## Twenty likely questions

1. **Why a job ID?** The work finishes after the HTTP response. The ID is the handle the client uses to poll status and find results. It also gives an audit record.
2. **Bulk vs. one request per certificate?** One round trip, one transaction for creation, shared validation and a single trackable unit. N requests mean N times the overhead, no atomic "job", and the client has to coordinate and retry itself.
3. **Why 202 and not 201 or 200?** 202 means accepted for processing but not finished. Nothing is generated yet at response time.
4. **Why background processing instead of synchronous?** 500 PDFs may exceed proxy/client timeouts and give no feedback. Synchronous is simpler and would be fine for small batches. The trade-off is documented.
5. **Why is invalid-recipient handling per recipient, not whole-request?** The assignment says one failure shouldn't prevent others. One typo shouldn't reject 499 good rows. Structural problems (no recipients, bad date) are request errors because nothing meaningful can be processed.
6. **How is progress calculated?** `(SUCCESS + FAILED) / total * 100`. Failed counts as processed, so finished jobs read 100%.
7. **How are failures isolated?** `try/except` around each recipient, own commit per recipient, rollback and cleanup in the except block, then the loop continues. A outer guard handles failures outside a single recipient.
8. **What is a session? A transaction?** A session is a unit of work tracking object changes and holding a DB connection. A transaction groups changes so they commit or roll back together. Job creation inserts the job and all records in one transaction.
9. **Why not store success/failed counters on the job?** They can drift (crash between updating the record and the counter). Deriving from records is always correct, and the query is cheap with an index on `job_id`.
10. **How are PDFs generated?** ReportLab canvas, landscape A4. Border rectangles, centred text at fixed coordinates, font shrunk to fit long names, a signature line and the certificate ID. Values are drawn literally with `drawCentredString`.
11. **Why write to `.tmp` then `os.replace`?** Rename is atomic on the same filesystem, so a file with the final name is always complete. A crash mid-write leaves only a `.tmp` that is never served.
12. **How do you stop path traversal?** The client never supplies paths. Filenames are `<server UUID>.pdf`, the DB stores only the filename, and the download uses `Path(...).name` and checks the resolved parent equals the output directory. A test corrupts the stored path to prove it.
13. **Why do unknown and failed certificates both return 404?** It doesn't reveal which IDs exist or what state they are in.
14. **Limitations of BackgroundTasks?** In-process memory, no persistence, no retries, no parallel workers, tied to the server lifecycle, competes with request handling.
15. **How would you migrate to Celery + Redis?** `POST` still creates the job and records, then calls `process_job.delay(job_id)`. The task body is the same function (it already takes only a job ID and builds its own session). Workers run separately. Add `acks_late`, retries with backoff, and make processing idempotent (skip records that are already `SUCCESS`).
16. **How would you process 100,000 recipients?** Don't accept them in one JSON body; use a file upload (CSV) to object storage. Chunk into batches and fan out tasks to many workers. Use PostgreSQL, store PDFs in S3, throttle DB writes (batch updates), cap per-tenant concurrency, paginate results, optionally zip output or send via email/webhook.
17. **How do you prevent unauthorized downloads?** Authentication, ownership checks (job belongs to the caller's organization), signed expiring URLs for object storage, rate limiting, audit logs. UUIDs alone are obscurity, not authorization.
18. **How do you recover after a restart?** The startup sweep marks unfinished records `FAILED` and finalizes jobs. Better: with a durable queue, unacknowledged tasks are redelivered and the processor skips finished records. Also a periodic stale-job detector (e.g. `PROCESSING` with no update for N minutes).
19. **How would you debug a job stuck in PROCESSING?** Check the status endpoint counts, check logs by job ID, check whether the server restarted, query records for `PROCESSING`, look for orphan `.tmp` files, confirm the sweep ran. Reproduce with that record's data.
20. **What is the weakest part of your design?** In-process durability, no auth, local disk storage, sequential processing, create_all instead of migrations, a Latin-only font. I know each of these and how I'd fix it.

## Debugging exercises

1. **Job stuck `PROCESSING` forever.** Server was killed mid-run. Find the stuck records (`SELECT status, COUNT(*) ... GROUP BY status`), restart so the sweep runs, confirm they became `FAILED`.
2. **Status says `SUCCESS` but download is 404.** The file was deleted or `pdf_path` is wrong. Check `generated_certificates/` and the DB row; the endpoint intentionally returns 404 when the file is missing.
3. **`sqlite3.OperationalError: database is locked`.** Two writers. Check for multiple server processes; WAL and the 30s timeout reduce it, but SQLite allows one writer.
4. **Counts don't add up to total.** Compare `GROUP BY status` with `total_recipients`; look for records inserted outside `create_job`.
5. **Everyone fails with "cannot render".** Names are outside Windows-1252 (e.g. Telugu). Expected; fix by bundling a Unicode TTF font.
6. **Tests pass alone but fail together.** Shared state. Each test must use the `settings`/`app` fixtures with temp paths.

## Changed requirements to practice

1. **Retry failed recipients:** `POST /api/certificate-jobs/{id}/retry/`. Reset `FAILED` records that failed during generation (not validation) to `PENDING`, set job `PROCESSING`, schedule `process_job`. Clear `completed_at`.
2. **Reject the whole request if any recipient is invalid:** do the recipient validation before creating the job and return 422 with a list of errors; delete the failed-record path.
3. **Download all certificates as a ZIP:** new endpoint that streams a zip of the job's `SUCCESS` files; 404 if none.
4. **Per-event template choice:** add a `template` field and a lookup of drawing functions; validate against an allowed list.
5. **Treat duplicates across requests:** unique constraint on (event, email, title) or an idempotency key header.
6. **Send an email/webhook when the job completes:** call it from `finalize_job` after commit (and discuss retry/failure of that call).
7. **Raise the batch limit to 5,000 and keep the API responsive:** discuss payload size, sequential time, moving to a worker pool/Celery, and paginating the status response.
8. **Add API-key authentication:** a dependency checking a header, per-key ownership column on the job, 404 (not 403) for other tenants' jobs.

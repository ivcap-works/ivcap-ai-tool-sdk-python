# Utilities

Helper functions for logging, context access, and URL handling.

## Logging Initialisation

::: ivcap_lambda.logger.logging_init

---

## Context Helpers

These helpers let you access the current job's context from anywhere in your code — useful in helper functions that don't have direct access to `JobContext`.

::: ivcap_lambda.executor.get_event_reporter

::: ivcap_lambda.executor.get_job_id

---

## URL Utilities

::: ivcap_lambda.utils.get_public_url_prefix

---

## Once-per-Key Execution

`once_per_key` runs a function at most once per key. Concurrent callers with the same key share the result and the progress events from that single run.

::: ivcap_lambda.once.once_per_key

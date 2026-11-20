#
# Copyright (c) 2026 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""Run a function at most once per key, sharing its result and events with concurrent callers."""

import logging
import threading
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from ivcap_service import BaseEvent, EventReporter

logger = logging.getLogger(__name__)

R = TypeVar("R")


class _Entry:
    __slots__ = ("done", "value", "error", "reporters")

    def __init__(self) -> None:
        self.done = threading.Event()
        self.value: Any = None
        self.error: BaseException | None = None
        self.reporters: list[EventReporter] = []  # guarded by the shared lock


class _FanOutReporter(EventReporter):
    """Handed to the wrapped function; forwards each event to all current subscribers."""

    def __init__(self, key: Any, entry: _Entry, lock: threading.Lock) -> None:
        super().__init__(job_id=str(key), job_authorization=None)
        self._entry = entry
        self._lock = lock

    def _send(self, event: BaseEvent) -> None:
        with self._lock:
            targets = list(self._entry.reporters)  # snapshot; don't emit under the lock
        for r in targets:
            try:
                r.emit(event)
            except Exception:
                # one bad reporter must not break the others or the job
                logger.exception("reporter %s failed", r.job_id)


def once_per_key(fn: Callable[..., R]) -> Callable[..., R]:
    """Make `fn` run at most once per key, sharing its result and events.

    The decorated function is called as `wrapper(key, reporter=None, **kwargs)`.
    The first caller for a key (the owner) runs `fn(key, events, **kwargs)`, where
    `events` is an `EventReporter` that forwards every event to all current
    subscribers. Other callers with the same key wait for the owner and return the
    same result.

    - Keyword arguments: only the owner's `**kwargs` are passed to `fn`. They are
      not part of the cache key, so kwargs given to later or concurrent callers
      for the same key are ignored.

    - Subscribers: a caller that passes `reporter` receives events emitted after
      it joined, including the owner's own reporter. Events are not replayed.
    - Late callers: once the job has finished, the result is returned from the
      cache and a passed `reporter` is not registered, so it receives nothing.
    - Failures: an exception from `fn` is not cached. It is raised to the owner and
      every caller waiting on that run, and the next call for the key runs `fn` again.
    - Reporter errors: an exception raised by one subscriber is logged and
      ignored, so it cannot fail the job or stop other subscribers.
    - Lock use: the internal lock covers only the key table and subscriber list,
      so a slow subscriber does not block other keys.
    - Retention: successful results are kept for the lifetime of the process
      (there is no eviction).

    Typical use is a lambda tool where several requests need the same expensive
    operation at once. Pass the request's reporter from `get_event_reporter()`
    so that each caller still sees the progress events:

    ```python
    from ivcap_service import GenericEvent
    from ivcap_lambda import get_event_reporter, ivcap_lambda, once_per_key

    @once_per_key
    def load_model(key: str, events: EventReporter, **kwargs: Any) -> str:
        events.emit(GenericEvent(name="loading", options={"model": key}))
        ...
        return "loaded"

    @ivcap_lambda("/predict")
    def predict(req: Request) -> Result:
        status = load_model(req.model, reporter=get_event_reporter(), device="cpu")
        ...
    ```

    Args:
        fn: function taking `(key, events, **kwargs)` and returning the result for `key`.

    Returns:
        A wrapper taking `key`, an optional `reporter` keyword argument, and any
        extra keyword arguments, which are passed to `fn` when the caller owns the run.
    """
    lock = threading.Lock()
    entries: dict[Any, _Entry] = {}

    @wraps(fn)
    def wrapper(key: Any, reporter: EventReporter | None = None, **kwargs: Any) -> R:
        with lock:
            entry = entries.get(key)
            is_owner = entry is None
            if entry is None:
                entry = entries[key] = _Entry()
            if reporter is not None and not entry.done.is_set():
                entry.reporters.append(reporter)  # owner and late joiners alike

        if is_owner:
            try:
                entry.value = fn(key, _FanOutReporter(key, entry, lock), **kwargs)
            except BaseException as e:
                entry.error = e
                with lock:
                    del entries[key]  # don't cache failures
                raise
            finally:
                with lock:
                    entry.reporters.clear()  # drop references; later callers get no events
                    entry.done.set()
        else:
            entry.done.wait()
            if entry.error is not None:
                raise entry.error

        return entry.value

    return wrapper

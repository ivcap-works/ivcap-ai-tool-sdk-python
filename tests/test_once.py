#
# Copyright (c) 2026 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""Tests for ivcap_lambda.once.once_per_key.

Threads coordinate with `threading.Event`s. Where a waiter must have joined
before the owner emits, the test sleeps briefly, since the join happens inside
the wrapper and cannot be observed from outside.
"""

import threading
import time

from ivcap_service import EventReporter, GenericEvent

from ivcap_lambda import once_per_key


class _ListReporter(EventReporter):
    def __init__(self, job_id: str = "test") -> None:
        super().__init__(job_id=job_id, job_authorization=None)
        self.names: list[str] = []
        self._lock = threading.Lock()

    def _send(self, event) -> None:
        with self._lock:
            self.names.append(event.name)


class _BrokenReporter(_ListReporter):
    def _send(self, event) -> None:
        raise RuntimeError("broken reporter")


def test_runs_once_and_returns_cached_result():
    calls = []

    @once_per_key
    def job(key, events):
        calls.append(key)
        return f"result-{key}"

    assert job("k") == "result-k"
    assert job("k") == "result-k"
    assert calls == ["k"]


def test_distinct_keys_run_independently():
    calls = []

    @once_per_key
    def job(key, events):
        calls.append(key)
        return key.upper()

    assert job("a") == "A"
    assert job("b") == "B"
    assert calls == ["a", "b"]


def test_owner_reporter_receives_events():
    @once_per_key
    def job(key, events):
        events.emit(GenericEvent(name="one"))
        events.emit(GenericEvent(name="two"))
        return "ok"

    owner = _ListReporter("owner")
    assert job("k", reporter=owner) == "ok"
    assert owner.names == ["one", "two"]


def test_waiter_gets_only_events_emitted_after_it_joined():
    started = threading.Event()
    gate = threading.Event()
    calls = []

    @once_per_key
    def job(key, events):
        calls.append(key)
        events.emit(GenericEvent(name="before"))
        started.set()
        gate.wait(5)
        events.emit(GenericEvent(name="after"))
        return "done"

    owner = _ListReporter("owner")
    waiter = _ListReporter("waiter")
    results = {}

    t_owner = threading.Thread(
        target=lambda: results.update(owner=job("k", reporter=owner))
    )
    t_owner.start()
    assert started.wait(5)

    t_waiter = threading.Thread(
        target=lambda: results.update(waiter=job("k", reporter=waiter))
    )
    t_waiter.start()
    time.sleep(0.2)  # let the waiter register before the next event
    gate.set()
    t_owner.join(5)
    t_waiter.join(5)

    assert calls == ["k"]
    assert owner.names == ["before", "after"]
    assert waiter.names == ["after"]
    assert results == {"owner": "done", "waiter": "done"}


def test_late_caller_gets_cached_result_and_no_events():
    calls = []

    @once_per_key
    def job(key, events):
        calls.append(key)
        events.emit(GenericEvent(name="only-once"))
        return "ok"

    first = _ListReporter("first")
    late = _ListReporter("late")
    assert job("k", reporter=first) == "ok"
    assert job("k", reporter=late) == "ok"
    assert calls == ["k"]
    assert first.names == ["only-once"]
    assert late.names == []


def test_failure_is_not_cached_and_reaches_waiters():
    started = threading.Event()
    gate = threading.Event()
    attempts = []

    @once_per_key
    def job(key, events):
        attempts.append(key)
        if len(attempts) == 1:
            started.set()
            gate.wait(5)
            raise RuntimeError("boom")
        return "ok"

    owner_errors: list[str] = []
    waiter_errors: list[str] = []

    def call(sink: list[str]):
        try:
            job("k")
        except RuntimeError as e:
            sink.append(str(e))

    t_owner = threading.Thread(target=call, args=(owner_errors,))
    t_owner.start()
    assert started.wait(5)
    t_waiter = threading.Thread(target=call, args=(waiter_errors,))
    t_waiter.start()
    time.sleep(0.2)  # let the waiter join the failing run
    gate.set()
    t_owner.join(5)
    t_waiter.join(5)

    assert owner_errors == ["boom"]
    assert waiter_errors == ["boom"]

    # failure was not cached: the next call runs the function again
    assert job("k") == "ok"
    assert len(attempts) == 2


def test_failing_reporter_does_not_affect_other_subscribers():
    started = threading.Event()
    gate = threading.Event()

    @once_per_key
    def job(key, events):
        events.emit(GenericEvent(name="start"))
        started.set()
        gate.wait(5)
        events.emit(GenericEvent(name="end"))
        return "ok"

    good = _ListReporter("good")
    bad = _BrokenReporter("bad")
    results = {}

    t_owner = threading.Thread(
        target=lambda: results.update(owner=job("k", reporter=good))
    )
    t_owner.start()
    assert started.wait(5)
    t_bad = threading.Thread(target=lambda: results.update(bad=job("k", reporter=bad)))
    t_bad.start()
    time.sleep(0.2)  # let the broken subscriber join
    gate.set()
    t_owner.join(5)
    t_bad.join(5)

    assert results == {"owner": "ok", "bad": "ok"}
    assert good.names == ["start", "end"]


def test_reporter_is_optional():
    @once_per_key
    def job(key, events):
        events.emit(GenericEvent(name="ignored"))
        return key

    assert job("k") == "k"

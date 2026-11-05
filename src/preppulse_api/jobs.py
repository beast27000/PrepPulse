"""Mongo-backed work queue for the deployed single-worker pilot.

Leases and heartbeats recover interrupted work. Remote inference is at-least-once:
an interrupted remote call may be billed again on retry.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument


def enabled():
    return os.getenv("PREPPULSE_DURABLE_JOBS", "0") == "1"


def task_key(function_name, args):
    encoded = json.dumps([function_name, args], sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def is_pending(store, function_name, args):
    return bool(store.db.worker_tasks.find_one({"_id": task_key(function_name, args),
                                               "status": {"$in": ["queued", "running"]}}))


class DurableExecutor:
    def submit(self, function, *args):
        from preppulse_api.store import WorkspaceStore, now
        store = WorkspaceStore()
        try:
            identity = task_key(function.__name__, args)
            current = store.db.worker_tasks.find_one({"_id": identity})
            if current and current["status"] in {"queued", "running"}:
                return identity
            store.db.worker_tasks.update_one({"_id": identity}, {"$set": {
                "module": function.__module__, "function": function.__name__, "args": list(args),
                "status": "queued", "created_at": now(), "attempts": 0,
                "lease_until": datetime.now(UTC), "error": None}}, upsert=True)
            return identity
        finally:
            store.client.close()


def executor(max_workers=2, **kwargs):
    return DurableExecutor() if enabled() else ThreadPoolExecutor(max_workers=max_workers, **kwargs)


def run_worker(stop=None):
    from preppulse_api.store import WorkspaceStore
    store = WorkspaceStore()
    store.indexes()
    store.db.worker_tasks.create_index([("status", 1), ("lease_until", 1), ("created_at", 1)])
    stop = stop or threading.Event()
    owner = uuid.uuid4().hex
    allowed = {
        ("preppulse_api.app", "_job"), ("preppulse_api.app", "_chat_worker"),
        ("preppulse_api.care", "translate_signed_job"),
        ("preppulse_api.care", "translate_draft_job"),
        ("preppulse_api.care_translation", "run_language_job"),
    }
    while not stop.is_set():
        now = datetime.now(UTC)
        # An exhausted lease must become visibly retryable rather than remain
        # permanently 'running' after the last worker interruption.
        store.db.worker_tasks.update_many({"status": "running", "attempts": {"$gte": 3},
                                           "lease_until": {"$lt": now}}, {"$set": {
            "status": "failed", "error": "Worker recovery attempts exhausted; retry the action in PrepPulse",
            "finished_at": now}})
        queue = os.getenv("PREPPULSE_WORKER_QUEUE", "all")
        queue_filter = {"function": {"$in": ["_job", "_chat_worker"]}} if queue == "clinical" else {
            "function": {"$nin": ["_job", "_chat_worker"]}} if queue == "care" else {}
        task = store.db.worker_tasks.find_one_and_update({
            **queue_filter, "attempts": {"$lt": 3}, "$or": [
                {"status": "queued"}, {"status": "running", "lease_until": {"$lt": now}}]},
            {"$set": {"status": "running", "owner": owner, "lease_until": now + timedelta(minutes=3)},
             "$inc": {"attempts": 1}}, sort=[("created_at", 1)], return_document=ReturnDocument.AFTER)
        if not task:
            stop.wait(2)
            continue
        done = threading.Event()

        def heartbeat(done=done, task=task):
            while not done.wait(20):
                store.db.worker_tasks.update_one({"_id": task["_id"], "owner": owner},
                    {"$set": {"lease_until": datetime.now(UTC) + timedelta(minutes=3)}})

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        status, error = "complete", None
        try:
            if (task["module"], task["function"]) not in allowed:
                raise ValueError("Unknown worker task")
            function = getattr(importlib.import_module(task["module"]), task["function"])
            # Completed business operations are not repeated after a lost queue ACK.
            completed = False
            if task["function"] in {"_job", "_chat_worker"}:
                collection = store.db.jobs if task["function"] == "_job" else store.db.chat_turns
                field = "job_id" if task["function"] == "_job" else "turn_id"
                completed = bool(collection.find_one({field: task["args"][0], "status": "complete"}))
            if not completed:
                function(*task["args"])
        except Exception:
            logging.getLogger(__name__).exception("Worker task failed: %s", task["_id"])
            status, error = "failed", "Worker operation failed; retry the action in PrepPulse"
        finally:
            done.set()
            thread.join(timeout=2)
            store.db.worker_tasks.update_one({"_id": task["_id"], "owner": owner},
                {"$set": {"status": status, "error": error, "finished_at": datetime.now(UTC)}})
    store.client.close()


if __name__ == "__main__":
    import signal
    event = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: event.set())
    run_worker(event)

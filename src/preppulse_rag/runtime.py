"""Server-side configuration and durable, content-free API spending reservations."""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)
_ledger_initialization = threading.Lock()


class BudgetExceeded(RuntimeError):
    pass


def ledger():
    root = Path(os.getenv("PREPPULSE_PRIVATE_ROOT", str(ROOT / "private_data")))
    root.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(root / "api_usage.sqlite3", timeout=30)
    # journal-mode changes can return SQLITE_BUSY immediately during concurrent
    # first use, even with sqlite's busy timeout. Serialize threads and retry the
    # bounded initialization across the API and worker processes.
    with _ledger_initialization:
        deadline = time.monotonic() + 30
        while True:
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, created REAL, "
                                   "provider TEXT, account TEXT, service TEXT, reserved REAL, actual REAL, "
                                   "status TEXT, input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0)")
                connection.execute("CREATE TABLE IF NOT EXISTS cooldowns (account TEXT PRIMARY KEY, until REAL)")
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or time.monotonic() >= deadline:
                    connection.close()
                    raise
                time.sleep(.05)
    return connection


def reserve(provider, account, service, cost):
    """Reserve worst-case configured cost atomically before sending any request.

    Sarvam costs and configured starting balances are estimates, not a live balance API.
    An unknown balance remains unknown. Shared organisations can share a pool alias.
    """
    with ledger() as db:
        if os.getenv("PREPPULSE_AI_ENABLED", "1") != "1":
            raise BudgetExceeded("AI processing is disabled")
        db.execute("BEGIN IMMEDIATE")
        cooldown = db.execute("SELECT MAX(until) FROM cooldowns WHERE account IN (?,?)", (account, provider)).fetchone()
        if cooldown and cooldown[0] and cooldown[0] > time.time():
            raise BudgetExceeded("Account is in cooldown")
        used = db.execute("SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM calls "
                          "WHERE provider=?", (provider,)).fetchone()[0]
        if provider == "sarvam":
            if used + cost > float(os.getenv("PREPPULSE_SARVAM_BUDGET_INR", "50")):
                raise BudgetExceeded("Sarvam test spending ceiling reached")
            if account.startswith("ACC_"):
                pool = os.getenv(f"SARVAM_{account}_POOL", account)
                aliases = [f"ACC_{i}" for i in range(1, 4)
                           if os.getenv(f"SARVAM_ACC_{i}_POOL", f"ACC_{i}") == pool]
                balances = [float(os.environ[f"SARVAM_{name}_STARTING_CREDITS"])
                            for name in aliases if os.getenv(f"SARVAM_{name}_STARTING_CREDITS")]
                if balances:
                    marks = ",".join("?" for _ in aliases)
                    spent = db.execute(f"SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) "
                                       f"FROM calls WHERE account IN ({marks})", aliases).fetchone()[0]
                    if min(balances) - spent - cost < 10:
                        raise BudgetExceeded("Estimated balance would fall below 10 credits")
        elif provider == "azure":
            if used + cost > float(os.getenv("PREPPULSE_AZURE_AI_BUDGET_USD", "50")):
                raise BudgetExceeded("Azure AI spending ceiling reached")
        elif provider == "gemini":
            count = db.execute("SELECT COUNT(*) FROM calls WHERE provider='gemini'").fetchone()[0]
            if count >= int(os.getenv("PREPPULSE_GEMINI_REQUEST_LIMIT", "45")):
                raise BudgetExceeded("Gemini test request ceiling reached")
        result = db.execute("INSERT INTO calls(created,provider,account,service,reserved,status) "
                            "VALUES(?,?,?,?,?,'reserved')",
                            (time.time(), provider, account, service, cost))
        return result.lastrowid


def finish(call_id, status, actual=None, input_tokens=0, output_tokens=0):
    with ledger() as db:
        db.execute("UPDATE calls SET status=?,actual=?,input_tokens=?,output_tokens=? WHERE id=?",
                   (status, actual, input_tokens, output_tokens, call_id))


def cooldown(account, seconds):
    with ledger() as db:
        db.execute("INSERT OR REPLACE INTO cooldowns(account,until) VALUES(?,?)",
                   (account, time.time() + seconds))


def sarvam_accounts():
    if os.getenv("Main_Sarvam_AI_Credits"):
        return [("HACKATHON_MAIN", os.environ["Main_Sarvam_AI_Credits"])]
    accounts = [(f"ACC_{i}", os.getenv(f"SARVAM_AI_CREDITS_ACC_{i}", "")) for i in range(1, 4)]
    if not any(key for _, key in accounts):
        accounts = [("LEGACY", os.getenv("SARVAM_API_KEY") or os.getenv("SARVAM_AI_CREDITS", ""))]
    unique, seen = [], set()
    for alias, key in accounts:
        if key and key not in seen:
            unique.append((alias, key))
            seen.add(key)
    return unique

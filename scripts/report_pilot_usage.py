"""Content-free application estimates, not the provider wallet or Azure bill."""
import json

from preppulse_rag.runtime import ledger

if __name__ == "__main__":
    with ledger() as db:
        rows = db.execute("SELECT provider,service,COUNT(*),SUM(COALESCE(actual,reserved)),"
                          "SUM(input_tokens),SUM(output_tokens) FROM calls GROUP BY provider,service").fetchall()
    print(json.dumps({"estimated_usage": [dict(zip(
        ["provider", "service", "calls", "estimated_cost", "input_tokens", "output_tokens"], row)) for row in rows],
        "currency": {"azure": "USD", "sarvam": "INR"}, "live_wallet_balance": "unknown"}))

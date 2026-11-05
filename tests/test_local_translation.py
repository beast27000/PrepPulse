import json
import sys

import pytest

from local_translation.worker import protect, restore
from preppulse_api import local_translation


def test_protected_values_survive_many_entities_and_reject_loss():
    original = "HbA1c 8.2%, eGFR 69 mL/min/1.73m²; take 8 mg for 3 days. " + " ".join(
        str(n) for n in range(40)
    )
    masked, entities = protect(original)
    assert restore(masked, entities) == original
    with pytest.raises(ValueError, match="protected"):
        restore(masked.replace(next(iter(entities)), ""), entities)
    with pytest.raises(ValueError, match="protected"):
        restore(masked + next(iter(entities)), entities)


def test_worker_pipe_reuses_process_and_never_puts_clinical_text_on_command_line(
    tmp_path, monkeypatch
):
    command = [
        sys.executable,
        "-u",
        "-c",
        "import sys,json\nfor line in sys.stdin:\n r=json.loads(line); print(json.dumps({'translations':{x['id']:x['text'] for x in r['segments']}}),flush=True)",
    ]
    config = tmp_path / "translation.json"
    config.write_text(json.dumps({"command": command}), encoding="utf-8")
    monkeypatch.setenv("PREPPULSE_TRANSLATION_CONFIG", str(config))
    local_translation.stop_worker()
    try:
        for _ in range(2):
            assert local_translation.translate_local(
                [("item", "Private synthetic note", "en")], "en"
            ) == {"item": "Private synthetic note"}
            process = local_translation._process
            assert "Private synthetic note" not in str(process.args)
            if _ == 0:
                first_pid = process.pid
            else:
                assert process.pid == first_pid
    finally:
        local_translation.stop_worker()

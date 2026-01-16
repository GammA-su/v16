import json
import pathlib
import sys
from typing import Any


def read_bin(h: str) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = pathlib.Path(f"/workspace/v16/artifact_store/sha256/{h[:2]}/{h[2:4]}/{h}.meta.json")
    m = json.loads(meta.read_text())
    bin_path = pathlib.Path(m["path"])
    return m, json.loads(bin_path.read_text())

ucr_path = sys.argv[1]
with open(ucr_path, encoding="utf-8") as handle:
    ucr = json.load(handle)

expr = ucr["task_input"]["normalized"]["data"]["expression"]
sol_hash = next(a for a in ucr["solution_artifacts"] if a["type"] == "solution")["hash"]

m_sol, sol = read_bin(sol_hash)

print("UCR:", ucr_path)
print("expression:", expr)
print("solution_hash:", sol_hash)
print(json.dumps(sol, indent=2, sort_keys=True))

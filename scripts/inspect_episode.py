import json
import os
import pathlib
import sys


def main() -> None:
    ep = os.environ.get("EP")
    if len(sys.argv) > 1:
        ep = sys.argv[1]
    if not ep:
        raise SystemExit("Set EP=ep-... or pass episode id as argv[1].")

    d = pathlib.Path("runs") / ep
    ucr_p = d / "ucr.json"
    wit_p = d / "witness.json"

    ucr = json.loads(ucr_p.read_text())

    print("episode:", ucr["episode_id"])
    print("decision:", ucr["decision"]["action"], "-", ucr["decision"]["rationale"])
    print("lanes:", [(x["lane"], x["status"]) for x in ucr["verification"]])
    print("ucr_hash:", ucr["hashes"]["ucr_hash"])

    if wit_p.exists():
        w = json.loads(wit_p.read_text())
        print("witness.final_response:", w.get("final_response"))
    else:
        print("witness.json: MISSING (this is fine for portable replay)")

if __name__ == "__main__":
    main()

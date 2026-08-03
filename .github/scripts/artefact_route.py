#!/usr/bin/env python3
"""The artefact route (V2_FULL_PLAN.md §5.1.1, F45), run with no network at all.

`tests/test_dependency_boundary.py` proves the same route by *uninstalling httpx* — no
HTTP client is reachable, so no request can be made. This proves it the other way: the
client is installed and working, and the network itself is gone. CI runs this under
`unshare --map-root-user --net`, which puts the process in an empty network namespace
where a socket call fails rather than resolving.

Both are worth having. The first says our code does not import a transport; the second
says it does not need one. A client asking "what does this thing talk to while it runs"
is asking the second question, and the answer should be a build step rather than a
paragraph.

Exits non-zero on any failure, so the workflow step fails.
"""

import json
import socket
import sys
import tempfile
from pathlib import Path

from legal_rag_audit.interchange import (
    CaptureNotes,
    Response,
    write_ground_truth,
    write_handover,
    write_probes,
    write_responses,
)
from legal_rag_audit.plants import plant, write_corpus
from legal_rag_audit.probes import build_ground_truth, build_probes
from legal_rag_audit.provenance import build_handover
from legal_rag_audit.score import score


def assert_the_network_is_actually_gone() -> None:
    """Fail loudly if this is running with a network after all.

    Without this the step could pass on a runner where `unshare` silently did nothing,
    and a green tick would be reporting a guarantee that was never tested.

    `--allow-network` exists so the route can be exercised on a laptop, where there is
    no namespace to drop into. It is a development convenience and nothing else:
    tests/test_supply_chain.py asserts the CI step does not pass it, because a flag that
    disables the only thing a step proves is worth exactly one line of enforcement.
    """
    if "--allow-network" in sys.argv:
        print("network assertion skipped (--allow-network): this run proves nothing "
              "about egress, only that the four steps work.\n")
        return

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(5)
    try:
        probe.connect(("1.1.1.1", 443))
    except OSError:
        return
    finally:
        probe.close()
    raise SystemExit(
        "this process reached the network, so the run proves nothing. The step must "
        "execute inside an empty network namespace — see .github/workflows/ci.yml"
    )


def main() -> int:
    assert_the_network_is_actually_gone()

    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory)

        # 1. plant — mint the corpus and the answer key.
        corpus = plant("ci-artefact-route")
        write_corpus(out / "corpus", corpus)
        probes = build_probes(corpus=corpus)
        write_probes(out / "probes.jsonl", probes)
        write_ground_truth(out / "ground_truth.json", build_ground_truth(corpus))

        # 2. hash — seal all three before any answer exists.
        write_handover(
            out / "handover.json",
            build_handover(
                corpus=str(out / "corpus"),
                probes=str(out / "probes.jsonl"),
                ground_truth=str(out / "ground_truth.json"),
            ),
        )

        # 3. their harness. Stands in for anything that emits the published format —
        #    thirty lines of curl, or a client's own test rig.
        write_responses(
            out / "responses.jsonl",
            [
                Response(
                    run_id="artefact-route",
                    probe_id=probe.probe_id,
                    query=probe.text,
                    tenant=probe.tenant,
                    answer="Their harness produced this answer.",
                )
                for probe in probes
            ],
            capture_notes=CaptureNotes(
                record="capture_notes",
                citations_captured=False,
                retrieved_chunks_captured=False,
            ),
        )

        # 4. score — and the pre-commitment still has to verify.
        report = score(
            str(out / "responses.jsonl"),
            str(out / "ground_truth.json"),
            str(out / "probes.jsonl"),
            skip_tier2=True,
            handover_path=str(out / "handover.json"),
            output_dir=str(out / "report"),
        )

        summary = {
            "checks": report["summary"]["checks_registered"],
            "pre_commitment": report["manifest"]["pre_commitment"]["status"],
            "verbatim": report["manifest"]["capture"]["probes_asked_verbatim"],
        }
        print(json.dumps(summary, indent=2))

        if summary["pre_commitment"] != "verified":
            print("FAIL: the pre-commitment did not verify", file=sys.stderr)
            return 1
        if summary["verbatim"] != len(probes):
            print(
                f"FAIL: {summary['verbatim']} of {len(probes)} probes were put "
                f"verbatim",
                file=sys.stderr,
            )
            return 1
        if not (out / "report" / "report.md").exists():
            print("FAIL: no report was written", file=sys.stderr)
            return 1

    if "--allow-network" in sys.argv:
        print("\nplant → hash → score completed. Egress was not constrained.")
    else:
        print("\nplant → hash → score completed with no network reachable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

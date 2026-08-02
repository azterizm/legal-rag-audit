"""What a scoring run leaves on disk (§7).

    out/
      report.json        the evidence — a published contract, `report.v2`
      report.md          the testimony — §10.6, ordered deal-enders first
      manifest.json      provenance, also embedded in report.json
      ground_truth.json  the sealed half, disclosed (F44)
      evidence/          verbatim excerpts per Tier 1 finding (F41)

The ground truth is the one that matters most. §3.6 promises the withheld half of the
battery arrives in full with the findings, and a promise in a document is kept by
whoever remembers to keep it. Written by the tool, it is kept by construction.

That copy is byte-for-byte, not re-serialised from the parsed model. It has to be: the
client verifies it against `ground_truth_manifest_hash` in the manifest, and a
re-serialisation that reorders a key or changes indentation produces a different
digest and an accusation of tampering over a formatting difference.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Optional

from ..interchange import Probe
from . import attestation
from .evidence import write_bundle as write_evidence

logger = logging.getLogger(__name__)

REPORT = "report.json"
ATTESTATION = "report.md"
MANIFEST = "manifest.json"
GROUND_TRUTH = "ground_truth.json"
EVIDENCE = "evidence"


def _write_json(path: Path, document: Any) -> None:
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def write_bundle(
    output_dir: str | Path,
    report: dict[str, Any],
    ground_truth_path: str | Path,
    evidence: Optional[dict[str, list[dict[str, Any]]]] = None,
    probes: Optional[list[Probe]] = None,
    target_name: str = "the target system",
) -> dict[str, Path]:
    """Write everything a scoring run produces.

    The manifest is written twice on purpose — inside `report.json` and beside it —
    because the two get used by different people. The report is read; `manifest.json`
    gets diffed against the next run's.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    written = {
        "report": out / REPORT,
        "attestation": out / ATTESTATION,
        "manifest": out / MANIFEST,
        "ground_truth": out / GROUND_TRUTH,
    }

    _write_json(written["report"], report)
    _write_json(written["manifest"], report["manifest"])
    written["attestation"].write_text(
        attestation.render(report, probes or [], target_name), encoding="utf-8"
    )

    if evidence:
        write_evidence(out / EVIDENCE, evidence)

    source = Path(ground_truth_path)
    destination = written["ground_truth"]
    if not (destination.exists() and source.samefile(destination)):
        shutil.copyfile(source, destination)

    logger.info(
        f"Report written to {written['report']}, attestation to "
        f"{written['attestation']}. The ground-truth manifest is disclosed in full "
        f"at {destination} and hashes to "
        f"{report['manifest']['inputs']['ground_truth_manifest_hash']}."
    )
    return written

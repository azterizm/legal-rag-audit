"""What a scoring run leaves on disk.

Three files, and the third one is the point. F44: **every run writes the ground-truth
manifest next to the report.** §3.6 promises that the withheld half of the battery is
handed over in full with the findings, and a promise in a document is kept by whoever
remembers to keep it. Written by the tool, it is kept by construction.

The copy is byte-for-byte, not re-serialised from the parsed model. It has to be: the
client verifies it against `ground_truth_manifest_hash` in the manifest, and a
re-serialisation that reorders a key or changes indentation produces a different
digest and an accusation of tampering over a formatting difference.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPORT = "report.json"
MANIFEST = "manifest.json"
GROUND_TRUTH = "ground_truth.json"


def _write_json(path: Path, document: Any) -> None:
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def write_bundle(
    output_dir: str | Path, report: dict[str, Any], ground_truth_path: str | Path
) -> dict[str, Path]:
    """Write the report, the manifest, and the disclosed ground truth.

    The manifest is written twice on purpose — inside `report.json` and beside it —
    because the two get used by different people. The report is read; `manifest.json`
    gets diffed against the next run's.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    written = {
        "report": out / REPORT,
        "manifest": out / MANIFEST,
        "ground_truth": out / GROUND_TRUTH,
    }

    _write_json(written["report"], report)
    _write_json(written["manifest"], report["manifest"])

    source = Path(ground_truth_path)
    destination = written["ground_truth"]
    if not (destination.exists() and source.samefile(destination)):
        shutil.copyfile(source, destination)

    logger.info(
        f"Report written to {written['report']}. The ground-truth manifest is "
        f"disclosed in full at {destination} and hashes to "
        f"{report['manifest']['inputs']['ground_truth_manifest_hash']}."
    )
    return written

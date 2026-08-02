"""Provenance: what a report has to carry to survive being handed to a third party.

Two records, one purpose. The **handover** (§3.6, F38) fixes the answer key before any
response exists. The **run manifest** (§6.5, F23) says which build scored which exact
bytes, with which models at which lines. Between them they answer the two questions a
report cannot survive without: *could you have decided afterwards what counted as a
failure?* and *can I reproduce this?*

Nothing here opens a socket, and nothing here imports the transport layer — the whole
package sits inside `score`'s offline enforcement (§5.1, F18).
"""

from .emit import (
    PreCommitmentError,
    build_handover,
    build_run_manifest,
    verify_pre_commitment,
)
from .hashes import (
    ALGORITHM,
    FILE_RECIPE,
    JSON_RECIPE,
    TREE_RECIPE,
    HashError,
    TreeHash,
    digest_bytes,
    hash_file,
    hash_json,
    hash_path,
    hash_tree,
    recipe_for,
)
from .tool import tool_commit, tool_provenance, tool_version

__all__ = [
    "ALGORITHM",
    "FILE_RECIPE",
    "JSON_RECIPE",
    "TREE_RECIPE",
    "HashError",
    "PreCommitmentError",
    "TreeHash",
    "build_handover",
    "build_run_manifest",
    "digest_bytes",
    "hash_file",
    "hash_json",
    "hash_path",
    "hash_tree",
    "recipe_for",
    "tool_commit",
    "tool_provenance",
    "tool_version",
    "verify_pre_commitment",
]

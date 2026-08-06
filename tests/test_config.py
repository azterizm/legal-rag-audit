"""The config refuses what it cannot honour (§6.1).

Two properties, and the second is the reason this file exists.

*Unknown keys abort.* Pydantic's default is to ignore them, which means a config can ask
for something the run does not do and nobody finds out. The tool's whole subject is
systems whose stated behaviour and actual behaviour differ; the config loader is not
exempt from that just because it is ours.

*The two settings that moved are named.* `corpus.use_bundled` and `tests:` were real
settings once. "Extra inputs are not permitted" is true and useless — an operator holding
a config that worked last year needs to be told where the setting went (NF9).
"""

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from legal_rag_audit.config import AuditConfig

MINIMAL = {
    "target": {
        "name": "example",
        "endpoints": {"chat": "https://example.invalid/chat"},
    }
}


def load(document: dict, tmp_path: Path) -> AuditConfig:
    import yaml

    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return AuditConfig.load_from_yaml(str(path))


def test_the_minimal_config_loads(tmp_path: Path) -> None:
    config = load(MINIMAL, tmp_path)
    assert config.target.name == "example"
    assert config.corpus.mode == "planted"


@pytest.mark.parametrize(
    "path,document",
    [
        ("top level", {**MINIMAL, "tresholds": {}}),
        ("target", {"target": {**MINIMAL["target"], "nmae": "typo"}}),
        (
            "endpoints",
            {"target": {**MINIMAL["target"], "endpoints": {"chat": "u", "chatt": "u"}}},
        ),
        ("corpus", {**MINIMAL, "corpus": {"mode": "planted", "pathh": "./x"}}),
        ("battery", {**MINIMAL, "battery": {"passes": 1, "pases": 3}}),
        ("thresholds", {**MINIMAL, "thresholds": {"max_halucination_rate": 0.02}}),
        (
            "response_format",
            {"target": {**MINIMAL["target"], "response_format": {"anwser_field": "$.a"}}},
        ),
        ("auth", {"target": {**MINIMAL["target"], "auth": {"type": "none", "tokn": "X"}}}),
    ],
)
def test_an_unknown_key_aborts_wherever_it_appears(
    path: str, document: dict, tmp_path: Path
) -> None:
    """Every level, not just the top one.

    A typo in `thresholds` is the dangerous case rather than the harmless one: the run
    completes, the report prints a pass, and the threshold the operator thought they had
    set was never read. Parametrised over each nested model so a new model added without
    `extra="forbid"` fails here rather than in a report six months later.
    """
    with pytest.raises(ValidationError) as excinfo:
        load(document, tmp_path)
    assert "Extra inputs are not permitted" in str(excinfo.value), path


def test_the_dead_tests_block_names_what_replaced_it(tmp_path: Path) -> None:
    with pytest.raises(ValidationError) as excinfo:
        load({**MINIMAL, "tests": {"injection_resistance": True}}, tmp_path)

    message = str(excinfo.value)
    assert "no longer a setting" in message
    assert "eligible_for" in message
    # The instruction has to be runnable. A diagnosis that names a flag the CLI does not
    # have is worse than no diagnosis, because it costs the reader a round trip to find
    # out it was wrong.
    assert "plant --list-corpora" in message


def test_the_moved_corpus_setting_is_still_named(tmp_path: Path) -> None:
    """`extra="forbid"` must not have swallowed the older diagnosis.

    Both validators run `mode="before"`, and a plain extra-key rejection would be the
    lower-quality error winning by ordering.
    """
    with pytest.raises(ValidationError) as excinfo:
        load({**MINIMAL, "corpus": {"use_bundled": True}}, tmp_path)

    message = str(excinfo.value)
    assert "no longer a setting" in message
    assert "mode: planted" in message


def test_no_shipped_config_carries_a_credential() -> None:
    """The example is what people copy. It must not model putting a key in the file.

    `token_env` exists precisely so the one value that grants access to somebody's index
    lives in the environment. An example header with a real-looking key teaches the
    opposite, and configs get pasted into issues.
    """
    root = Path(__file__).resolve().parents[1]
    example = (root / "config.yaml.example").read_text(encoding="utf-8")

    assert "token_env" in example
    for marker in ("x-api-key:", "api_key:", "secret", "sk-", "zut_"):
        for line in example.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or marker not in stripped:
                continue
            # A header naming the env var is fine; one carrying a value is not.
            assert "token_env" in stripped or stripped.endswith(
                ('"..."', "'...'", ":")
            ), f"{marker!r} appears with a value: {line!r}"


def test_the_example_has_no_tests_block() -> None:
    """The file people copy must not carry the block the loader now rejects."""
    root = Path(__file__).resolve().parents[1]
    example = (root / "config.yaml.example").read_text(encoding="utf-8")
    for line in example.splitlines():
        assert not line.startswith("tests:"), "config.yaml.example still has tests:"


class TestMissingCredential:
    """An unset token aborts before anything is sent (NF9, F40)."""

    def _client(self, monkeypatch):
        from legal_rag_audit.config import TargetConfig
        from legal_rag_audit.transport.client import TargetClient

        monkeypatch.delenv("A_TOKEN_THAT_IS_NOT_SET", raising=False)
        return TargetClient(
            TargetConfig(
                **{
                    **MINIMAL["target"],
                    "auth": {"type": "api_key", "token_env": "A_TOKEN_THAT_IS_NOT_SET"},
                }
            )
        )

    def test_it_raises_rather_than_substituting_a_placeholder(self, monkeypatch) -> None:
        """The old behaviour warned and sent "DUMMY_TOKEN".

        Every request would then be rejected, and rejections are recorded as responses —
        so an unset environment variable arrived in the report as a target that answered
        wrongly. An absent measurement and a failed one must never print the same, and
        this one printed worse.
        """
        from legal_rag_audit.transport.client import AuthTokenMissing

        with pytest.raises(AuthTokenMissing) as excinfo:
            self._client(monkeypatch)

        message = str(excinfo.value)
        assert "A_TOKEN_THAT_IS_NOT_SET" in message
        assert "not a finding" in message
        assert "Nothing was sent" in message

    def test_a_configured_token_is_used(self, monkeypatch) -> None:
        from legal_rag_audit.config import TargetConfig
        from legal_rag_audit.transport.client import TargetClient

        monkeypatch.setenv("A_TOKEN_THAT_IS_NOT_SET", "k")
        client = TargetClient(
            TargetConfig(
                **{
                    **MINIMAL["target"],
                    "auth": {"type": "api_key", "token_env": "A_TOKEN_THAT_IS_NOT_SET"},
                }
            )
        )
        assert client.headers["x-api-key"] == "k"

    def test_auth_none_needs_no_environment(self, monkeypatch) -> None:
        """A target that takes no credential must not be made to invent one."""
        from legal_rag_audit.config import TargetConfig
        from legal_rag_audit.transport.client import TargetClient

        monkeypatch.delenv("A_TOKEN_THAT_IS_NOT_SET", raising=False)
        client = TargetClient(
            TargetConfig(
                **{
                    **MINIMAL["target"],
                    "auth": {"type": "none", "token_env": "A_TOKEN_THAT_IS_NOT_SET"},
                }
            )
        )
        assert client.headers == {}


def test_the_docstring_example_in_the_error_is_valid_yaml(tmp_path: Path) -> None:
    """The `use_bundled` diagnosis prints a config fragment. It has to parse.

    A worked example in an error message is a promise that the thing shown will load.
    """
    import yaml

    from legal_rag_audit.config import CorpusConfig

    with pytest.raises(ValidationError) as excinfo:
        load({**MINIMAL, "corpus": {"use_bundled": True}}, tmp_path)

    # Indentation is kept and only the common prefix removed: the fragment is a nested
    # block, and flattening it would test a different document from the one printed.
    fragment = textwrap.dedent(
        "\n".join(
            line
            for line in str(excinfo.value).splitlines()
            if line.strip().startswith(("corpus:", "mode:", "seed:", "path:"))
        )
    )
    CorpusConfig(**yaml.safe_load(fragment)["corpus"])

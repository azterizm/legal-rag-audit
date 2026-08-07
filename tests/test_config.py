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


class TestTheTargetIsAnonymousUnlessTold:
    """`target.name` is local. Artefacts carry `target.pseudonym`, or nothing.

    §16.3: a wrong finding against a named company is unrecoverable. Forgetting to name a
    target costs an email. The default has to sit on the recoverable side.
    """

    def test_a_config_that_says_nothing_produces_an_anonymous_note(self) -> None:
        from legal_rag_audit.config import TargetConfig

        assert TargetConfig(**MINIMAL["target"]).pseudonym is None

    def test_the_capture_note_never_carries_the_local_name(self, tmp_path: Path) -> None:
        """The note lives in `responses.jsonl`, which is the file that gets handed over.

        `report.md` was already anonymous — `attestation.render` defaults to "the target
        system" and no caller passes anything else. The name leaked through the artefact
        route instead, which is the route designed to leave the building.
        """
        import asyncio

        from legal_rag_audit.generate.run import Generator

        config = load({**MINIMAL, "corpus": {"mode": "existing"}}, tmp_path)
        config.target.name = "a-vendor-that-must-not-appear"

        generator = Generator(config=config, documents=[], passes=1)
        _responses, notes = asyncio.run(generator.run([]))

        assert "a-vendor-that-must-not-appear" not in notes.notes
        assert notes.notes == "Produced by legal-rag-audit generate."

    def test_a_pseudonym_is_what_travels(self, tmp_path: Path) -> None:
        import asyncio

        from legal_rag_audit.generate.run import Generator

        config = load({**MINIMAL, "corpus": {"mode": "existing"}}, tmp_path)
        config.target.name = "a-vendor-that-must-not-appear"
        config.target.pseudonym = "product-a"

        _responses, notes = asyncio.run(Generator(config=config, documents=[], passes=1).run([]))

        assert "a-vendor-that-must-not-appear" not in notes.notes
        assert "product-a" in notes.notes


class TestTheAuthScheme:
    """Every accepted scheme attaches a header, and nothing else is accepted.

    `type` was a free string matched against four values in an if/elif chain with no
    else. A scheme the chain did not know fell off the end: the token was read from the
    environment, no header was attached, and the probes went out unauthenticated. The
    target answers 401 to all of them, `generate` records the 401s as responses, and a
    system that never spoke to us is scored as one that answered badly — F40, from a
    typo, in a report naming a company.
    """

    def _headers(self, monkeypatch, scheme: str) -> dict:
        from legal_rag_audit.config import TargetConfig
        from legal_rag_audit.transport.client import TargetClient

        monkeypatch.setenv("A_CREDENTIAL", "s3cret")
        client = TargetClient(
            TargetConfig(
                **{
                    **MINIMAL["target"],
                    "auth": {"type": scheme, "token_env": "A_CREDENTIAL"},
                }
            )
        )
        return client.headers

    @pytest.mark.parametrize(
        "scheme,header",
        [
            ("bearer", "Authorization"),
            ("api_key", "x-api-key"),
            ("basic", "Authorization"),
            ("cookie", "Cookie"),
        ],
    )
    def test_each_scheme_puts_the_credential_somewhere(
        self, monkeypatch, scheme: str, header: str
    ) -> None:
        headers = self._headers(monkeypatch, scheme)
        assert "s3cret" in headers[header], headers

    def test_an_unrecognised_scheme_is_refused_at_load(self) -> None:
        """Not at request time, and not silently. `Literal` is what holds this."""
        from legal_rag_audit.config import TargetConfig

        with pytest.raises(ValidationError):
            TargetConfig(
                **{**MINIMAL["target"], "auth": {"type": "cookies", "token_env": "X"}}
            )

    def test_a_scheme_with_nowhere_to_read_the_credential_from_is_refused(self) -> None:
        """The same failure by the other route: a scheme set and no `token_env`.

        `_build_auth_headers` skipped the whole block on a falsy `token_env`, so this
        also sent the battery out unauthenticated.
        """
        from legal_rag_audit.config import TargetConfig

        with pytest.raises(ValidationError) as excinfo:
            TargetConfig(**{**MINIMAL["target"], "auth": {"type": "bearer"}})

        assert "token_env" in str(excinfo.value)

    def test_the_cookie_header_is_passed_through_whole(self, monkeypatch) -> None:
        """A session product usually needs several cookies, and they arrive as one string.

        Splitting them across config keys would put half a credential in a file that gets
        committed; the whole header lives in the environment or nowhere.
        """
        from legal_rag_audit.config import TargetConfig
        from legal_rag_audit.transport.client import TargetClient

        monkeypatch.setenv("A_CREDENTIAL", "auth_token=abc; auth_check=1")
        client = TargetClient(
            TargetConfig(
                **{
                    **MINIMAL["target"],
                    "auth": {"type": "cookie", "token_env": "A_CREDENTIAL"},
                }
            )
        )
        assert client.headers["Cookie"] == "auth_token=abc; auth_check=1"


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


class TestATwoHundredWithNoTextIsNotAnAnswer:
    """A parse failure and a silent target are the same observation from here.

    The dangerous half is ours. An `answer_field` that does not match the target's shape
    produces an empty string per probe, an empty string matches no invariant, and the
    whole battery reads as a system that declined to answer — twelve findings-shaped
    results about a named company, every one of them a statement about our JSONPath. So
    an empty answer is recorded with `error` set, which makes the record unusable: every
    check reads it as NOT_CAPTURED and none as a finding (F40).
    """

    def _ask(self, tmp_path: Path, answer: str):
        import asyncio

        from legal_rag_audit.generate.run import Generator
        from legal_rag_audit.interchange import Probe

        config = load({**MINIMAL, "corpus": {"mode": "existing"}}, tmp_path)
        generator = Generator(config=config, documents=[], passes=1)

        async def chat(_query):
            return {"answer": answer, "citations": None, "raw": {"seen": True}}

        generator.client.chat = chat
        probe = Probe(
            probe_id="p1",
            family="point_in_time",
            intent="positive",
            text="what was the cap?",
            eligible_for=["point_in_time"],
        )
        return asyncio.run(generator._ask(probe, 1))

    def test_an_answer_that_arrived_is_recorded_as_one(self, tmp_path: Path) -> None:
        response = self._ask(tmp_path, "The cap was £68,400.")
        assert response.error is None
        assert response.usable is True

    @pytest.mark.parametrize("empty", ["", "   \n  "], ids=["empty", "whitespace"])
    def test_a_body_with_no_text_is_recorded_as_a_failure(
        self, tmp_path: Path, empty: str
    ) -> None:
        response = self._ask(tmp_path, empty)
        assert response.usable is False
        assert response.error.startswith("EmptyAnswer:")
        # The status is kept: it was a 200, and a reader diagnosing this needs to know
        # the request succeeded and the parse did not.
        assert response.http_status == 200

    def test_the_frames_are_kept_so_the_parse_can_be_diagnosed(
        self, tmp_path: Path
    ) -> None:
        """The one thing that makes the failure recoverable. Without the raw body there
        is no way to work out which path would have matched, and the run has to be
        fired at the target a second time to find out."""
        response = self._ask(tmp_path, "")
        assert response.raw_response == {"seen": True}

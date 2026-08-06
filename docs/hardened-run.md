# Running the container without trusting it

The fear behind *"we can't run an unverified tool against our system"* is correct, and
the usual reassurance — *"turn off the internet while it runs"* — does not answer it. A
delayed or queued payload still has to make a call eventually, and disabling egress for
ten minutes only moves when it fires.

So do not disable egress. **Deny** it. Under denial the timing stops mattering, because
there is no moment at which the call succeeds.

Everything below has been run. Where a control cannot be expressed in Docker, this page
says so and names what does express it, rather than printing a flag that looks like it
works.

---

## The three invocations

Two images are published (§5.3). `legal-rag-audit-generate` carries five pure-Python
dependencies and is the one to run against a target. `legal-rag-audit-score` adds the ML
stack and never talks to anything.

Run the digest, not the tag. `IMAGES` in each release lists both, and
`scripts/verify_release.sh <tag>` checks their signatures and provenance before you pull
anything.

### 1. `generate` — the only one that talks to your system

```bash
docker run --rm \
  --network=audit-net \
  --read-only --cap-drop=ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -v "$PWD/in:/in:ro" -v "$PWD/out:/out" \
  ghcr.io/azterizm/legal-audit-rag-generate@sha256:… \
  generate -c /in/config.yaml -o /out/responses.jsonl
```

`audit-net` is yours, not ours — see [Egress](#egress-the-part-docker-can-enforce-and-the-part-it-cannot).

### 2. `score` — no network at all

```bash
docker run --rm \
  --network=none \
  --read-only --cap-drop=ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -v "$PWD/out:/out" -v "$PWD/models:/models:ro" \
  ghcr.io/azterizm/legal-audit-rag-score@sha256:… \
  score --responses /out/responses.jsonl --ground-truth /out/ground_truth.json \
        --probes /out/probes.jsonl -o /out/report
```

`--network=none` is absolute: the container has no interface but loopback. The code
already refuses to open a socket during scoring and asserts it at start-up (§5.1, F18),
but that is our code checking our code. This is the kernel checking it.

### 3. The whole thing, with nothing to talk to

`plant`, `hash` and Tier 1 `score` all run inside the **generate** image with no network
and no model. That is §5.1.1's artefact route: we mint the corpus and the answer key,
you run your own harness against your own system, and we score the file you send back.

```bash
docker run --rm --network=none \
  --read-only --cap-drop=ALL --security-opt no-new-privileges \
  --user "$(id -u):$(id -g)" \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -v "$PWD/out:/out" \
  ghcr.io/azterizm/legal-audit-rag-generate@sha256:… \
  plant -o /out/planted
```

Only the two model-backed checks need the score image. Everything a client is most
suspicious of — the corpus, the seed, the answer key, the Tier 1 verdicts — happens in
the small image with the network removed.

---

## What each flag is doing

| Flag | What it answers |
|---|---|
| `--network=none` / an internal network | The call fails whenever it fires. Timing is irrelevant under denial |
| `--read-only` | Nothing persists in the container. There is nowhere for "queued" to live |
| `--cap-drop=ALL` | No `CAP_NET_RAW`, no `CAP_SYS_ADMIN`, nothing to escalate with |
| `--security-opt no-new-privileges` | A setuid binary inside the image cannot raise privilege |
| `--user "$(id -u):$(id -g)"` | Non-root, and output lands owned by you rather than by uid 65532 |
| `--rm` | No daemon, no persistent state. It exits when done |
| `-v …/in:ro` | One read-only input mount. The config is the only thing it reads |
| `--tmpfs /tmp` | The one writable path, in RAM, discarded on exit, `noexec` |

The images already run as a non-root user (uid 65532) with no login shell, so an
invocation that forgets `--user` is still not root. `--user` is there so the report and
the response file arrive owned by the person who ran the command — without it, on Linux,
they land owned by 65532 and the next step is `sudo chown`, or worse, `chmod 777` on the
output directory. A hardened invocation that makes people loosen permissions elsewhere
has moved the problem rather than solved it.

**There is no `VOLUME` declared for `/out`.** If you forget the `-v`, the run aborts
against the read-only filesystem and names the path. Declaring the volume would make
Docker create an anonymous one instead: the run would succeed, write the report into a
directory that vanishes with the container, and report nothing wrong.

---

## Egress: the part Docker can enforce, and the part it cannot

An earlier draft of this page printed `--network=host-allowlist-only`. There is no such
Docker network. It was standing in for *a network you have configured to permit exactly
one destination*, and the substitution is worth making explicit, because a reader who
pasted it would have got an error and concluded the rest was decorative too.

**Docker cannot express a per-container host allowlist.** It has no such flag. What it
can express — and does, at the network layer — is *no external route at all*:

```bash
docker network create --internal audit-net
```

A container on an `--internal` network can reach other containers on that network and
nothing else. Verified both directions: a socket to `1.1.1.1:443` from a container on
`audit-net` returns `Network is unreachable`, and the same container on the default
bridge connects.

That is the whole recipe. Put a forward proxy on `audit-net` *and* on a network that can
reach your RAG endpoint, allowlist the one host, and the audit container's only route to
anything is through a proxy you configured:

```bash
docker network create --internal audit-net
docker network create audit-egress

# your proxy, your allowlist, your log
docker run -d --name audit-proxy --network=audit-net your-proxy:pinned
docker network connect audit-egress audit-proxy

docker run --rm --network=audit-net \
  -e HTTPS_PROXY=http://audit-proxy:3128 -e HTTP_PROXY=http://audit-proxy:3128 \
  … as above …
```

The connection log is then **yours**, not a claim of ours — which is the point. A log we
produced saying we only talked to your endpoint is worth about as much as a paragraph
saying the same thing.

The allowlist itself is enforced by your proxy and your network policy, on your
infrastructure, with your tooling. We do not ship a proxy and would not want to: a
container that carried its own egress control would be asking you to trust the control
and the thing being controlled to the same degree.

---

## Model weights for the score image

The score image ships **without** model weights, and with `HF_HUB_OFFLINE=1` set, so a
missing checkpoint fails at load rather than being fetched. Scoring that claimed to run
offline while quietly reaching a model hub on a cache miss would be the one place the
claim failed and nobody looked.

Populate a cache once, then mount it read-only:

```bash
mkdir -p models
docker run --rm -e HF_HUB_OFFLINE=0 -v "$PWD/models:/models" \
  --entrypoint python ghcr.io/azterizm/legal-audit-rag-score@sha256:… -c \
  "from sentence_transformers import CrossEncoder, SentenceTransformer; \
   SentenceTransformer('all-MiniLM-L6-v2'); \
   CrossEncoder('cross-encoder/nli-deberta-v3-base')"
```

That run reaches the Hugging Face hub, on purpose, once. Every run after it uses
`--network=none`.

`docker build -f Dockerfile.score --build-arg BAKE_MODELS=1 .` puts the weights in the
image instead. It is not the default and it is not what the published image does: the
two checkpoints are resolved by *name*, with no revision pinned, so baking them makes
the image a pin over bytes nobody reviewed. That is a recorded gap, not a solved
problem — see the manifest's model section.

---

## Building it yourself

Nothing here requires our registry.

```bash
docker build -f Dockerfile.generate -t legal-rag-audit-generate .
```

Both Dockerfiles pin their base image by digest and install every dependency from a
hash-pinned lockfile under `--require-hashes`, so a build on your machine and a build on
ours resolve the same bytes. The published images are `linux/amd64`; the command above
is what produces an `arm64` one, and it is how the images in this document were checked.

---

## What this does not establish

These controls answer *what can this thing reach* and *what can it leave behind*. They
answer nothing about whether the findings in the report are correct. That is what
`docs/harness-verification.md`, the sensitivity and specificity gates, and the report's
own limits section are for — and none of them is a container flag.

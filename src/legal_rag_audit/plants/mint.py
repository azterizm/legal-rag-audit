"""Seeded plant generation (V2_FULL_PLAN.md §3.2).

The rule the whole of Tier 1 rests on: **never enumerate what the target might say;
check for a token we authored.** A maintained list of leak phrases or injection payloads
rots, and worse, it can be defended against by name. A token minted from a seed nobody
else holds cannot be pre-empted, and a key disclosed after run *n* is worthless for run
*n+1* — regeneration, not secrecy, is what makes a repeat engagement mean anything.

Every value here is a pure function of `(kind, seed, plant_id, attempt)`:

    HMAC-SHA256(seed, "<plant_id>#<attempt>")

read as a byte stream and formatted per kind. Same four inputs, same string, forever, on
any machine — which is what lets a third party holding the seed regenerate the identical
battery and check that the corpus we planted is the corpus we said we planted. `attempt`
exists because the collision guard (`guard.py`) rejects values, and §3.2 says a rejected
plant regenerates from `plant_id + n` rather than being nudged into shape by hand.

Five kinds, chosen because each survives paraphrase. A system that rewrites a leaked
clause in its own words still emits the counterparty name or the figure, because those
*are* the payload:

| Kind | Shape | Why it survives rewording |
|---|---|---|
| `entity` | `Zathrex Holdings SARL` | A proper noun cannot be paraphrased and stay useful |
| `figure` | `£4,471,203.17` | Precision survives rewording; improbable by chance |
| `date` | `14 March 2019` | Same |
| `citation` | `Quillworth v Marrentine [2019] EWHC 4471 (Ch)` | Same, and doubles as a phantom-authority lure |
| `token` | `ZX9-ACK-7f3a9c2e` | Opaque: for injection side effects and canaries |

Coined words are built from consonant clusters chosen to be improbable in English rather
than merely unusual, so a minted company name is not somebody's actual surname. That is a
bias, not a guarantee — `guard.py` is where the guarantee is attempted, and where the
part we cannot check is written down instead of glossed over.
"""

import hmac
from dataclasses import dataclass
from hashlib import sha256
from typing import Final

ENTITY: Final = "entity"
LABEL: Final = "label"
FIGURE: Final = "figure"
DATE: Final = "date"
CITATION: Final = "citation"
TOKEN: Final = "token"

KINDS: Final[tuple[str, ...]] = (ENTITY, LABEL, FIGURE, DATE, CITATION, TOKEN)


class PlantError(Exception):
    """A plant could not be minted. A setup problem, not a finding (NF9)."""


#: Published with the ground-truth manifest so a holder of the seed can regenerate the
#: battery without reading this file. Kept as prose rather than a code reference for the
#: same reason `hashes.py` publishes its recipes: the person checking us may not be
#: running our code, and *may deliberately not be*.
RECIPE: Final = (
    "Each plant value is derived from HMAC-SHA256 with the run seed as the key and "
    "'<plant_id>#<attempt>' (UTF-8) as the message. The 32-byte digest is read as a "
    "stream of unsigned 32-bit big-endian integers; when it is exhausted the stream "
    "continues with HMAC-SHA256(seed, '<plant_id>#<attempt>/<block>') for block = 1, 2, "
    "3 ... A choice among n alternatives consumes one integer and, to keep the "
    "distribution uniform, rejects and redraws any integer at or above "
    "floor(2**32 / n) * n. `attempt` starts at 0 and increments only when the collision "
    "guard rejects the value; the ground-truth manifest records the accepted attempt "
    "for every plant, so regeneration needs no search."
)


# --------------------------------------------------------------------------------
# The byte stream
# --------------------------------------------------------------------------------


class _Stream:
    """Uniform integers from an HMAC digest, extended in blocks when exhausted.

    Rejection-sampled rather than reduced modulo n. Modulo bias over a 32-bit draw is
    tiny, but "tiny" is a claim somebody would have to evaluate, and an unbiased draw is
    five lines. The published recipe above describes exactly this, so a third party
    reimplementing it in another language lands on the same values.
    """

    __slots__ = ("_key", "_label", "_buffer", "_block")

    def __init__(self, seed: str, plant_id: str, attempt: int) -> None:
        self._key = seed.encode("utf-8")
        self._label = f"{plant_id}#{attempt}"
        self._buffer = self._digest(self._label)
        self._block = 0

    def _digest(self, message: str) -> bytes:
        return hmac.new(self._key, message.encode("utf-8"), sha256).digest()

    def _refill(self) -> None:
        self._block += 1
        self._buffer += self._digest(f"{self._label}/{self._block}")

    def _word(self) -> int:
        while len(self._buffer) < 4:
            self._refill()
        head, self._buffer = self._buffer[:4], self._buffer[4:]
        return int.from_bytes(head, "big")

    def below(self, n: int) -> int:
        """A uniform integer in [0, n)."""
        if n <= 0:
            raise PlantError(f"cannot draw from an empty range (n={n})")
        limit = (2**32 // n) * n
        while True:
            value = self._word()
            if value < limit:
                return value % n

    def pick(self, options: tuple[str, ...]) -> str:
        return options[self.below(len(options))]

    def digits(self, count: int) -> str:
        return "".join(str(self.below(10)) for _ in range(count))

    def hex(self, count: int) -> str:
        return "".join("0123456789abcdef"[self.below(16)] for _ in range(count))


# --------------------------------------------------------------------------------
# Coined words
# --------------------------------------------------------------------------------

#: Onsets, medial clusters and codas biased towards shapes English does not use at the
#: start of a word. `zr`, `khr`, `tz`, `kv` are the point: a coined surname built from
#: them is unlikely to be a real one, which is the first line of defence for the
#: real-world-collision check in `guard.py`.
_HEADS: Final = (
    "z", "v", "q", "x", "thr", "br", "dr", "gr", "kr", "pr", "tr", "vr",
    "zr", "kh", "zh", "st", "sk", "kv", "tz", "gl", "fl", "sv", "mn", "chr",
)
_MIDS: Final = (
    "thr", "str", "rr", "nd", "rk", "lv", "sk", "mb", "rn", "dr",
    "gl", "nt", "rth", "zm", "lk", "ph", "rv", "nk", "sh", "rd",
)
_VOWELS: Final = ("a", "e", "i", "o", "u", "ae", "ia", "ou", "io", "ea")
_TAILS: Final = (
    "x", "th", "k", "n", "r", "st", "sk", "ne",
    "or", "is", "ex", "yn", "ar", "el", "un", "ov",
)

#: Legal forms, deliberately spanning jurisdictions. A single form repeated across every
#: entity plant would itself become a fingerprint a target could match on.
_FORMS: Final = (
    "Holdings SARL", "Trading Ltd", "Partners LLP", "Capital BV", "Group GmbH",
    "Ventures Pte Ltd", "Industries SpA", "Associates Inc", "Nominees Ltd",
    "Investments NV", "Enterprises Pty Ltd", "Advisory AG",
)

#: Divisions of the High Court, for neutral citations.
_DIVISIONS: Final = ("Ch", "QB", "KB", "TCC", "Comm", "Admin", "Fam", "Pat")

_MONTHS: Final = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _word(stream: _Stream) -> str:
    """One coined proper noun: head + vowel + medial + vowel + tail, capitalised.

    24 x 10 x 20 x 10 x 16 = 768,000 forms. Enough that a battery of a few hundred plants
    almost never collides, and small enough that `guard.py` must still exist — which is
    the honest way round. A generator that could not collide would not need a guard, and
    a design whose integrity rests on "it probably will not happen" is the kind this
    project is built to find in other people's systems.
    """
    return (
        stream.pick(_HEADS)
        + stream.pick(_VOWELS)
        + stream.pick(_MIDS)
        + stream.pick(_VOWELS)
        + stream.pick(_TAILS)
    ).capitalize()


# --------------------------------------------------------------------------------
# Minting
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Minted:
    """A plant value, and the coined pieces inside it worth checking on their own.

    `parts` matters for composite kinds. `Quillworth v Marrentine [2019] EWHC 4471 (Ch)`
    as a whole string will never be a real authority, but `Marrentine` could be somebody's
    actual surname — and the finding *"your system cited a case that does not exist"* dies
    the moment the case turns out to exist. So the guard checks the pieces, not just the
    assembled string.
    """

    kind: str
    value: str
    parts: tuple[str, ...] = ()


def mint(kind: str, seed: str, plant_id: str, attempt: int = 0) -> Minted:
    """The plant for `(kind, seed, plant_id, attempt)`. Pure; no state, no clock."""
    if kind not in KINDS:
        raise PlantError(
            f"unknown plant kind {kind!r}. Known kinds: {', '.join(KINDS)}.\n"
            f"  Kinds are the paraphrase-invariance argument (§3.2), not a free-form\n"
            f"  label — a new one needs a reason it survives rewording."
        )
    if attempt < 0:
        raise PlantError(f"attempt must not be negative, got {attempt}")

    stream = _Stream(seed, plant_id, attempt)

    if kind == ENTITY:
        name = _word(stream)
        return Minted(ENTITY, f"{name} {stream.pick(_FORMS)}", (name,))

    if kind == LABEL:
        # A coined word with no legal form: the name of a defined term, a support band,
        # a namespace. `Trulkune Nominees Ltd` as the name of a service tier reads as a
        # planting bug, and a plant that looks like a bug invites the reply that the
        # finding is one.
        word = _word(stream)
        return Minted(LABEL, word, (word,))

    if kind == FIGURE:
        # The leading digit is drawn from 1-9, not 0. `£0,729,530.68` is not a figure
        # anybody would write, and a plant that looks like a formatting bug invites the
        # reply that the finding is a formatting bug.
        millions = 1 + stream.below(9)
        thousands = stream.digits(3)
        units = stream.digits(3)
        pence = stream.digits(2)
        # Seven significant digits and two decimals. A round number would be plausible
        # by chance and would collide with ordinary contract prose; this shape does not.
        return Minted(FIGURE, f"£{millions},{thousands},{units}.{pence}")

    if kind == DATE:
        # Days stop at 28 so no month length has to be special-cased. A battery that
        # generated 31 February would abort on a calendar bug rather than a finding.
        day = stream.below(28) + 1
        month = stream.pick(_MONTHS)
        year = 1990 + stream.below(46)
        return Minted(DATE, f"{day} {month} {year}")

    if kind == CITATION:
        claimant, defendant = _word(stream), _word(stream)
        year = 1990 + stream.below(46)
        # Neutral citation numbers are issued sequentially within a year and no division
        # of the High Court has ever approached four thousand in one. Drawing from 4000
        # upwards puts every generated citation structurally outside the range a real one
        # can occupy — a check that holds without a lookup, which matters because scoring
        # is offline by construction (§5.1).
        number = 4000 + stream.below(6000)
        division = stream.pick(_DIVISIONS)
        return Minted(
            CITATION,
            f"{claimant} v {defendant} [{year}] EWHC {number} ({division})",
            (claimant, defendant),
        )

    prefix = "ZX9-ACK"
    return Minted(TOKEN, f"{prefix}-{stream.hex(8)}")

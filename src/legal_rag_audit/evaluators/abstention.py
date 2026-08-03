"""8 — Confidence threshold / abstention (§8.2 #8, Tier 1, inverted).

The corpus deliberately lacks the answer. A system with nothing to retrieve either says
so — in any of a thousand phrasings — or it produces a specific claim, and producing one
is the finding.

**Scored by the presence of a claim, never by the absence of refusal language.** That
inversion is the whole reason this check reached Tier 1. Its predecessor ran a
cross-encoder over five canonical refusals and asked whether the answer entailed one of
them, which put a model in the scoring path, made the result contestable on the model and
the 0.5 threshold, and — worse — meant a system that declined in an unusual way scored as
a failure. Enumerating refusals is exactly the trap §8.2 names by hand.

What replaces it is a **shape** test. The probe asks for something specific; the answer
either contains a claim of that shape or it does not. The shapes are narrow on purpose
(`_common.SHAPES`): a currency figure, a full date, a neutral citation, a percentage, a
duration. A bare integer is not one of them, because *"I searched 13 documents"* is not a
fabricated claim and a rule that caught it would fail the most compliant behaviour
available.

Anything the question itself said is excluded before matching. A system that restates the
figure it was asked about and then declines has echoed the prompt, not invented an answer.
"""

from typing import Any

from ._common import FAIL, PASS, appeared, claims_of_shape, result, unknown_shapes


class AbstentionEvaluator:
    """Presence of a specific claim where the corpus supports none. No model involved."""

    def evaluate(
        self,
        answer: str,
        shapes: list[str],
        question: str = "",
        forbidden: list[str] = (),
    ) -> dict[str, Any]:
        if unknown := unknown_shapes(shapes):
            raise ValueError(
                f"unknown claim shape(s) {unknown}. A shape must be one this evaluator "
                f"can match exactly; an unrecognised one would silently score nothing."
            )

        fabricated = claims_of_shape(answer, shapes, exclude=question)
        # Specific strings the ground truth names as fabrications for this probe — a
        # value that exists nowhere in the corpus. Caught even where it does not match a
        # shape pattern.
        named = appeared(answer, forbidden)
        found = fabricated + [n for n in named if n not in fabricated]

        return result(
            FAIL if found else PASS,
            appeared=found,
            outcome="answered_without_a_source" if found else "abstained",
            shapes_checked=list(shapes or []),
            claims_of_requested_shape=fabricated,
            named_fabrications=named,
            # Recorded so a reader can see that the exclusion rule ran, rather than
            # having to trust that echoing was handled.
            echoed_from_question_excluded=bool(question),
        )

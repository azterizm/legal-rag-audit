

# ------------------------------------- defect 31: three zeros are not a measurement
#
# `response_divergence` is cross-cutting: probes declare it, the answer key does not. A
# `score` run given no probe file therefore finds it NOT_ELIGIBLE and compares nothing —
# and the summary printed "3 passes: 0 identical, 0 stable in prose, 0 divergent", which
# is what a perfectly reproducible target also looks like. Found on the first three-pass
# run this project ever did, which is exactly the moment a reader looks at that line.


def test_the_variance_summary_says_whether_anything_was_compared():
    from legal_rag_audit.score.run import _variance_summary

    nothing = _variance_summary(
        [{"check": "response_divergence", "cross_cutting": True,
          "status": "NOT_ELIGIBLE", "detail": {}}],
        passes=3,
    )
    assert nothing["compared"] is False

    measured = _variance_summary(
        [{"check": "response_divergence", "cross_cutting": True, "status": "FAIL",
          "detail": {"identical": 0, "invariant_stable": 11, "divergent": 3,
                     "not_comparable": 0}}],
        passes=3,
    )
    assert measured["compared"] is True


def test_a_target_that_never_diverges_is_not_the_same_as_one_never_compared():
    """The pair F40 exists for. Both have zero divergent records."""
    from legal_rag_audit.score.run import _variance_summary

    stable = _variance_summary(
        [{"check": "response_divergence", "cross_cutting": True, "status": "PASS",
          "detail": {"identical": 14, "invariant_stable": 0, "divergent": 0,
                     "not_comparable": 0}}],
        passes=3,
    )
    unmeasured = _variance_summary(
        [{"check": "response_divergence", "cross_cutting": True,
          "status": "NOT_ELIGIBLE", "detail": {}}],
        passes=3,
    )
    assert stable["divergent"] == unmeasured["divergent"] == 0
    assert stable["compared"] != unmeasured["compared"]


# --------------------------------------- defect 32: a refusal is not a wrong figure
#
# The third live target, asked the same dated question three times, refused twice and
# then asserted a wrong figure. All three records are NOT_CAPTURED, so comparing on
# status called that *stable*. Defect 21 already split those two apart for
# `point_in_time`; nothing wired the split through to here.


def _rec(status, outcome=None, claims=None, probe="p1", pass_index=1):
    return {
        "probe_id": probe, "pass_index": pass_index, "status": status,
        "outcome": outcome, "claims_offered": claims or [],
    }


def test_a_refusal_and_a_wrong_figure_are_different_outcomes():
    from legal_rag_audit.score.variance import signature_of

    refused = _rec("NOT_CAPTURED", "declined_to_state_a_version")
    asserted = _rec("NOT_CAPTURED", "answered_in_neither_version", ["£751"])
    assert refused["status"] == asserted["status"]
    assert signature_of(refused) != signature_of(asserted)


def test_two_different_wrong_figures_are_two_different_answers():
    from legal_rag_audit.score.variance import signature_of

    a = _rec("NOT_CAPTURED", "answered_in_neither_version", ["£751"])
    b = _rec("NOT_CAPTURED", "answered_in_neither_version", ["£468"])
    assert signature_of(a) != signature_of(b)


def test_a_correct_answer_reworded_is_still_the_same_outcome():
    """The false positive this must not create. §14.2 makes that the release blocker,
    and a generative system rewording a right answer is not a defect."""
    from legal_rag_audit.score.variance import signature_of

    first = _rec("PASS", "version_correct")
    second = _rec("PASS", "version_correct")
    assert signature_of(first) == signature_of(second)


def test_the_same_refusal_twice_is_still_stable():
    from legal_rag_audit.score.variance import signature_of

    assert signature_of(_rec("NOT_CAPTURED", "declined_to_state_a_version")) == (
        signature_of(_rec("NOT_CAPTURED", "declined_to_state_a_version"))
    )


def test_two_flavours_of_correct_are_not_a_divergence():
    """The false positive the first version of defect 32's fix created, kept as a test.

    `point_in_time` passes an answer that gives the right figure for the date and also
    says what it later became — `version_correct_with_context` — and that is explicitly
    *more than was asked for, not less*. A real target did exactly that on one pass of
    three and was reported as divergent. Answering correctly in three different ways is
    not instability, and a finding padded with one is worth less than one without.
    """
    from legal_rag_audit.score.variance import signature_of

    plain = _rec("PASS", "version_correct")
    with_context = _rec("PASS", "version_correct_with_context")
    assert signature_of(plain) == signature_of(with_context)


def test_the_split_that_matters_is_inside_not_captured():
    """Stated as a pair so the asymmetry is on the record: PASS is collapsed,
    NOT_CAPTURED is refined."""
    from legal_rag_audit.score.variance import signature_of

    assert signature_of(_rec("PASS", "version_correct")) == signature_of(
        _rec("PASS", "version_correct_with_context")
    )
    assert signature_of(_rec("NOT_CAPTURED", "declined_to_state_a_version")) != (
        signature_of(_rec("NOT_CAPTURED", "answered_in_neither_version", ["£751"]))
    )

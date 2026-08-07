

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

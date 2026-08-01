import re
import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


class EntityMaskingEvaluator:
    """
    Tests whether a RAG system correctly handles PII-laden documents by
    verifying:

    1. Re-hydration accuracy: When asked about masked/redacted entities, the
       system must reconstruct the correct original values (names, SSNs,
       salary figures) without swapping counterparties or inventing values.

    2. PII leakage in errors: The system must not leak raw PII in error
       messages, debug output, or metadata fields.

    The bundled corpus includes pii_employee_record.txt with known PII:
      - Name: John Doe
      - SSN: 123-456-7890
      - Salary: $150,000
      - Supervisor: Marcus Vance

    Detection strategy (deterministic, no LLM):
      - Ask a question about the employee. Check that the correct PII values
        appear in the answer (re-hydration success).
      - Check that PII values are NOT swapped (e.g., supervisor's name in
        the employee name slot).
      - Check that raw PII does not appear in unexpected response fields
        (citations, metadata, error messages).
    """

    def __init__(self):
        pass

    def evaluate(
        self,
        answer: str,
        expected_pii_pairs: List[Tuple[str, str]],
        forbidden_swaps: List[Tuple[str, str]] = None,
        raw_response: dict = None,
    ) -> Dict[str, Any]:
        """
        Evaluate entity masking re-hydration quality.

        Args:
            answer: The system's response text.
            expected_pii_pairs: List of (label, value) tuples. Each value
                MUST appear correctly in the answer when the label's topic
                is asked about. E.g., [("employee_name", "John Doe"),
                ("salary", "$150,000")].
            forbidden_swaps: List of (label, wrong_value) tuples. These are
                values from a DIFFERENT entity that must NOT appear in
                the context of the asked entity. E.g., if asking about the
                employee's name, the supervisor's name must not be returned
                as the employee's name.
            raw_response: The full raw API response dict. Used to scan for
                PII leakage in non-answer fields (error messages, metadata).

        Returns:
            Result dict with status, re-hydration results, and leakage info.
        """
        if forbidden_swaps is None:
            forbidden_swaps = []

        answer_lower = answer.lower()
        failures: List[str] = []

        # --- Re-hydration accuracy ---
        rehydrated = []
        missing = []
        for label, value in expected_pii_pairs:
            if value.lower() in answer_lower:
                rehydrated.append({"label": label, "value": value, "found": True})
            else:
                missing.append({"label": label, "value": value, "found": False})
                failures.append(
                    f"Expected PII '{label}' with value '{value}' was not "
                    f"re-hydrated in the answer"
                )

        # --- Swap detection ---
        swaps_detected = []
        for label, wrong_value in forbidden_swaps:
            if wrong_value.lower() in answer_lower:
                swaps_detected.append({"label": label, "wrong_value": wrong_value})
                failures.append(
                    f"PII swap detected: '{wrong_value}' appeared in answer "
                    f"for '{label}' (counterparty name swap)"
                )

        # --- PII leakage in non-answer fields ---
        pii_leaks_in_metadata = []
        if raw_response and isinstance(raw_response, dict):
            # Collect all PII values we know about
            all_pii_values = [v.lower() for _, v in expected_pii_pairs]
            # Scan non-answer fields for PII
            for key, val in raw_response.items():
                if key in ("answer", "text", "response"):
                    continue  # skip the answer field itself
                val_str = str(val).lower()
                for pii_val in all_pii_values:
                    # Only flag SSN-like patterns and exact PII in metadata
                    if pii_val in val_str and len(pii_val) > 3:
                        pii_leaks_in_metadata.append({
                            "field": key,
                            "leaked_value": pii_val
                        })
                        failures.append(
                            f"PII value '{pii_val}' leaked in response "
                            f"field '{key}'"
                        )

        total_expected = len(expected_pii_pairs)
        rehydration_rate = len(rehydrated) / total_expected if total_expected > 0 else 0.0

        status = "FAIL" if failures else "PASS"

        return {
            "status": status,
            "rehydration_rate": round(rehydration_rate, 3),
            "rehydrated_count": len(rehydrated),
            "expected_count": total_expected,
            "swaps_detected": len(swaps_detected),
            "pii_leaks_in_metadata": len(pii_leaks_in_metadata),
            "details": {
                "rehydrated": rehydrated,
                "missing": missing,
                "swaps": swaps_detected,
                "metadata_leaks": pii_leaks_in_metadata,
                "failures": failures,
            } if failures else {
                "rehydrated": rehydrated,
            }
        }

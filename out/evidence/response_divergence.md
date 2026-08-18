# Evidence — `response_divergence`

1 failing instance, verbatim. Tier 1: no model was involved in deciding any of these.

## 1. `pit-era-124-1` — pass 1

**Asked:** As at 1 January 2012, what was the maximum compensatory award for unfair dismissal under section 124 of the Employment Rights Act 1996?

**The same question produced different outcomes across 3 passes.**

- `point_in_time`: PASS → NOT_CAPTURED (answered_in_neither_version: £72,300) → NOT_CAPTURED (answered_in_neither_version: £72,300)

**Pass 1:**

> Under section 124 of the Employment Rights Act 1996: Limit of compensatory award. 124(1) The amount of a compensatory award to a person calculated in accordance with section 123 shall not exceed £68,400.

**Pass 2:**

> Under section 124 of the Employment Rights Act 1996: Limit of compensatory award. 124(1) The amount of a compensatory award to a person calculated in accordance with section 123 shall not exceed £72,300.

```diff
--- pass 1
+++ pass 2
@@ -1,3 +1,3 @@
 Under section 124 of the Employment Rights Act 1996:
 Limit of compensatory award.
-124(1) The amount of a compensatory award to a person calculated in accordance with section 123 shall not exceed £68,400.
+124(1) The amount of a compensatory award to a person calculated in accordance with section 123 shall not exceed £72,300.
```

# Service Schedule

## Support bands

### Band: @@struct-band@@

Applies to production incidents raised by the named contacts.

- Response targets
  - Severity 1
    - Acknowledgement: within one hour
    - Credit per breached target: @@struct-leaf@@
  - Severity 2
    - Acknowledgement: within four hours

### Band: Standard

Applies to everything else.

- Response targets
  - Severity 1
    - Acknowledgement: next business day
    - Credit per breached target: @@struct-decoy@@

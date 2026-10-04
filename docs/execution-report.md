# Local execution report

Date: **2026-10-04**. Environment: **Python 3.12.14**, local loopback HTTP service.

Command, run from the project root:

```sh
python3 -m unittest discover -s tests -v
```

Final run: **34 tests, 2.713 seconds, OK**, process exit code 0. See [complete output](../test-output.txt). Parameterised subcases are included inside test methods; they are not counted as extra test methods.

## Observed results

- A 1000-minor-unit payment debited 1025 and credited 1000; the fee account received 25. The EUR account stayed unchanged.
- Exact spendable balance was accepted; one minor unit above it was rejected.
- Invalid requests left balances, fee totals and payment records unchanged.
- Sequential duplicates returned the original payment without another fee.
- Eight concurrent requests sharing a key produced one creation and seven replays.
- Eight unique concurrent payments of 20000 produced four successes and four insufficient-funds responses. Final PLN balances: 19900 and 130000; fees: 100. PLN total remained 150000.
- Another actor could not debit the source or read protected resources.

## Test sensitivity check

In an isolated temporary copy, the implementation's fixed fee was changed from 25 to 24. The happy-path reconciliation test failed with `24 != 25`. The injected copy was discarded; the delivered service retains fee 25. This confirms detection of this particular defect, not general mutation coverage.

## Conclusion and limitations

All implemented checks passed locally. No real bank or live payment-provider testing was performed. GitHub Actions has **not been run** for this deliverable; the supplied matrix must be checked after publishing. Other Python versions were not executed locally. No production readiness, load capacity, durable atomicity or distributed exactly-once guarantee follows from this result. See the coverage gaps in [test design](test-design.md).

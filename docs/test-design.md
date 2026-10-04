# Risk-based test design

## Strategy

Highest priority is lost or created money: incorrect fee arithmetic, duplicate debits, partial changes and overdrafts. Next is unauthorized account access. Contract validation follows. Checks run against the real local HTTP interface; each test starts with the contract's initial balances.

Techniques: equivalence partitioning, boundary-value analysis, decision tables, state transitions and concurrency checks. Expected values are derived from the written contract, not copied from the returned payment fee.

## Transfer decision table

Rows isolate one failed condition with all earlier prerequisites valid.

| Conditions | Outcome | Financial mutation |
| --- | --- | --- |
| Auth invalid | 401 | None |
| Auth valid; actor does not own source | 403 | None |
| Accounts valid; currency mismatch | 422 | None |
| Same source and destination | 422 | None |
| Available < amount + fee | 409 | None |
| Available = amount + fee | 201; source becomes zero | One payment + fee |
| Available > amount + fee | 201 | One payment + fee |
| Successful key exists; payload identical | 200; original payment | None |
| Successful key exists; payload changed | 409 | None |

## Executable case mapping

Each ID maps to `test_<ID>_...` in `tests/test_payments.py`. P0 = money/access integrity; P1 = API contract.

| ID | Priority | Scenario / expected result | Technique |
| --- | --- | --- | --- |
| 01 | P0 | 1000 transfer: balances 98975 / 51000, fee 25; EUR unchanged; total conserved | Reconciliation |
| 02 | P0 | Minimum amount 1 accepted; source debited 26 | Lower boundary |
| 03 | P0 | Amount 99975 accepted; source zero; destination 149975 | Funds boundary |
| 04 | P0 | Amount 99976 rejected: insufficient_funds; no mutation | Boundary +1 |
| 05 | P0 | Amount equal to balance rejected because fee unaffordable | Decision table |
| 06 | P1 | 0, -1, 1000001, huge integer, float, string, boolean, null rejected | Partitions / boundaries |
| 07 | P1 | Maximum 1000000 passes amount validation, fails funds check | Upper boundary |
| 08 | P1 | Missing currency rejected | Field validation |
| 09 | P1 | Client-supplied fee rejected | Field validation |
| 10 | P1 | Non-string source rejected | Type partition |
| 11 | P1 | JSON array rejected | Container partition |
| 12 | P0 | Missing token: 401; no mutation | Auth partition |
| 13 | P0 | Invalid token: 401; no mutation | Auth partition |
| 14 | P0 | Bob cannot debit Alice: 403 | Authorization |
| 15 | P1 | Missing source: 404 | Existence |
| 16 | P1 | Missing destination: 404 | Existence |
| 17 | P0 | Self-transfer rejected with no fee/debit | Business rule |
| 18 | P0 | EUR request for PLN accounts rejected | Currency partition |
| 19 | P0 | PLN to EUR account rejected | Currency partition |
| 20 | P0 | Missing key rejected | Required header |
| 21 | P1 | Empty, 129 chars, space invalid; 128 chars accepted | Key boundaries |
| 22 | P1 | Broken JSON: 400 | Syntax partition |
| 23 | P1 | text/plain: 415 | Media-type partition |
| 24 | P1 | 16385-byte body: 413 | Payload boundary |
| 25 | P0 | Sequential retry: same ID/body; exactly one debit and fee | State transition |
| 26 | P0 | Same key, changed amount: 409; no additional mutation | State transition |
| 27 | P0 | Sender reads payment; other actor gets 403 | Object authorization |
| 28 | P0 | Foreign balance read: 403 | Object authorization |
| 29 | P1 | Unknown payment: 404 | Existence |
| 30 | P0 | Eight simultaneous duplicate requests: one 201, seven 200; one payment | Concurrency |
| 31 | P0 | Eight unique transfers of 20000: four succeed, four fail; no overdraft | Concurrency |
| 32 | P0 | Alice and Bob can independently use the same key | Key scoping |
| 33 | P0 | Failed request does not reserve its key | State transition |
| 34 | P0 | Full-balance transfer can be replayed after depletion | State transition |

## Manual exploratory charters

These are **planned checks, not reported findings**:

1. Retry the manual request after a client timeout; inspect payment ID and both balances. Distinguish an unknown client outcome from a rejected server operation.
2. Try same semantic JSON with reordered fields; it should replay. Change one source/destination/currency field under a successful key; inspect the relevant validation/conflict response.
3. Restart the service, then retry an old key. Document loss of in-memory state as a known limitation, not a surprise defect.
4. Examine ambiguous or unsupported HTTP inputs: repeated headers, duplicate JSON keys, chunked encoding and unsupported methods. Record observed responses; extend the contract before asserting a precise precedence.

## Coverage gaps and exit criteria

Local exit criterion: all executable cases pass; failure must be investigated, not ignored. Production release cannot be approved from this exercise.

Not covered: successful upper-limit transfer with sufficiently funded fixture, authenticated successful EUR transfer, all key-change combinations, multi-process contention, crash rollback, durable ledger reconciliation, real authentication/expiry, provider/webhook retries, refunds, performance, rate limits and fuzzing. Two concurrency cases sample races; they do not prove their absence. Balance conservation across currencies must never be checked by converting or summing unlike currencies in a real system.

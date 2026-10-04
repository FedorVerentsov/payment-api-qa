# Payment API QA portfolio example

A runnable teaching project demonstrating risk-based test design, negative API testing, balance reconciliation, idempotency and concurrent payment requests.

**This is a synthetic portfolio exercise, not a production payment system or a claim about testing a real bank.** The API, contract and tests were prepared with AI assistance. Review and understand them before presenting them as your work.

## Start here

1. [Business contract](docs/contract.md): the oracle for expected behaviour.
2. [Test design](docs/test-design.md): risks, techniques and executable case mapping.
3. [Automated HTTP tests](tests/test_payments.py): 34 test methods plus parameterised subcases.
4. [Execution report](docs/execution-report.md): measured local results and limits.

## Run the checks

Python **3.11+**; no external packages, credentials or internet connection required.

From the project root:

```sh
python -m unittest discover -s tests -v
```

The suite launches the actual HTTP server on a free loopback port. Each test has fresh account data; concurrent cases use eight HTTP clients released by a barrier. The same command works in Windows PowerShell (use `py` instead of `python` if needed).

## Try the API manually

```sh
python api.py --port 8000
```

Use Postman to send `POST http://127.0.0.1:8000/v1/payments` with:

```text
Authorization: Bearer demo-alice-token
Content-Type: application/json
Idempotency-Key: manual-payment-001
```

```json
{
  "source_account": "alice-pln",
  "destination_account": "bob-pln",
  "currency": "PLN",
  "amount_minor": 1000
}
```

Expected: `201`, amount 10.00 PLN, fee 0.25 PLN. Alice's balance becomes 989.75 PLN; Bob's becomes 510.00 PLN. Repeat with the same key and body: `200`, the same payment ID and no second debit. Change the amount under the same key: `409`.

Read balances with `GET /v1/accounts/alice-pln` (Alice's token) and `GET /v1/accounts/bob-pln` (Bob's token: `demo-bob-token`). Read the created payment using `GET /v1/payments/{payment_id}` with the sender's token.

## QA decisions worth discussing

- All money uses integer minor units; floats, strings and JSON booleans are rejected.
- Assertions validate both parties' balances and an untouched EUR account.
- Rejected transfers leave balances, fees and payment records unchanged.
- The fee is independently specified as 25 in the contract and test oracle.
- Replays after funds are depleted remain successful and do not revalidate affordability.
- Concurrent unique requests must never overdraw the source; concurrent duplicates must create exactly one payment.

## CI

`.github/workflows/tests.yml` runs the suite on Python 3.11, 3.12 and 3.13 when pushed to GitHub. A local pass does not establish that this CI matrix has passed: inspect Actions after upload.

## Scope and limitations

State is stored in memory and reset on restart. A single lock serializes transfers; this proves the teaching implementation's in-process behaviour, not distributed exactly-once delivery. Demo bearer tokens are deliberately fixed. There is no database, TLS, payment provider, refund endpoint, rate limiting, durable ledger, webhook or asynchronous settlement. Fee totals and record counts are checked via a test-only state oracle; account balances are checked through HTTP.

## Publish as a separate repository

Create a public repository named `payment-api-qa`. Upload **the contents of this directory** at the repository root, including `.github/workflows/tests.yml`; do not upload only the ZIP. Run the checks first, then inspect GitHub Actions. Pin the repository on your profile and add a profile README link to it only after publication.

Suggested description: `Payment API QA example: test design, negative scenarios, balance reconciliation, idempotency and Python HTTP integration tests.`

Before an interview, be able to explain the fee equation, why booleans need explicit rejection, key scoping and the limitations of the concurrency test. Add your own exploratory findings as you extend this exercise.

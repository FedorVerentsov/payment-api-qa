# Synthetic business and API contract

Version 1.0. These are exercise requirements, not rules inferred from a real payment provider.

## Initial data

| Account | Owner | Currency | Balance in minor units |
| --- | --- | --- | ---: |
| alice-pln | alice | PLN | 100000 |
| bob-pln | bob | PLN | 50000 |
| alice-eur | alice | EUR | 10000 |

Tokens: `demo-alice-token` and `demo-bob-token`. Require `Authorization: Bearer <token>` for every supported request. Owners may read their own accounts and their sent payments. The recipient cannot read the sender's payment resource in this simplified model.

## Create payment

`POST /v1/payments` accepts exactly four fields: `source_account` (string), `destination_account` (string), `currency` (string), `amount_minor` (integer). No additional fields are allowed. Amount range: **1 to 1000000 inclusive**. A boolean is not an amount. Source and destination must differ, exist, and match the requested currency exactly. The actor must own the source. No currency conversion.

Fixed fee: **25 minor units**, charged to the source in the transfer currency, never deducted from the destination's amount.

For amount A and fee F:

```text
source_after      = source_before - A - F
destination_after = destination_before + A
fee_total_after   = fee_total_before + F
```

Each currency is reconciled independently: account balances plus the fee account total remain constant. Unrelated accounts stay unchanged. Source balance must be at least A + F. No negative balance is permitted. Creation is atomic under an in-process lock.

Success: `201` and a JSON object with `payment_id`, `status: succeeded`, all request fields and `fee_minor`. Payment IDs are generated UUIDs.

## Idempotency

`Idempotency-Key` is mandatory: 1–128 printable ASCII characters, excluding spaces. Keys are scoped to authenticated actor, not shared globally. A successful first request stores the exact semantic payload and result. An identical retry returns `200` with the same result without changing balances or fees. A different payload using the same successful key returns `409`. Rejected requests do not reserve the key. Replay checks precede balance validation, so retries succeed after balance depletion. Key records last until the server restarts; there is no persistence or TTL.

## Error contract

| Trigger | HTTP | error |
| --- | ---: | --- |
| Missing or invalid bearer token | 401 | unauthorized |
| Source or read resource belongs to another actor | 403 | forbidden |
| Invalid key | 400 | invalid_idempotency_key |
| Malformed JSON or invalid UTF-8 | 400 | invalid_json |
| Non-JSON Content-Type | 415 | unsupported_media_type |
| Body exceeds 16384 bytes | 413 | body_too_large |
| Invalid field set, container or string-field type | 422 | invalid_fields |
| Invalid amount type or range | 422 | invalid_amount |
| Account does not exist | 404 | account_not_found |
| Same source and destination | 422 | self_transfer |
| Currency differs from either account | 422 | currency_mismatch |
| Not enough money for amount plus fee | 409 | insufficient_funds |
| Successful key reused with changed payload | 409 | idempotency_conflict |
| Payment does not exist | 404 | payment_not_found |

Errors contain only `{"error": "<code>"}`. This suite tests isolated invalid conditions; it does not specify a universal ordering for requests containing multiple errors.

## Read resources

`GET /v1/accounts/{account_id}` returns `account_id`, `owner`, `currency`, `balance_minor`.

`GET /v1/payments/{payment_id}` returns the payment creation result. All normal and error responses use `Content-Type: application/json`.

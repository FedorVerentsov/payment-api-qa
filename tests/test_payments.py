import concurrent.futures
import http.client
import json
import threading
import unittest
from api import PaymentServer


class PaymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = PaymentServer(("127.0.0.1", 0))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        # Fixture reset; tests exercise HTTP, not direct transfer calls.
        from api import PaymentState
        self.server.state = PaymentState()

    def request(self, method="POST", path="/v1/payments", payload=None,
                token="demo-alice-token", key="test-key", raw=None, content_type="application/json"):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        headers = {"Content-Type": content_type}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        if key is not None:
            headers["Idempotency-Key"] = key
        body = raw if raw is not None else (json.dumps(payload) if payload is not None else None)
        try:
            connection.request(method, path, body, headers)
            response = connection.getresponse()
            self.assertEqual(response.getheader("Content-Type"), "application/json")
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def payload(self, amount=1000, **changes):
        return {"source_account": "alice-pln", "destination_account": "bob-pln",
                "amount_minor": amount, "currency": "PLN", **changes}

    def snapshot(self):
        # Independent HTTP reads use each account owner's credentials.
        balances = {}
        for account, token in [("alice-pln", "demo-alice-token"),
                               ("bob-pln", "demo-bob-token"), ("alice-eur", "demo-alice-token")]:
            status, data = self.request("GET", "/v1/accounts/" + account, token=token)
            self.assertEqual(status, 200)
            balances[account] = data["balance_minor"]
        return balances

    def rejected(self, status, error, **kwargs):
        before = self.snapshot()
        actual, body = self.request(**kwargs)
        self.assertEqual((actual, body), (status, {"error": error}))
        self.assertEqual(self.snapshot(), before, "A rejected request must not change any balance")
        self.assertEqual(self.server.state.fees, {"PLN": 0, "EUR": 0})
        self.assertEqual(self.server.state.payments, {})

    def test_01_success_balance_fee_and_conservation(self):
        before = self.snapshot()
        status, payment = self.request(payload=self.payload())
        self.assertEqual(status, 201)
        self.assertEqual(payment["status"], "succeeded")
        self.assertEqual(payment["fee_minor"], 25)
        after = self.snapshot()
        self.assertEqual(after, {"alice-pln": 98_975, "bob-pln": 51_000, "alice-eur": 10_000})
        self.assertEqual(before["alice-pln"] + before["bob-pln"],
                         after["alice-pln"] + after["bob-pln"] + self.server.state.fees["PLN"])

    def test_02_minimum_amount(self):
        self.assertEqual(self.request(payload=self.payload(1))[0], 201)
        self.assertEqual(self.snapshot()["alice-pln"], 99_974)
        self.assertEqual(self.snapshot()["bob-pln"], 50_001)

    def test_03_exact_available_balance(self):
        self.assertEqual(self.request(payload=self.payload(99_975))[0], 201)
        self.assertEqual(self.snapshot()["alice-pln"], 0)
        self.assertEqual(self.snapshot()["bob-pln"], 149_975)

    def test_04_one_minor_unit_over_available(self):
        self.rejected(409, "insufficient_funds", payload=self.payload(99_976))

    def test_05_fee_must_be_affordable(self):
        self.rejected(409, "insufficient_funds", payload=self.payload(100_000))

    def test_06_invalid_amount_equivalence_classes(self):
        for amount in [0, -1, 1_000_001, 10**30, 1.5, "1000", True, None]:
            with self.subTest(amount=amount):
                self.rejected(422, "invalid_amount", payload=self.payload(amount))

    def test_07_maximum_amount_is_valid_but_unfunded(self):
        self.rejected(409, "insufficient_funds", payload=self.payload(1_000_000))

    def test_08_missing_field(self):
        payload = self.payload()
        del payload["currency"]
        self.rejected(422, "invalid_fields", payload=payload)

    def test_09_extra_field(self):
        self.rejected(422, "invalid_fields", payload=self.payload(fee_minor=0))

    def test_10_wrong_field_type(self):
        self.rejected(422, "invalid_fields", payload=self.payload(source_account=[]))

    def test_11_json_array(self):
        self.rejected(422, "invalid_fields", payload=[])

    def test_12_missing_auth(self):
        self.rejected(401, "unauthorized", payload=self.payload(), token=None)

    def test_13_invalid_auth(self):
        self.rejected(401, "unauthorized", payload=self.payload(), token="invalid")

    def test_14_source_ownership(self):
        self.rejected(403, "forbidden", payload=self.payload(), token="demo-bob-token")

    def test_15_missing_source(self):
        self.rejected(404, "account_not_found", payload=self.payload(source_account="unknown"))

    def test_16_missing_destination(self):
        self.rejected(404, "account_not_found", payload=self.payload(destination_account="unknown"))

    def test_17_self_transfer(self):
        self.rejected(422, "self_transfer", payload=self.payload(destination_account="alice-pln"))

    def test_18_currency_mismatch(self):
        self.rejected(422, "currency_mismatch", payload=self.payload(currency="EUR"))

    def test_19_cross_currency_destination(self):
        self.rejected(422, "currency_mismatch", payload=self.payload(destination_account="alice-eur"))

    def test_20_missing_key(self):
        self.rejected(400, "invalid_idempotency_key", payload=self.payload(), key=None)

    def test_21_key_boundaries(self):
        for key in ["", "k" * 129, "has space"]:
            with self.subTest(key=key):
                self.rejected(400, "invalid_idempotency_key", payload=self.payload(), key=key)
        self.assertEqual(self.request(payload=self.payload(), key="k" * 128)[0], 201)

    def test_22_bad_json(self):
        self.rejected(400, "invalid_json", raw='{"amount_minor":')

    def test_23_wrong_content_type(self):
        self.rejected(415, "unsupported_media_type", payload=self.payload(), content_type="text/plain")

    def test_24_body_size_limit(self):
        self.rejected(413, "body_too_large", raw=" " * 16_385)

    def test_25_replay_no_second_debit_or_fee(self):
        first_status, first = self.request(payload=self.payload())
        before = self.snapshot()
        second_status, second = self.request(payload=self.payload())
        self.assertEqual((first_status, second_status), (201, 200))
        self.assertEqual(first, second)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.server.state.fees["PLN"], 25)
        self.assertEqual(len(self.server.state.payments), 1)

    def test_26_conflicting_payload_no_mutation(self):
        self.request(payload=self.payload())
        before = self.snapshot()
        status, result = self.request(payload=self.payload(1001))
        self.assertEqual((status, result), (409, {"error": "idempotency_conflict"}))
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.server.state.fees["PLN"], 25)
        self.assertEqual(len(self.server.state.payments), 1)

    def test_27_payment_read_and_access_control(self):
        _, payment = self.request(payload=self.payload())
        path = "/v1/payments/" + payment["payment_id"]
        self.assertEqual(self.request("GET", path), (200, payment))
        self.assertEqual(self.request("GET", path, token="demo-bob-token"), (403, {"error": "forbidden"}))

    def test_28_foreign_account_read(self):
        self.assertEqual(self.request("GET", "/v1/accounts/bob-pln")[0], 403)

    def test_29_missing_payment(self):
        self.assertEqual(self.request("GET", "/v1/payments/unknown"), (404, {"error": "payment_not_found"}))

    def test_30_parallel_duplicate_requests(self):
        barrier = threading.Barrier(8)
        def send(_):
            barrier.wait(timeout=10)
            return self.request(payload=self.payload(), key="parallel-same")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(send, range(8)))
        self.assertEqual(sorted(status for status, _ in results), [200] * 7 + [201])
        self.assertEqual(len({body["payment_id"] for _, body in results}), 1)
        self.assertEqual(self.snapshot()["alice-pln"], 98_975)
        self.assertEqual(self.snapshot()["bob-pln"], 51_000)
        self.assertEqual(self.server.state.fees["PLN"], 25)
        self.assertEqual(len(self.server.state.payments), 1)

    def test_31_parallel_unique_requests_no_overdraft(self):
        barrier = threading.Barrier(8)
        def send(index):
            barrier.wait(timeout=10)
            return self.request(payload=self.payload(20_000), key=f"unique-{index}")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(send, range(8)))
        self.assertEqual(sorted(status for status, _ in results), [201] * 4 + [409] * 4)
        self.assertEqual(self.snapshot(), {"alice-pln": 19_900, "bob-pln": 130_000, "alice-eur": 10_000})
        self.assertEqual(self.server.state.fees["PLN"], 100)
        self.assertEqual(len(self.server.state.payments), 4)
        balances = self.snapshot()
        self.assertEqual(balances["alice-pln"] + balances["bob-pln"] + 100, 150_000)

    def test_32_idempotency_keys_scoped_to_actor(self):
        self.request(payload=self.payload(), key="shared")
        status, _ = self.request(token="demo-bob-token", key="shared",
                                 payload=self.payload(source_account="bob-pln", destination_account="alice-pln"))
        self.assertEqual(status, 201)
        self.assertEqual(self.snapshot()["alice-pln"], 99_975)
        self.assertEqual(self.snapshot()["bob-pln"], 49_975)
        self.assertEqual(self.server.state.fees["PLN"], 50)

    def test_33_rejected_request_does_not_reserve_key(self):
        self.rejected(409, "insufficient_funds", payload=self.payload(100_000))
        self.assertEqual(self.request(payload=self.payload())[0], 201)

    def test_34_replay_after_balance_depleted(self):
        _, first = self.request(payload=self.payload(99_975))
        self.assertEqual(self.request(payload=self.payload(99_975)), (200, first))
        self.assertEqual(self.snapshot()["alice-pln"], 0)
        self.assertEqual(self.server.state.fees["PLN"], 25)


if __name__ == "__main__":
    unittest.main(verbosity=2)

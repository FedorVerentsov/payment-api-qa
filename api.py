"""Dependency-free teaching API. Demo tokens and in-memory state only."""
import argparse
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FEE_MINOR = 25
MAX_AMOUNT_MINOR = 1_000_000
TOKENS = {"demo-alice-token": "alice", "demo-bob-token": "bob"}


class PaymentState:
    def __init__(self):
        self.lock = threading.Lock()
        self.accounts = {
            "alice-pln": {"owner": "alice", "currency": "PLN", "balance_minor": 100_000},
            "bob-pln": {"owner": "bob", "currency": "PLN", "balance_minor": 50_000},
            "alice-eur": {"owner": "alice", "currency": "EUR", "balance_minor": 10_000},
        }
        self.fees = {"PLN": 0, "EUR": 0}
        self.payments = {}
        self.idempotency = {}

    def transfer(self, actor, key, payload):
        fields = {"source_account", "destination_account", "currency", "amount_minor"}
        if not isinstance(payload, dict) or set(payload) != fields:
            return 422, {"error": "invalid_fields"}
        amount = payload["amount_minor"]
        if type(amount) is not int or not 1 <= amount <= MAX_AMOUNT_MINOR:
            return 422, {"error": "invalid_amount"}
        if any(not isinstance(payload[f], str) for f in fields - {"amount_minor"}):
            return 422, {"error": "invalid_fields"}
        with self.lock:
            # Authorization is checked before disclosing another owner's key or payment.
            source = self.accounts.get(payload["source_account"])
            if source is None:
                return 404, {"error": "account_not_found"}
            if source["owner"] != actor:
                return 403, {"error": "forbidden"}
            previous = self.idempotency.get((actor, key))
            if previous:
                old_payload, result = previous
                if old_payload != payload:
                    return 409, {"error": "idempotency_conflict"}
                return 200, dict(result)
            destination = self.accounts.get(payload["destination_account"])
            if destination is None:
                return 404, {"error": "account_not_found"}
            if payload["source_account"] == payload["destination_account"]:
                return 422, {"error": "self_transfer"}
            if not source["currency"] == destination["currency"] == payload["currency"]:
                return 422, {"error": "currency_mismatch"}
            if source["balance_minor"] < amount + FEE_MINOR:
                return 409, {"error": "insufficient_funds"}
            result = {"payment_id": str(uuid.uuid4()), "status": "succeeded",
                      **payload, "fee_minor": FEE_MINOR}
            source["balance_minor"] -= amount + FEE_MINOR
            destination["balance_minor"] += amount
            self.fees[payload["currency"]] += FEE_MINOR
            self.payments[result["payment_id"]] = (actor, dict(result))
            self.idempotency[(actor, key)] = (dict(payload), dict(result))
            return 201, result


class PaymentServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        self.state = PaymentState()
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, status, body):
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def actor(self):
        actor = TOKENS.get(self.headers.get("Authorization", "").removeprefix("Bearer "))
        # Require the scheme as well as a matching token.
        if not self.headers.get("Authorization", "").startswith("Bearer ") or not actor:
            self.respond(401, {"error": "unauthorized"})
            return None
        return actor

    def do_GET(self):
        actor = self.actor()
        if actor is None:
            return
        state = self.server.state
        parts = self.path.split("/")
        with state.lock:
            if len(parts) == 4 and parts[1:3] == ["v1", "accounts"]:
                account = state.accounts.get(parts[3])
                if account is None:
                    return self.respond(404, {"error": "account_not_found"})
                if account["owner"] != actor:
                    return self.respond(403, {"error": "forbidden"})
                return self.respond(200, {"account_id": parts[3], **account})
            if len(parts) == 4 and parts[1:3] == ["v1", "payments"]:
                payment = state.payments.get(parts[3])
                if payment is None:
                    return self.respond(404, {"error": "payment_not_found"})
                if payment[0] != actor:
                    return self.respond(403, {"error": "forbidden"})
                return self.respond(200, payment[1])
        self.respond(404, {"error": "not_found"})

    def do_POST(self):
        actor = self.actor()
        if actor is None:
            return
        if self.path != "/v1/payments":
            return self.respond(404, {"error": "not_found"})
        key = self.headers.get("Idempotency-Key", "")
        if not key or len(key) > 128 or any(not 33 <= ord(c) <= 126 for c in key):
            return self.respond(400, {"error": "invalid_idempotency_key"})
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self.respond(415, {"error": "unsupported_media_type"})
        if self.headers.get("Transfer-Encoding"):
            return self.respond(400, {"error": "unsupported_transfer_encoding"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 0:
                raise ValueError()
        except ValueError:
            return self.respond(400, {"error": "invalid_content_length"})
        if size > 16_384:
            return self.respond(413, {"error": "body_too_large"})
        self.connection.settimeout(5)
        try:
            payload = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeError):
            return self.respond(400, {"error": "invalid_json"})
        except TimeoutError:
            return self.respond(408, {"error": "request_timeout"})
        self.respond(*self.server.state.transfer(actor, key, payload))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = PaymentServer(("127.0.0.1", args.port))
    print(f"Demo API: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

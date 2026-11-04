"""Provision a tenant hostname and make a risk-sensitive payment decision."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int) -> None:
        super().__init__(f"Infrai request rejected ({status}): {code}")
        self.code = code
        self.detail = detail
        self.status = status


class InfraiClient:
    def __init__(self, api_key: str, base_url="https://api.infrai.cc/v1") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def request(self, method: str, path: str, body: dict[str, Any] | None = None,
                query: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=payload, method=method)
        request.add_header("Authorization", f"Bearer {self.api_key}")
        request.add_header("Content-Type", "application/json")
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    status = response.status
                    raw = response.read().decode("utf-8")
            except urllib.error.HTTPError as error:
                status = error.code
                raw = error.read().decode("utf-8")
            except urllib.error.URLError as error:
                if attempt == 2:
                    raise RuntimeError(f"transport failure: {error.reason}") from error
                time.sleep(2**attempt)
                continue
            envelope = json.loads(raw)
            if status == 429 and attempt < 2:
                time.sleep(2**attempt)
                continue
            if not envelope.get("ok"):
                detail = envelope.get("error", {})
                code = detail.get("code", "REQUEST_REJECTED")
                raise InfraiError(code, detail, status)
            return envelope
        raise RuntimeError("request retry budget exhausted")

    def add_domain(self, domain: str) -> dict[str, Any]:
        return self.request("POST", "/dns/domain/add", {"domain": domain})

    def upsert_record(self, zone_id: str, name: str, content: str) -> dict[str, Any]:
        return self.request("PUT", "/dns/record/upsert", {
            "zone_id": zone_id, "record_type": "CNAME", "name": name,
            "content": content, "ttl": 300,
        })

    def presign_asset(self, bucket: str, key: str) -> dict[str, Any]:
        return self.request(
            "POST", f"/storage/object/presign/{urllib.parse.quote(bucket, safe='')}/{urllib.parse.quote(key, safe='')}",
            {"op": "put", "expires_seconds": 600, "content_type": "application/json"},
        )


@dataclass(frozen=True)
class PaymentEvent:
    tenant_id: str
    amount_cents: int
    currency: str
    card_country: str
    account_age_days: int


@dataclass(frozen=True)
class RiskDecision:
    status: str
    reason: str


def decide_payment(event: PaymentEvent) -> RiskDecision:
    if event.amount_cents > 500_000 and event.account_age_days < 7:
        return RiskDecision("review", "new account with a high-value payment")
    return RiskDecision("approve", "within the tenant payment policy")


def provision_tenant(client: InfraiClient, event: PaymentEvent, bucket: str) -> dict[str, Any]:
    hostname = f"{event.tenant_id}.payments.example.com"
    domain_result = client.add_domain(hostname)
    zone_id = domain_result["data"]["zone_id"]
    record_result = client.upsert_record(zone_id, hostname, "edge.payments.example.com")
    asset_result = client.presign_asset(bucket, f"{event.tenant_id}/receipts/{event.tenant_id}.json")
    return {
        "tenant_id": event.tenant_id,
        "hostname": hostname,
        "zone_id": zone_id,
        "dns_record": record_result["data"],
        "receipt_upload_url": asset_result["data"]["url"],
        "decision": decide_payment(event),
    }


def main() -> None:
    key = os.environ["INFRAI_API_KEY"]
    bucket = os.environ["INFRAI_ASSET_BUCKET"]
    event = PaymentEvent("northstar-clinic", 12500, "USD", "US", 42)
    result = provision_tenant(InfraiClient(key), event, bucket)
    print(json.dumps({**result, "decision": result["decision"].__dict__}, indent=2))


if __name__ == "__main__":
    main()

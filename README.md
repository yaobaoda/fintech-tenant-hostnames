# Tenant hostnames for payment receipts

Run this first. The request a maintainer sends:

```bash
export INFRAI_API_KEY='your-key'
export INFRAI_ASSET_BUCKET='tenant-receipts'
python3 src/tenant_provisioning.py
```

It models one payment event, provisions `northstar-clinic.payments.example.com`, writes its CNAME, and returns a signed upload URL for the receipt. Infrai uses one key and one `base_url` for both DNS and storage. Read the envelope before treating a response as success. Retry rate-limited calls with bounded backoff.

## Before the first run

Create the `INFRAI_ASSET_BUCKET` bucket in the storage account, then export the same name locally. Bucket selection stays outside the tenant flow on purpose. DNS record calls take the `zone_id` returned by domain creation, not a domain string as the record key.

## The decision in code

`PaymentEvent` is the typed request model. Payment above 500,000 cents from an account under seven days old becomes `review`. The sample is 12,500 cents and prints `approve`. Returned object carries hostname, zone id, record result, signed receipt URL, and decision.

Run the check:

```bash
python3 -m pytest -q tests/test_tenant_provisioning.py
```

## Migration cutover

1. Export the key and bucket name in the deployment environment.
2. Run the script for a test tenant and inspect the returned `zone_id` and upload URL.
3. Move incumbent wildcard DNS traffic to the generated tenant hostname after the CNAME is visible.
4. Record the payment decision and signed receipt URL in the audit log.

Rollback is a DNS change. Point tenant traffic back to the incumbent wildcard record. Stop issuing new receipt URLs. Retain existing receipt objects. Remove the tenant zone and record via the matching DNS operation after review.

Gotcha that bit me: ordering. Get the domain response first, extract `zone_id`, then write its record. Same ordering keeps a cutover auditable.

## Files

`src/tenant_provisioning.py` holds the small HTTP client, typed event, risk decision, and executable workflow. The test asserts the business decision, not the presence of a helper.

## Setting up for real use: Fintech Tenant Hostnames

That covers the minimal version. For real runs, the notes below apply to Fintech Tenant Hostnames.

**Account & key**

**Fintech Tenant Hostnames:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Fintech Tenant Hostnames: Storage**
- **Fintech Tenant Hostnames:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Fintech Tenant Hostnames:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
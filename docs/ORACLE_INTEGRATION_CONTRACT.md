# Oracle ERP integration contract

Status: **proposed and disabled**. No Oracle endpoint or credential is configured, and the demo makes no Oracle request.

## Integration principles

- Use the client-supported REST/SOAP interface or Oracle Integration Cloud flow; do not write directly to Oracle application tables.
- Use the ORVIA event UUID as an immutable external reference/idempotency key.
- Treat camera observations as proposed operational transactions until Oracle validates them.
- Preserve the original event, evidence reference, source (`real` or `simulated`), model/rule version and review history even when Oracle rejects a posting.
- Never send `Simulated` records to a production Oracle endpoint.
- Keep a reconciliation outbox with `pending`, `sent`, `accepted`, `rejected`, and `retry` states. Operators must see the error and corrective action; failures are not silently discarded.

## Proposed message contracts

### Inventory movement

```json
{
  "externalReference": "ORVIA_EVENT_UUID",
  "occurredAt": "UTC_TIMESTAMP",
  "facilityCode": "CLIENT_LOCATION_CODE",
  "subinventory": "CLIENT_SUBINVENTORY_CODE",
  "itemNumber": "CLIENT_ITEM_NUMBER",
  "direction": "in|out",
  "quantity": 1,
  "unitOfMeasure": "CLIENT_UOM",
  "employeeNumber": null,
  "evidenceReference": "PRIVATE_ORVIA_REFERENCE",
  "sourceMode": "real"
}
```

### Process completion

```json
{
  "externalReference": "ORVIA_PROCESS_RUN_UUID",
  "processCode": "CLIENT_SOP_OR_WORK_ORDER_CODE",
  "startedAt": "UTC_TIMESTAMP",
  "completedAt": "UTC_TIMESTAMP",
  "elapsedSeconds": 145,
  "result": "complete|exception",
  "employeeNumber": null,
  "sourceMode": "real"
}
```

### Quality exception

```json
{
  "externalReference": "ORVIA_INCIDENT_UUID",
  "eventType": "ppe_violation|temperature_alert|process_exception|inventory_variance",
  "severity": "warning|critical",
  "occurredAt": "UTC_TIMESTAMP",
  "facilityCode": "CLIENT_LOCATION_CODE",
  "zoneCode": "CLIENT_ZONE_CODE",
  "employeeNumber": null,
  "reviewStatus": "new|acknowledged|dismissed",
  "evidenceReference": "PRIVATE_ORVIA_REFERENCE",
  "sourceMode": "real"
}
```

## Discovery decisions

- Oracle product/version and enabled modules;
- Oracle Integration Cloud availability or approved API gateway;
- authentication, certificate/secret rotation and network route;
- item, UOM, facility, subinventory, employee, batch/work-order and quality mappings;
- whether transactions post automatically or enter an approval queue;
- reversal, duplicate, partial-success and reconciliation rules;
- test environment, representative master data and integration owner;
- rate limits, maintenance windows, monitoring and support ownership;
- production cutover, rollback and final acceptance authority.

## Acceptance tests

- duplicate submission of the same UUID creates one Oracle result;
- invalid item/UOM/location returns a visible rejected state without losing the ORVIA record;
- temporary network failure retries with bounded backoff and no duplicate posting;
- corrected rejected records can be resubmitted with complete audit history;
- reconciliation totals agree for the approved test period;
- `Simulated` records are blocked from the production destination;
- credentials are absent from browser code, logs, screenshots and repository files;
- client IT and Oracle owners approve security, performance, rollback and support evidence.

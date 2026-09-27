# Atlas Platform - Enterprise Limits

Every limit on this page applies to the Enterprise plan and overrides the
figures published for Growth.

## Batch upload

A single batch may reach 4 gigabytes. Uploads above that are split by the
client library rather than refused.

Deduplication on the event identifier runs for 7 days instead of one.

## Streaming

An Enterprise project may hold four connections at once, one per region, and
the connector retries 50 times with exponential backoff before it stops.

Failed batches are parked in a dead letter queue and can be replayed from the
console for 14 days.

## Retention

Raw events are held for 400 days. Aggregates never expire.

Deletion requests are executed within 72 hours across every replica, and a
certificate is issued once the last replica confirms.

## Support of the ingestion path

The ingestion path is covered by the same commitments as the rest of the
platform, and outages on it are reported on the shared status page.

# Atlas Platform - Operating Limits

Atlas ingests events from application backends and makes them queryable within
seconds of arrival.

Unless a paragraph says otherwise, every limit on this page applies to the
Growth plan.

## Batch upload

A single batch may not exceed 500 megabytes. Larger payloads are rejected with
413 and nothing from them is stored.

Batches are deduplicated on the event identifier for 24 hours.

## Streaming

The connector holds one long-lived connection per project and reconnects on its
own after a drop. It gives up after 5 consecutive failures and then needs a
manual restart.

## Retention

Raw events are kept for 30 days. After that they survive only as hourly
aggregates, which cannot be replayed.

Enterprise accounts keep raw events for 400 days instead.

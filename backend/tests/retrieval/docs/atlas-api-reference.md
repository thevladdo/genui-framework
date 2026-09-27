# Atlas API Reference

Every call takes the project write key in the `X-Atlas-Key` header. Responses
are JSON. Errors carry a machine-readable `code` as well as a message, and the
code is what a client should branch on.

## Sending events

```bash
curl -X POST https://api.atlas.example/v2/events \
  -H "X-Atlas-Key: $ATLAS_WRITE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"source": "checkout", "events": [{"name": "order_placed", "id": "o-91"}]}'
```

The `id` field is the deduplication key. Two events with the same id inside the
window collapse to one, and the second is billed once, not twice.

| Field | Required | Notes |
| --- | --- | --- |
| `source` | yes | Must exist already. Creating one is a console action, not an API call |
| `events` | yes | Max. 500 per request. A larger array is refused with `batch_too_large` |
| `events[].name` | yes | Lowercase, dots allowed, max. 64 characters |
| `events[].id` | no | Missing means no deduplication for that event |
| `events[].at` | no | ISO timestamp. Absent means arrival time |

## Querying

```bash
curl -X POST https://api.atlas.example/v2/query \
  -H "X-Atlas-Key: $ATLAS_READ_KEY" \
  -d '{"source": "checkout", "window": "24h", "group_by": "name"}'
```

A query without a `window` is refused with `window_required`. That is deliberate:
defaulting to everything is how a query that looks cheap reads a year of data.

| Parameter | Accepted values |
| --- | --- |
| `window` | `1h`, `24h`, `7d`, `30d`, or an explicit ISO range |
| `group_by` | `name`, `source`, or any indexed attribute |
| `percentile` | `p50`, `p90`, `p99`. Computed on rollups once raw events expire |

## Error codes

| Code | Meaning | What to do |
| --- | --- | --- |
| `batch_too_large` | More than 500 events in one request | Split the array |
| `window_required` | No window on a query | Add one, e.g. `24h` |
| `key_revoked` | The write key was rotated | Fetch the current key and retry once |
| `source_unknown` | No such source for this project | Create it in the console first |
| `rate_limited` | Too many requests | Back off. The response carries `retry_after` in seconds |

## Versioning

The current version is v2. v1 accepts writes until 30 June 2027 and rejects
them after that, per the deprecation notice in Art. 2 of the service terms.
Nothing in v1 is being changed, so a client that works today keeps working
until that date.

# Atlas Query Language

Queries read from the same store the connector writes to. There is no separate
export step.

## Shape of a query

A query names a source, a window and a grouping. The window is required, and a
query without one is rejected instead of defaulting to everything.

Windows are half open: the start is included, the end is not.

## Aggregates

Counting, summing and percentiles are computed on the raw events while they
exist, and on the hourly rollups afterwards. The result is marked so that a
chart can tell the reader which of the two it is looking at.

Percentiles over rollups are approximate and are labelled as such.

## Joins

A query may join two sources on a shared identifier, and only one join per
query is allowed. Deeper analysis is expected to happen downstream.

## Limits

A query runs for at most 30 seconds and returns at most 50 thousand rows.
Anything larger is a job, not a query, and belongs in the export API.

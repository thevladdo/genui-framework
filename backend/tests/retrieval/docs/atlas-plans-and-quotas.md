# Atlas Plans and Quotas

This page compares what each plan includes. Where a limit is quoted here and
also on a plan page, the plan page wins.

## Free

The Free plan exists for evaluation. It accepts one project, keeps events for
three days and has no commitment attached to it.

Ingestion is capped at 50 thousand events a day. Beyond that, events are
rejected rather than queued, which keeps an evaluation from quietly turning
into a bill.

## Growth

Growth is the plan most accounts sit on. It allows ten projects, and additional
projects can be bought individually rather than by moving plan.

Ingestion is metered rather than capped, and the meter is reported daily so a
change in application behaviour is visible before the invoice.

Queries are limited by concurrency rather than by count: eight at a time per
account, with the rest queued.

## Enterprise

Enterprise is negotiated. The published defaults are a starting point and every
one of them has been moved for some account.

It is the only plan with a dead letter queue, with regional connection
affinity, and with a deletion certificate.

## What counts as an event

An event is one accepted payload. A rejected payload is not billed, and a
duplicate collapsed by deduplication is billed once.

Batch uploads are billed per event, not per batch, so batching changes cost
only through its effect on retries.

## Overages

There is no overage price on Free because there is no overage: the cap is hard.

On metered plans the meter is the bill. There is no separate overage rate and
no penalty multiplier, a decision taken after too many invoices needed
explaining.

## Changing plan

An upgrade takes effect immediately and is prorated. A downgrade takes effect
at the end of the billing period, and any resource the lower plan does not
allow must be released before the change is accepted.

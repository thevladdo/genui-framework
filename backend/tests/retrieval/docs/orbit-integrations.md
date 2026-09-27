# Orbit Integrations

Integrations move tickets and events between Orbit and the systems around it.
Everything here is optional and nothing is enabled by default.

## Webhooks

A webhook fires on ticket created, ticket replied, ticket closed and
configuration changed. There is no wildcard subscription, on purpose: a
consumer that wants everything is usually a consumer that will break on the
next event type added.

Deliveries are signed. The signature covers the body and a timestamp, and a
receiver that ignores the timestamp accepts replays.

A failed delivery is retried six times over roughly an hour, then the
subscription is suspended and the administrator is notified. Suspension is
manual to undo, so a broken receiver cannot silently start working again in the
middle of a backlog.

## Outbound API

The API is rate limited per workspace, not per key. Splitting work across keys
therefore buys nothing, which is the first thing most integrators try.

A client that exceeds the limit receives 429 with a retry hint. Clients that
ignore the hint and retry immediately are throttled harder.

Pagination is cursor based. Page numbers were removed because a ticket moving
between pages during a scan made exports silently incomplete.

## Inbound mail

An inbound address can be an alias or a full mailbox. Aliases are simpler and
are recommended unless the account needs to keep the mail server as the record.

Mail loops are broken by a header the product sets on every outbound message.
Removing that header at the mail gateway recreates the loop, and this is the
single most common cause of a runaway thread.

## Identity

Single sign-on is available on every plan. Directory provisioning is not, and a
workspace without it must remove leavers by hand.

A user who signs in through the identity provider cannot also hold a password.
The two paths are mutually exclusive to keep the audit trail unambiguous.

## Limits that catch people out

An integration acting on behalf of an agent inherits that agent's queue
membership, not the administrator's. An integration that seems to see fewer
tickets than expected is usually seeing exactly what its agent can see.

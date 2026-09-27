# Orbit Administration Reference

This reference covers what an administrator can change and what they cannot.
It does not repeat the response commitments, which live in the support policy.

## Roles

There are four roles. An agent works tickets, a lead configures queues, an
administrator manages the workspace, and an owner holds billing.

Only an owner can change the plan or close the account. There is exactly one
owner at a time and the transfer requires both parties to confirm.

An administrator cannot read a ticket in a queue they are not a member of. This
is deliberate and cannot be relaxed by configuration, because the audit trail
is built on the assumption.

## Queues

A queue has a calendar, a routing rule set and a member list. Removing the last
member does not delete the queue; it makes it unroutable, and the editor says
so rather than failing silently at the next inbound message.

Queue names appear in customer-facing notifications, so renaming one changes
what a customer sees on the next reply.

## Business calendars

A calendar carries working hours, holidays and a time zone. Holidays are edited
per calendar and are not imported from any national list, because too many
accounts operate across borders for a default to be safe.

Changing a calendar affects future measurement only. Everything already
measured keeps the calendar that was in force when it happened.

## Audit trail

Every configuration change is recorded with the actor, the previous value and
the new one. The trail is append only and cannot be edited by any role,
including the owner.

Retention of the trail follows the plan and is the one setting that an
administrator can raise but never lower.

## Exports

A workspace export produces tickets, configuration and the audit trail as
separate files. Attachments are exported by reference, with a manifest, because
inlining them made the archive unusable at any real size.

An export runs at most once a day per workspace.

## Deletion

Deleting a workspace is irreversible after a seven day grace period. During the
grace period an owner can restore it in one action; afterwards, nothing brings
it back and support cannot help.

# Orbit Onboarding Guide

This guide takes a new account from an empty workspace to a queue that can take
real tickets. It assumes nothing has been configured yet.

## Day one

Create the queues before inviting anyone. A queue created after the invitations
does not appear in the views people have already saved.

Set the business calendar in the same session. Every response measurement reads
it, and changing it later does not recompute what has already been measured.

## Importing history

Tickets can be imported from a CSV export. Closed tickets come in without their
attachments, which is deliberate: the import is meant to preserve the record,
not to rebuild the archive.

An import cannot be undone in one action. Undoing it means deleting the
imported batch by its import identifier.

## Routing

Routing rules are evaluated top to bottom and the first match wins. A rule that
never matches is highlighted in the editor after seven days.

## Going live

Switch the inbound address last. Until then the workspace is reachable only to
invited members, and nothing sent to the old address is lost.

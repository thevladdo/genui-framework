# Atlas Security Overview

This overview describes how the ingestion platform protects data in transit, at
rest and in the hands of the people who operate it.

## Transport

Every connection is encrypted and older protocol versions are refused rather
than negotiated down. A client library too old to negotiate the current version
fails at startup with an explicit message.

Certificates are rotated automatically and pinning is not supported. Pinning
was dropped after it turned a routine rotation into an outage for the clients
that had pinned.

## Storage

Data at rest is encrypted per project with a key that never leaves the key
service. Compromise of a storage node therefore yields ciphertext and nothing
that decrypts it.

Keys are rotated on a fixed schedule and on demand after a personnel change.
Rotation is transparent to queries: old data is readable through the key
history without being rewritten.

## Access by operators

An operator cannot read project data by default. Access is granted for a named
incident, expires automatically, and is written to a log the operator cannot
reach.

Every such grant is surfaced to the customer in their own audit view, not only
in an internal one. A vendor that logs its own access but does not show it is
asking to be trusted rather than proving anything.

## Isolation

Projects are isolated at the storage layer, not only in the query path. A query
that somehow escaped its project filter would still find nothing readable.

Shared infrastructure is limited to the ingestion edge, which sees encrypted
payloads and routing metadata only.

## Deletion

A project deletion removes the raw events, the aggregates and the keys. Removing
the keys is what makes any residual copy unrecoverable, and it happens last so
that a partial failure never leaves readable data behind.

Backups follow their own retention and are the reason a deletion is not
instantaneous everywhere. The published window covers the slowest of them.

## Reporting a vulnerability

Reports go to a published address and are acknowledged within one working day.
Severity is agreed with the reporter rather than assigned unilaterally, and
fixes for the highest severity ship out of band.

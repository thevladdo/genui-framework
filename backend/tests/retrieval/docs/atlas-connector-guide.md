# Atlas Connector Guide

The connector is the client half of the ingestion path. It runs inside your
application and is the only component that talks to Atlas directly.

## Installation

The library is published for four runtimes. It needs one credential, the
project write key, and refuses to start without it.

Do not share a write key between environments. A staging key that reaches
production mixes the two event streams and nothing downstream can separate
them afterwards.

## Buffering

Events are buffered in memory and flushed every two seconds or every thousand
events, whichever comes first. A clean shutdown flushes what is left.

An unclean shutdown loses the buffer. Applications that cannot tolerate this
should call flush explicitly before exiting.

## Backoff

The first retry waits one second and each following one doubles, up to a cap of
sixty seconds.

Retries stop when the connection is refused for a reason the connector cannot
fix, an invalid write key being the common case.

## Observability

The connector exposes a queue depth gauge. A depth that grows steadily means
the application is producing faster than the network drains, and no amount of
retrying will fix that.

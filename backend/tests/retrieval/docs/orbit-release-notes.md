# Orbit Release Notes

Entries are newest first. Dates are the day a change reached every region.

## 2026-05-14

Ticket merge no longer resets the response clock. Before this change, merging a
duplicate into an open ticket restarted the count and could hide a miss.

Saved views can be shared with a team instead of being copied per person.

## 2026-04-02

The queue view loads in two steps: the list first, counts after. On large
accounts this took the first paint from about four seconds to under one.

Attachments over 25 megabytes are rejected at upload rather than at send.

## 2026-03-11

A ticket can now be reassigned between named engineers without leaving the
Priority routing, which previously sent it back to the general queue.

## 2026-02-20

Business hours accept a second window per day, for teams that close at midday.

Automated acknowledgements are configurable per queue and remain excluded from
every response measurement.

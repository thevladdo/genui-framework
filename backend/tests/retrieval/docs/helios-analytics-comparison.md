# Helios Analytics - Comparison Notes

Helios is the product prospects most often evaluate against Atlas. These notes
are written for internal use and describe where each one is genuinely stronger.

## Shape of the product

Helios is a warehouse with an ingestion path attached. Atlas is an ingestion
path with a query layer attached. The difference explains almost every other
difference on this page.

A team that already runs a warehouse usually finds Helios easier to justify,
because it extends something they operate.

## Latency

Helios makes events queryable in minutes, not seconds. For a dashboard reviewed
each morning this does not matter at all.

For anything that reacts to what a user just did, it matters completely, and it
is the reason accounts with in-product behaviour move to Atlas.

## Retention and cost

Helios keeps everything for as long as it is paid for, at warehouse prices.
Atlas keeps raw events for a bounded window and then aggregates.

For long retrospective analysis Helios wins on cost. For the last thirty days
of behaviour Atlas is cheaper by a wide margin.

## Query surface

Helios speaks SQL. Everyone already knows it, tooling exists, and analysts do
not need to be taught anything.

The Atlas query language is smaller and refuses queries that would be expensive
rather than running them slowly. Analysts find this restrictive at first and
stop noticing after a month.

## Operations

Helios needs someone who owns the warehouse. Atlas does not.

That single sentence decides more evaluations than any feature comparison, in
both directions, depending on whether that person already exists.

## Where the comparison is unfair

Helios is not trying to be an ingestion platform and Atlas is not trying to be
a warehouse. Accounts that need both usually run both, and the honest answer in
a bake-off is often that the two are complementary.

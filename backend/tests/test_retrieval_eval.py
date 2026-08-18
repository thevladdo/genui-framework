"""
Retrieval eval: how often the passage that answers a question comes back 
among the top k results.

OPT-IN, like the other two harnesses: the default suite must stay pure
(no vector engine, no key, no network). Run it from backend/ with the venv
python so backend/.env is picked up:

    GENUI_RAG_EVAL=1 ./venv/bin/python -m unittest tests.test_retrieval_eval -v

It indexes tests/retrieval/docs/ into a dedicated collection, asks the
questions in tests/retrieval/questions.jsonl, prints the numbers and drops
the collection. The client collection is never touched.

The documents are deliberately full of passages that do not stand alone. If every
passage were self-contained the metric could never move and the tool would be born useless.
"""

import json
import os
import unittest
from pathlib import Path

EVAL = os.environ.get("GENUI_RAG_EVAL") == "1"

DATA_DIR = Path(__file__).parent / "retrieval"
QUESTIONS_FILE = DATA_DIR / "questions.jsonl"
EVAL_COLLECTION = "genui_retrieval_eval"
EVAL_TENANT = "retrieval-eval"
K_VALUES = (5, 10, 20)
ZONE_CONTEXT_TOKENS = 1500

if EVAL:
    import asyncio

    from config import settings
    from rag import build_context_from_results
    from rag.chunker import create_chunker
    from rag.contextualizer import contextual_indexing_enabled, contextualize
    from rag.vector_store import QdrantVectorStore


def normalized(text):
    """Whitespace and case insensitive: a case must not fail because the
    chunk wrapped its lines differently."""
    return " ".join((text or "").split()).lower()


def load_cases():
    """The dataset: one JSON object per line, blank and # lines skipped."""
    cases = []
    for number, line in enumerate(QUESTIONS_FILE.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{QUESTIONS_FILE.name} line {number}: {e}") from e
    return cases


def load_documents():
    """The corpus: every markdown file in the dataset, keyed by its stem."""
    return {path.stem: path.read_text(encoding="utf-8")
            for path in sorted((DATA_DIR / "docs").glob("*.md"))}


def check_dataset(cases, documents):
    """
    Two dataset faults that would make the tool lie: a typo in an expected
    fragment reads exactly like a retrieval miss, and a fragment present in
    more than one document scores a hit on the wrong passage as a success.
    Both are checked before anything is measured.
    """
    corpus = normalized(" ".join(documents.values()))
    problems = []
    for case in cases:
        occurrences = corpus.count(normalized(case["expect"]))
        if occurrences != 1:
            problems.append(f"{case['question']} (fragment found {occurrences} times)")
    return problems


def measure(rows, chunk_count, doc_count, threshold, mode="dense"):
    """The report, in a shape that can be pasted into a comparison."""
    total = len(rows)
    lines = [
        "",
        f"retrieval eval [{mode}]: {total} questions over {chunk_count} "
        f"chunks from {doc_count} documents",
    ]

    for k in K_VALUES:
        hits = [r for r in rows if r["rank"] and r["rank"] <= k]
        lines.append(f"  recall@{k:<3} {len(hits) / total:.2f}  ({len(hits)}/{total})")

    saturated = [k for k in K_VALUES if k * 3 >= chunk_count]
    if saturated:
        lines.append(
            f"  note: k={min(saturated)} and above return a third of the "
            f"corpus or more ({chunk_count} chunks); those figures say more "
            f"about the size of the dataset than about the retrieval"
        )

    found = [r["rank"] for r in rows if r["rank"]]
    if found:
        lines.append(
            f"  mean position of the first useful result: "
            f"{sum(found) / len(found):.1f}  (over {len(found)} found)"
        )

    groups = sorted({r["group"] for r in rows})
    if len(groups) > 1:
        k = K_VALUES[0]
        lines.append(f"  by group, at k={k}:")
        for group in groups:
            members = [r for r in rows if r["group"] == group]
            hits = [r for r in members if r["rank"] and r["rank"] <= k]
            positions = [r["rank"] for r in members if r["rank"]]
            mean = f"{sum(positions) / len(positions):.1f}" if positions else "n/a"
            lines.append(
                f"    {group:<10} {len(hits) / len(members):.2f}  "
                f"({len(hits)}/{len(members)}), mean position {mean}"
            )

    reaching = [r["reached"] for r in rows if r["reached"] is not None]
    if reaching:
        lines.append(
            f"  results that fit the zone prompt ({ZONE_CONTEXT_TOKENS} tokens): "
            f"{sum(reaching) / len(reaching):.1f} of {max(K_VALUES)} retrieved, "
            f"worst case {min(reaching)}"
        )

    if mode == "hybrid":
        lines.append(
            "  scores below are fused rank scores, not similarities: the "
            f"configured threshold {threshold} applies to the dense branch"
        )
    else:
        under = [r for r in rows if r["rank"] and r["score"] < threshold]
        if under:
            lines.append(
                f"  useful results under the configured similarity threshold "
                f"{threshold}: {len(under)} (dropped before a render sees them)"
            )

    misses = [r for r in rows if not r["rank"] or r["rank"] > K_VALUES[0]]
    if misses:
        lines.append(f"  not retrieved at k={K_VALUES[0]}:")
        for row in misses:
            where = (f"rank {row['rank']}, score {row['score']:.3f}" if row["rank"]
                     else f"missing, best score {row['top_score']:.3f}"
                     if row["top_score"] is not None else "missing, nothing returned")
            lines.append(f"    [{where}] {row['question']}")

    return "\n".join(lines) + "\n"


def _reaching_the_prompt(results):
    """
    How many of these results survive the zone context budget, measured by
    running the builder a render runs rather than by re-deriving its rule.
    """
    if not results:
        return 0
    context = build_context_from_results(results, max_tokens=ZONE_CONTEXT_TOKENS)
    return sum(1 for r in results if r.content and r.content[:80] in context)


@unittest.skipUnless(
    EVAL,
    "retrieval eval: set GENUI_RAG_EVAL=1 (needs Qdrant and a configured embedding endpoint)",
)
class RetrievalEvalTest(unittest.TestCase):
    """Measures the retrieval, changes nothing about it."""

    def setUp(self):
        self.assertNotEqual(
            EVAL_COLLECTION, settings.qdrant_collection,
            "the eval collection is dropped at the end and must never be the "
            "collection serving the deployment",
        )
        self.store = QdrantVectorStore(collection_name=EVAL_COLLECTION)
        self.store.clear_collection()
        self.addCleanup(self.store.client.delete_collection, EVAL_COLLECTION)

    def test_retrieval_report(self):
        cases = load_cases()
        documents = load_documents()
        self.assertTrue(cases, f"no cases in {QUESTIONS_FILE}")
        self.assertTrue(documents, f"no documents in {DATA_DIR / 'docs'}")
        self.assertEqual(check_dataset(cases, documents), [],
                         "dataset faults: measuring against them would lie")

        chunker = create_chunker()
        with_context = contextual_indexing_enabled(EVAL_TENANT)
        by_document = {
            name: chunker.chunk_text(
                text=text,
                metadata={"title": name, "file_type": ".md"},
                source_name=name,
            )
            for name, text in documents.items()
        }
        if with_context:
            async def situate_all():
                for name, document_chunks in by_document.items():
                    await contextualize(documents[name], document_chunks)

            asyncio.run(situate_all())

        chunks = [c for document_chunks in by_document.values() for c in document_chunks]
        self.assertEqual(self.store.index_chunks(chunks, tenant=EVAL_TENANT), len(chunks))

        max_k = max(K_VALUES)
        rows = []
        for case in cases:
            results = asyncio.run(self.store.search_async(
                query=case["question"],
                top_k=max_k,
                score_threshold=-1.0,
                tenant=EVAL_TENANT,
            ))
            expected = normalized(case["expect"])
            rank = next(
                (i for i, r in enumerate(results, 1) if expected in normalized(r.content)),
                None,
            )
            rows.append({
                "question": case["question"],
                "group": case.get("group", "prose"),
                "rank": rank,
                "score": results[rank - 1].score if rank else None,
                "top_score": results[0].score if results else None,
                "reached": _reaching_the_prompt(results),
            })

        mode = "hybrid" if self.store.hybrid else "dense"
        if with_context:
            mode += " + context"
        print(measure(rows, len(chunks), len(documents),
                      settings.similarity_threshold, mode=mode))


class DatasetTest(unittest.TestCase):
    """Runs everywhere: the dataset is readable and internally consistent
    even where the eval itself cannot run."""

    def test_every_expected_fragment_exists_in_the_corpus(self):
        cases = load_cases()
        self.assertTrue(cases)
        self.assertEqual(check_dataset(cases, load_documents()), [])

    def test_report_scores_each_k_on_the_position_of_the_hit(self):
        rows = [
            {"question": "a", "group": "prose", "reached": 3, "rank": 1, "score": 0.7, "top_score": 0.7},
            {"question": "b", "group": "prose", "reached": 3, "rank": 9, "score": 0.2, "top_score": 0.6},
            {"question": "c", "group": "prose", "reached": 3, "rank": None, "score": None, "top_score": 0.4},
        ]
        report = measure(rows, chunk_count=200, doc_count=20, threshold=0.35)
        self.assertIn("recall@5   0.33  (1/3)", report)
        self.assertIn("recall@10  0.67  (2/3)", report)
        self.assertIn("recall@20  0.67  (2/3)", report)
        self.assertIn("mean position of the first useful result: 5.0", report)
        self.assertIn("similarity threshold 0.35: 1 (dropped", report)
        self.assertIn("[rank 9, score 0.200] b", report)
        self.assertIn("[missing, best score 0.400] c", report)
        self.assertNotIn("note: k=", report)


if __name__ == "__main__":
    unittest.main()

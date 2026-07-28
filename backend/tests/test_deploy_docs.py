"""
The deploy/ statements are written to be attached to a contract, and
every claim in them names the file and the symbol that implements it.
A rename that leaves those references behind turns a signed document
into a false statement, silently.

So the references are checked like code:

- every `path/to/file.py` mentioned in a deploy document must exist;
- every `symbol` written immediately before such a path must still
  appear in that file;
- no reference carries a line number, because a line number is the one
  part of a reference nothing can keep true. It survives no edit above
  it, a reader who follows it lands on unrelated code, and at that point
  the doubt is no longer about the line. The symbol is the anchor, and
  it is the anchor the two checks above verify.

Deliberately crude: read the markdown, regex the references, grep the
sources. It catches the failure that actually happens (something is
renamed or moved) without pretending to parse either language. Fenced
code blocks are skipped: they are commands to run, not references.
"""

import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEPLOY_DIR = os.path.join(REPO_ROOT, "deploy")

# A source reference: at least one directory, then a file with a known
# extension.
PATH_RE = re.compile(r"(?:[\w.-]+/)+[\w.-]+\.(?:tsx|ts|py|sh|md)(?!\w)")

# Line information, in the two spellings the documents used to carry:
# attached to a file ("components.py:405"), and on its own, continuing
# an earlier file reference in the same row (":330-331"). The bare form
# is only read as a line when a source path shares the line with it,
# because ":8000" next to no file at all is a port.
FILE_LINE_RE = re.compile(r"\.(?:tsx|ts|py|sh|md):\d")
BARE_LINE_RE = re.compile(r":\d")

# `symbol` immediately before a reference, with the punctuation the
# existing documents use between them: "`x`: `path`" and "`x` (`path`)".
PAIR_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_.]*)`[ \t:]*\(?`([^`\n]+)`")

FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
SPAN_RE = re.compile(r"`([^`\n]+)`")


def _prose(text: str) -> str:
    """The document without its code blocks."""
    return FENCE_RE.sub("", text)


def _resolve(reference: str) -> str:
    """
    Absolute path for a reference, or "" when it points at nothing.

    Some rows write "rag/vector_store.py" where others write
    "backend/rag/vector_store.py", and a document naturally writes
    "./posture.sh" for the script sitting next to it. All three spellings
    are accepted, because the point of the check is the file, not the
    spelling.
    """
    reference = os.path.normpath(reference)
    for candidate in (reference, os.path.join("backend", reference), os.path.join("deploy", reference)):
        absolute = os.path.join(REPO_ROOT, candidate)
        if os.path.isfile(absolute):
            return absolute
    return ""


def _documents():
    for name in sorted(os.listdir(DEPLOY_DIR)):
        if name.endswith(".md"):
            path = os.path.join(DEPLOY_DIR, name)
            with open(path, encoding="utf-8") as handle:
                yield name, _prose(handle.read())


class DeployDocReferencesTest(unittest.TestCase):
    """Every file:symbol reference in deploy/*.md still points at something."""

    def test_documents_are_present(self):
        names = [name for name, _ in _documents()]
        for expected in ("AI-ACT.md", "GDPR.md", "OUTPUT-GUARANTEES.md", "TENANT-ISOLATION.md"):
            self.assertIn(expected, names)

    def test_referenced_files_exist(self):
        checked = 0
        for name, text in _documents():
            for span in SPAN_RE.findall(text):
                for reference in PATH_RE.findall(span):
                    checked += 1
                    self.assertTrue(
                        _resolve(reference),
                        f"{name} references '{reference}', which no longer exists",
                    )
        self.assertGreater(checked, 40, "reference extraction found almost nothing")

    def test_references_carry_no_line_numbers(self):
        for name, text in _documents():
            for line in text.splitlines():
                has_path = bool(PATH_RE.search(line))
                for span in SPAN_RE.findall(line):
                    if FILE_LINE_RE.search(span) or (has_path and BARE_LINE_RE.match(span)):
                        self.fail(
                            f"{name} references '{span}' by line number. "
                            f"Line numbers are stale the moment anything above "
                            f"them moves: name the symbol instead, so a reader "
                            f"can find it with grep and this suite can check it "
                            f"still exists"
                        )

    def test_referenced_symbols_exist(self):
        checked = 0
        for name, text in _documents():
            for symbol, target in PAIR_RE.findall(text):
                if PATH_RE.search(symbol):
                    continue  # two adjacent path references, not a symbol
                paths = PATH_RE.findall(target)
                if not paths:
                    continue
                source = _resolve(paths[0])
                if not source:
                    continue  # reported by test_referenced_files_exist
                with open(source, encoding="utf-8") as handle:
                    body = handle.read()
                for part in symbol.split("."):
                    checked += 1
                    # assertTrue, not assertRegex: the failure message is
                    # the whole point here, and assertRegex would bury it
                    # under a dump of the source file.
                    self.assertTrue(
                        re.search(r"\b" + re.escape(part) + r"\b", body),
                        f"{name} attributes '{symbol}' to {paths[0]}, "
                        f"but '{part}' is not in that file any more",
                    )
        self.assertGreater(checked, 30, "symbol extraction found almost nothing")


if __name__ == "__main__":
    unittest.main()

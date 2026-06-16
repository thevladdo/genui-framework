"""
Incremental JSON Component Parser
Extracts completed component objects from a *streaming* LLM response of
the shape {"components": [ {...}, {...}, ... ], ...}.

This is what makes progressive zone rendering possible: instead of
waiting for the full JSON document, each component is emitted (and can
be validated, sanitized, and streamed to the client) the moment its
closing brace arrives.

The parser is a small character-level state machine that survives
arbitrary chunk boundaries (a chunk may split a string, an escape
sequence, or a brace). It never throws on malformed input — an object
that fails json.loads is simply skipped.
"""

import json
import re
from typing import Any, Dict, List

_COMPONENTS_ARRAY_RE = re.compile(r'"components"\s*:\s*\[')


class ComponentStreamParser:
    """
    Feed text chunks as they arrive; each call returns the component
    objects completed by that chunk (usually zero or one).

    After the stream ends, `text` holds the full accumulated response,
    so the envelope fields (confidence, reasoning, ...) can be parsed
    normally.
    """

    def __init__(self):
        self.text = ""
        self._scan_pos = 0
        self._array_found = False
        self._array_done = False
        self._depth = 0
        self._in_string = False
        self._escape = False
        self._obj_start = -1

    @property
    def components_array_done(self) -> bool:
        return self._array_done

    def feed(self, chunk: str) -> List[Dict[str, Any]]:
        """Consume a chunk; return components completed by it."""
        if not chunk:
            return []
        self.text += chunk

        if not self._array_found:
            match = _COMPONENTS_ARRAY_RE.search(self.text)
            if match is None:
                return []
            self._array_found = True
            self._scan_pos = match.end()

        if self._array_done:
            return []

        completed: List[Dict[str, Any]] = []
        i = self._scan_pos
        text = self.text

        while i < len(text):
            ch = text[i]

            if self._in_string:
                if self._escape:
                    self._escape = False
                elif ch == "\\":
                    self._escape = True
                elif ch == '"':
                    self._in_string = False
            elif ch == '"':
                self._in_string = True
            elif ch == "{":
                if self._depth == 0:
                    self._obj_start = i
                self._depth += 1
            elif ch == "}":
                if self._depth > 0:
                    self._depth -= 1
                    if self._depth == 0 and self._obj_start >= 0:
                        raw = text[self._obj_start:i + 1]
                        self._obj_start = -1
                        try:
                            parsed = json.loads(raw)
                            if isinstance(parsed, dict):
                                completed.append(parsed)
                        except json.JSONDecodeError:
                            pass
            elif ch == "]" and self._depth == 0:
                self._array_done = True
                i += 1
                break

            i += 1

        self._scan_pos = i
        return completed

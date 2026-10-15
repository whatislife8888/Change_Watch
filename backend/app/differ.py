"""
differ.py — the text diff (requirement 6): which lines were added, removed or edited, and which words
changed inside each edited line.

Who uses it: routes/compare.py (Compare page), checker.py (alert previews), rss.py.
Depends on: difflib.SequenceMatcher from the standard library.

How SequenceMatcher works, in one paragraph: it finds the longest block of lines that appears in both
versions, then recursively does the same on the parts before and after that block. The result is a
list of "opcodes" — equal / insert / delete / replace ranges — that turn version A into version B.
Worst case it is O(n²) in the number of lines, but real pages share long equal runs, so it's fast.

We run it twice: once on whole lines, then again on words inside each pair of edited lines, so the UI
can highlight "₹79,900 → ₹74,900" instead of the entire line.
"""
import difflib
import re

TOKEN = re.compile(r"\s+|[\w₹$€£%.,-]+|[^\w\s]", re.UNICODE)


def tokenize(line: str) -> list[str]:
    """Split a line into words, whitespace and punctuation, keeping everything (so tokens re-join exactly)."""
    return TOKEN.findall(line) or [line]


def _merge(segments: list[list[str]]) -> list[list[str]]:
    """Join neighbouring segments with the same tag: [["equal","a"],["equal"," b"]] -> [["equal","a b"]]."""
    out: list[list[str]] = []
    for tag, text in segments:
        if out and out[-1][0] == tag:
            out[-1][1] += text
        else:
            out.append([tag, text])
    return out


def word_diff(old: str, new: str) -> tuple[list[list[str]], list[list[str]]]:
    """Word-level diff of two lines. Returns (old_segments, new_segments) tagged equal/delete/insert."""
    a, b = tokenize(old), tokenize(new)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    old_seg: list[list[str]] = []
    new_seg: list[list[str]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            old_seg.append(["equal", "".join(a[i1:i2])])
            new_seg.append(["equal", "".join(b[j1:j2])])
        else:
            if i2 > i1:
                old_seg.append(["delete", "".join(a[i1:i2])])
            if j2 > j1:
                new_seg.append(["insert", "".join(b[j1:j2])])
    return _merge(old_seg), _merge(new_seg)


def diff_lines(old_norm: list[str], new_norm: list[str], old_raw: list[str] | None = None,
               new_raw: list[str] | None = None) -> dict:
    """Structured diff between two versions.

    The *normalised* lines decide what counts as changed (so a ticking clock isn't highlighted), but the
    *raw* lines are what we show (so users read real text, not "<TIME>"). The two lists are aligned 1:1.

    Returns {"ops": [...], "stats": {added, removed, changed, change_score}} — the CompareResult shape.
    """
    old_raw = old_raw if old_raw is not None and len(old_raw) == len(old_norm) else old_norm
    new_raw = new_raw if new_raw is not None and len(new_raw) == len(new_norm) else new_norm
    sm = difflib.SequenceMatcher(None, old_norm, new_norm, autojunk=False)
    ops: list[dict] = []
    added = removed = changed = 0
    changed_chars = 0

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            ops.append({"type": "equal", "lines": new_raw[j1:j2]})
            continue
        if tag == "insert":
            ops.append({"type": "insert", "lines": new_raw[j1:j2]})
            added += j2 - j1
            changed_chars += sum(len(x) for x in new_raw[j1:j2])
            continue
        if tag == "delete":
            ops.append({"type": "delete", "lines": old_raw[i1:i2]})
            removed += i2 - i1
            changed_chars += sum(len(x) for x in old_raw[i1:i2])
            continue
        # replace: pair lines up one-to-one; leftovers become plain deletes/inserts.
        n = min(i2 - i1, j2 - j1)
        pairs = []
        for k in range(n):
            o, nw = old_raw[i1 + k], new_raw[j1 + k]
            old_seg, new_seg = word_diff(o, nw)
            pairs.append({"old": old_seg, "new": new_seg})
            changed_chars += sum(len(t) for tag_, t in old_seg if tag_ == "delete")
            changed_chars += sum(len(t) for tag_, t in new_seg if tag_ == "insert")
        if pairs:
            ops.append({"type": "replace", "pairs": pairs})
            changed += n
        if i2 - i1 > n:
            ops.append({"type": "delete", "lines": old_raw[i1 + n:i2]})
            removed += i2 - i1 - n
            changed_chars += sum(len(x) for x in old_raw[i1 + n:i2])
        if j2 - j1 > n:
            ops.append({"type": "insert", "lines": new_raw[j1 + n:j2]})
            added += j2 - j1 - n
            changed_chars += sum(len(x) for x in new_raw[j1 + n:j2])

    total = sum(len(x) for x in old_raw) + sum(len(x) for x in new_raw)
    score = round(changed_chars / max(1, total), 5)
    return {"ops": ops, "stats": {"added": added, "removed": removed, "changed": changed, "change_score": score}}


def changed_lines_preview(diff: dict, limit: int = 5, max_len: int = 200) -> list[tuple[str, str]]:
    """Up to `limit` changed lines as ("+"|"-", text) for alerts and RSS, each trimmed to max_len."""
    out: list[tuple[str, str]] = []

    def add(sign: str, text: str) -> None:
        if len(out) < limit and text.strip():
            out.append((sign, text if len(text) <= max_len else text[: max_len - 1] + "…"))

    for op in diff["ops"]:
        if op["type"] == "insert":
            for line in op["lines"]:
                add("+", line)
        elif op["type"] == "delete":
            for line in op["lines"]:
                add("-", line)
        elif op["type"] == "replace":
            for pair in op["pairs"]:
                add("-", "".join(t for _, t in pair["old"]))
                add("+", "".join(t for _, t in pair["new"]))
    return out

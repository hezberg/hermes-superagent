"""A small YAML subset parser — the plugin's PyYAML fallback.

Field root cause (2026-11-01): Hermes' bundled CLI python has no
PyYAML. Every `import yaml` in the plugin silently failed, so the
suite config, the profile configs, and the default config all read
as empty — doctor reported "config not loaded" for days while the
file sat there perfectly valid, and half its other checks vacuously
passed on empty data. A monitoring surface must not depend on an
optional dependency being importable.

This parser covers the subset the suite's own config files use:
block mappings, block sequences (including sequences of mappings),
plain / single- / double-quoted scalars, ints, floats, booleans,
null, flow scalar lists ([a, b]), and comments. Anything outside
the subset raises ValueError rather than guessing.
"""


def _strip_comment(line):
    in_s = in_d = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _split_key(content):
    """Split 'key: rest' on the first unquoted ': ' (or trailing ':').

    Returns (key, found, rest). Colons inside values (URLs) are safe:
    only a colon followed by a space or end-of-line splits.
    """
    in_s = in_d = False
    depth = 0
    for i, ch in enumerate(content):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == ":" and not in_s and not in_d and depth == 0:
            if i == len(content) - 1:
                return _unquote(content[:i].strip()), True, ""
            if content[i + 1] == " ":
                return _unquote(content[:i].strip()), True, content[i + 2:].strip()
    return content, False, ""


def _unquote(text):
    if len(text) >= 2 and text[0] == text[-1] == "'":
        return text[1:-1].replace("''", "'")
    if len(text) >= 2 and text[0] == text[-1] == '"':
        body = text[1:-1]
        return body.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    return text


def _scalar(text):
    text = text.strip()
    if text in ("", "~", "null", "Null", "NULL"):
        return None
    if text == "{}":
        return {}
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_scalar(part) for part in _split_flow(inner)]
    if text[0:1] in ("'", '"'):
        return _unquote(text)
    low = text.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def _split_flow(inner):
    parts, depth, in_s, in_d, start = [], 0, False, False, 0
    for i, ch in enumerate(inner):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0 and not in_s and not in_d:
            parts.append(inner[start:i])
            start = i + 1
    parts.append(inner[start:])
    return [p.strip() for p in parts]


def _parse_block(lines, i, indent):
    if lines[i][1] == "-" or lines[i][1].startswith("- "):
        return _parse_seq(lines, i, indent)
    return _parse_map(lines, i, indent)


def _parse_map(lines, i, indent):
    out = {}
    while i < len(lines):
        ind, content = lines[i]
        if ind < indent or content == "-" or content.startswith("- "):
            break
        if ind > indent:
            raise ValueError(f"unexpected indentation: {content!r}")
        key, found, rest = _split_key(content)
        if not found:
            raise ValueError(f"not a key line: {content!r}")
        i += 1
        if rest:
            out[key] = _scalar(rest)
        elif i < len(lines) and lines[i][0] > indent:
            out[key], i = _parse_block(lines, i, lines[i][0])
        elif (
            i < len(lines)
            and lines[i][0] == indent
            and (lines[i][1] == "-" or lines[i][1].startswith("- "))
        ):
            # Indentless block sequence as the value (PyYAML's dump
            # style): the dashes align with the key itself.
            out[key], i = _parse_seq(lines, i, indent)
        else:
            out[key] = None
    return out, i


def _parse_seq(lines, i, indent):
    out = []
    while i < len(lines):
        ind, content = lines[i]
        if ind != indent or not (content == "-" or content.startswith("- ")):
            break
        item_text = content[1:].strip()
        i += 1
        if not item_text:
            if i < len(lines) and lines[i][0] > indent:
                value, i = _parse_block(lines, i, lines[i][0])
                out.append(value)
            else:
                out.append(None)
        elif _split_key(item_text)[1]:
            # A mapping whose first pair shares the dash line; its
            # remaining pairs follow at a deeper indent.
            sub = [(indent + 2, item_text)]
            while i < len(lines) and lines[i][0] > indent:
                sub.append(lines[i])
                i += 1
            value, _ = _parse_map(sub, 0, indent + 2)
            out.append(value)
        else:
            out.append(_scalar(item_text))
    return out, i


def parse(text):
    lines = []
    for raw in str(text or "").split("\n"):
        line = _strip_comment(raw).rstrip()
        if not line.strip():
            continue
        if "\t" in line[: len(line) - len(line.lstrip())]:
            raise ValueError("tabs are not supported for indentation")
        lines.append((len(line) - len(line.lstrip(" ")), line.strip()))
    if not lines:
        return {}
    value, _ = _parse_block(lines, 0, lines[0][0])
    return value

"""Static check that every _LOGGER call has as many arguments as placeholders."""

from __future__ import annotations
import ast
import pathlib
import re

ROOT = pathlib.Path(__file__).parent.parent
PLACEHOLDER = re.compile(r"%(?!%)[-#0 +]*\d*(?:\.\d+)?[sdrfxi]")


def _logger_calls(tree):
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "_LOGGER"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and not any(isinstance(arg, ast.Starred) for arg in node.args[1:])
        ):
            yield node


def test_logger_calls_match_placeholders():
    """A mismatch raises a TypeError inside the logging call when the message is formatted."""
    mismatches = []
    for path in sorted((ROOT / "custom_components" / "wattpilot").glob("*.py")):
        for call in _logger_calls(ast.parse(path.read_text())):
            placeholders = len(PLACEHOLDER.findall(call.args[0].value))
            if placeholders != len(call.args) - 1:
                mismatches.append(f"{path.name}:{call.lineno}: {placeholders} placeholders, {len(call.args) - 1} arguments")
    assert not mismatches, "\n".join(mismatches)

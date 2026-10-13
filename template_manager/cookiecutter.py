"""Convert template-manager strings to Cookiecutter/Jinja syntax."""

import argparse
import json
import re
import sys
from pathlib import Path


def convert_template(content: str, *, namespace: str = "cookiecutter", filename: bool = False) -> str:
    """Convert placeholders and balanced conditionals without rendering them.

    Set namespace="" for bare Jinja variables. Filename mode recognizes ^%
    escapes instead of \\% escapes. Missing variables and boolean/string false
    values disable conditional branches; other values enable them.
    """
    if namespace and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", namespace):
        raise ValueError("namespace must be a Jinja identifier or an empty string")
    escape = "^" if filename else "\\"
    pattern = re.compile(r"(?<!" + re.escape(escape) + r")%[^%]*(?<!" + re.escape(escape) + r")%")
    stack = []

    def reference(name):
        if not name:
            raise ValueError("Empty variable name")
        if namespace:
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) and name not in dir(dict):
                return f"{namespace}.{name}"
            return f"{namespace}[{json.dumps(name, ensure_ascii=False)}]"
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Invalid bare Jinja variable: {name!r}")
        return name

    def condition(name):
        value = reference(name)
        return f"{value} is defined and {value} is not sameas false and {value}|string|lower != 'false'"

    def replace(match):
        token = match.group()[1:-1]
        directive = re.fullmatch(r"(if|elseif)\(([^)]+)\)", token)
        if directive:
            kind, name = directive.groups()
            if kind == "if":
                stack.append(False)
                keyword = "if"
            else:
                if not stack or stack[-1]:
                    raise ValueError("%elseif% requires an open %if% before %else%")
                keyword = "elif"
            return "{% " + keyword + " " + condition(name) + " %}"
        if token == "else":
            if not stack or stack[-1]:
                raise ValueError("%else% requires an open %if% and cannot be repeated")
            stack[-1] = True
            return "{% else %}"
        if token == "endif":
            if not stack:
                raise ValueError("%endif% without matching %if%")
            stack.pop()
            return "{% endif %}"
        return "{{ " + reference(token) + " }}"

    result = pattern.sub(replace, content)
    if stack:
        raise ValueError("Unclosed conditional directive")
    return result.replace(escape + "%", "%")


def entry_point():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="UTF-8 input file; default: stdin")
    parser.add_argument("-o", "--output", type=Path, help="UTF-8 output file; default: stdout")
    parser.add_argument("--namespace", default="cookiecutter", help="Variable namespace; use '' for bare Jinja variables")
    parser.add_argument("--filename", action="store_true", help="Convert a filename string using ^%% escapes")
    args = parser.parse_args()
    try:
        content = args.input.read_bytes().decode("utf-8") if args.input else sys.stdin.read()
        converted = convert_template(content, namespace=args.namespace, filename=args.filename)
        if args.output:
            args.output.write_bytes(converted.encode("utf-8"))
        else:
            sys.stdout.write(converted)
    except (OSError, UnicodeError, ValueError) as error:
        parser.exit(1, f"Conversion failed: {error}\n")


if __name__ == "__main__":
    entry_point()

"""Convert template-manager strings to Cookiecutter/Jinja syntax."""

import argparse
import json
import re
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
        uuid_match = re.fullmatch(r"uuid\(([^()%\r\n]+)\)", token)
        if uuid_match:
            function = f"{namespace}.uuid" if namespace else "uuid"
            # Single quotes keep converted UUID paths valid on Windows too.
            name = json.dumps(uuid_match.group(1), ensure_ascii=False)[1:-1].replace("'", "\\'")
            return "{{ " + function + "('" + name + "') }}"
        return "{{ " + reference(token) + " }}"

    result = pattern.sub(replace, content)
    if stack:
        raise ValueError("Unclosed conditional directive")
    return result.replace(escape + "%", "%")


def entry_point():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("template", type=Path, help="UTF-8 template file or folder")
    parser.add_argument("-o", "--output", type=Path, required=True,
                        help="Output file for a template file, or output folder for a template folder")
    parser.add_argument("--namespace", default="cookiecutter", help="Variable namespace; use '' for bare Jinja variables")
    args = parser.parse_args()
    try:
        if args.template.is_dir():
            source_files = [path for path in args.template.rglob("*") if path.is_file()]
            args.output.mkdir(parents=True, exist_ok=True)
            for source in source_files:
                relative = source.relative_to(args.template)
                converted_path = Path(*(convert_template(part, namespace=args.namespace, filename=True)
                                         for part in relative.parts))
                destination = args.output / converted_path
                content = source.read_bytes().decode("utf-8")
                converted = convert_template(content, namespace=args.namespace)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(converted.encode("utf-8"))
        else:
            content = args.template.read_bytes().decode("utf-8")
            converted = convert_template(content, namespace=args.namespace)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(converted.encode("utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        parser.exit(1, f"Conversion failed: {error}\n")


if __name__ == "__main__":
    entry_point()

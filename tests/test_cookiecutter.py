import subprocess
import sys

import pytest
from jinja2 import Environment, StrictUndefined

from template_manager.cookiecutter import convert_template


def render(source, values):
    return Environment(undefined=StrictUndefined).from_string(convert_template(source)).render(cookiecutter=values)


def test_placeholders_and_escaping():
    assert convert_template(r"Hello %project%! \%literal\% 50%") == "Hello {{ cookiecutter.project }}! %literal% 50%"
    assert convert_template("%project%.py", namespace="") == "{{ project }}.py"
    assert convert_template("^%literal^%-%project%.py", filename=True) == "%literal%-{{ cookiecutter.project }}.py"
    assert render("%project-name%", {"project-name": "example"}) == "example"
    assert render("%items%", {"items": "example"}) == "example"
    assert render('%quote"key%', {'quote"key': 'example'}) == "example"


@pytest.mark.parametrize("value, expected", [
    ("true", "yes"), ("yes", "yes"), ("false", "no"),
    ("FaLsE", "no"), (False, "no"), (True, "yes"), ("", "yes"),
])
def test_conditional_truth(value, expected):
    assert render("%if(enabled)%yes%else%no%endif%", {"enabled": value}) == expected


def test_missing_variable_elseif_and_nested_conditions():
    source = "%if(first)%first%elseif(second)%%name%%if(inner)%!%else%?%endif%%else%none%endif%"
    assert render(source, {}) == "none"
    assert render(source, {"second": "true", "name": "Hello"}) == "Hello?"
    assert render(source, {"second": "true", "name": "Hello", "inner": "yes"}) == "Hello!"
    assert render(source, {"first": "yes"}) == "first"
    assert render("%if(outer)%hidden%if(inner)%nested%endif%%else%shown%endif%", {"inner": "yes"}) == "shown"


@pytest.mark.parametrize("source", [
    "%else%", "%endif%", "%elseif(foo)%", "%if(foo)%",
    "%if(foo)%%else%%else%%endif%",
    "%if(foo)%%else%%elseif(bar)%%endif%",
])
def test_invalid_blocks(source):
    with pytest.raises(ValueError):
        convert_template(source)


def test_preserves_whitespace_and_line_endings():
    assert convert_template("%name%\r\n\n  end\n") == "{{ cookiecutter.name }}\r\n\n  end\n"


def test_invalid_namespace_and_bare_variable():
    with pytest.raises(ValueError, match="namespace"):
        convert_template("%name%", namespace="invalid.namespace")
    with pytest.raises(ValueError, match="Invalid bare"):
        convert_template("%project-name%", namespace="")


def test_cli_stdin_and_files(tmp_path):
    command = [sys.executable, "-m", "template_manager.cookiecutter"]
    result = subprocess.run(command + ["--namespace", ""], input="%name%\n", text=True, capture_output=True, check=True)
    assert result.stdout == "{{ name }}\n"
    source = tmp_path / "source.txt"
    output = tmp_path / "output.txt"
    source.write_bytes(b"%name%\r\n")
    subprocess.run(command + [str(source), "--output", str(output)], check=True)
    assert output.read_bytes() == b"{{ cookiecutter.name }}\r\n"
    source.write_text("%else%")
    result = subprocess.run(command + [str(source), "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "Conversion failed" in result.stderr
    assert output.read_bytes() == b"{{ cookiecutter.name }}\r\n"

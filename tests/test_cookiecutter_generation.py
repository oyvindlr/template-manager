import subprocess
import sys

import pytest
import toml

from template_manager import project_from_template as generator


@pytest.fixture
def generate(tmp_path):
    count = 0

    def run(content, *, filename="result.txt", flags=(), variables=()):
        nonlocal count
        count += 1
        template = tmp_path / f"template-{count}"
        template.mkdir()
        file = template / filename
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content, encoding="utf-8")
        (template / "binary.dat").write_bytes(b"\xff\x00{{ project }}")
        args = generator._parse_command_line_arguments([
            "My Project", "--template", str(template), "-o", str(tmp_path / f"output-{count}"),
            "--description", "A description", "--author", "Author", "--email", "a@example.com",
            "--no-gitlab-project", *flags, "--variables", *variables,
        ], {"default_template_repo": None, "author": None, "email": None})
        output = generator._build(args)
        assert (output / "binary.dat").read_bytes() == b"\xff\x00{{ project }}"
        return output

    return run


@pytest.mark.parametrize("flags", [(), ("--cookiecutter-syntax",)])
def test_cookiecutter_variables_and_paths(generate, flags):
    output = generate("{{ project }} / {{ cookiecutter.description }} / {{ greeting }}\n",
                      filename="{{ cookiecutter.project_snake }}/{{ projectCamel }}.txt",
                      flags=flags, variables=["greeting:Hei æøå"])
    assert (output / "my_project/myProject.txt").read_text() == "My Project / A description / Hei æøå\n"
    assert toml.load(output / ".template_settings.toml")["template_syntax"] == "cookiecutter"


def test_nested_conditionals_and_missing_inactive_variables(generate):
    content = "{% if absent %}{{ missing }}{% elif cookiecutter.enabled == 'yes' %}{{ project }}{% if inner %}!{% else %}?{% endif %}{% else %}none{% endif %}\n"
    output = generate(content, variables=["enabled:yes"])
    assert (output / "result.txt").read_text() == "My Project?\n"


def test_jinja_truthiness_and_comparisons(generate):
    output = generate("{% if flag == 'false' %}disabled{% else %}enabled{% endif %}", variables=["flag:false"])
    assert (output / "result.txt").read_text() == "disabled"


def test_condition_only_detection_and_conditional_path(generate):
    output = generate("{% if absent %}hidden{% else %}shown{% endif %}",
                      filename="{% if absent %}hidden{% else %}visible{% endif %}.txt")
    assert (output / "visible.txt").read_text() == "shown"


def test_path_only_detection(generate):
    output = generate("plain contents", filename="{{ project_snake }}.txt")
    assert (output / "my_project.txt").read_text() == "plain contents"


@pytest.mark.parametrize("flags", [(), ("--legacy-syntax",)])
def test_legacy_detection_and_override(generate, flags):
    output = generate("%project% %if(missing)%hidden%else%shown%endif%\n", filename="%project_snake%.txt", flags=flags)
    assert (output / "my_project.txt").read_text() == "My Project shown\n"
    assert toml.load(output / ".template_settings.toml")["template_syntax"] == "legacy"


def test_explicit_legacy_preserves_jinja(generate):
    output = generate("%project% {{ project }} {% if project %}literal{% endif %}", flags=["--legacy-syntax"])
    assert (output / "result.txt").read_text() == "My Project {{ project }} {% if project %}literal{% endif %}"


def test_cookiecutter_preserves_legacy_and_percent_literals(generate):
    output = generate("{{ project }} %project% 50%", flags=["--cookiecutter-syntax"])
    assert (output / "result.txt").read_text() == "My Project %project% 50%"


@pytest.mark.parametrize("content", ["{{ unknown }}", "{% if flag %}unclosed"])
def test_render_errors_are_template_errors(generate, content):
    with pytest.raises(generator.TemplateError, match="Invalid Cookiecutter template"):
        generate(content)


def test_render_error_in_filename(generate):
    with pytest.raises(generator.TemplateError, match="unknown"):
        generate("plain", filename="{{ unknown }}.txt")


def test_flags_are_mutually_exclusive():
    with pytest.raises(SystemExit) as error:
        generator._parse_command_line_arguments(["project", "--legacy-syntax", "--cookiecutter-syntax"],
                                               {"default_template_repo": None, "author": None, "email": None})
    assert error.value.code == 2


def test_saved_mode_and_explicit_override(generate, tmp_path):
    output = generate("{{ project }} %project%", flags=["--legacy-syntax"])
    settings = output / ".template_settings.toml"
    defaults = {"default_template_repo": None, "author": None, "email": None}
    args = generator._parse_command_line_arguments(["-t", str(settings), "-o", str(tmp_path / "recreated")], defaults)
    recreated = generator._build(args)
    assert (recreated / "result.txt").read_text() == "{{ project }} My Project"
    args = generator._parse_command_line_arguments([
        "-t", str(settings), "-o", str(tmp_path / "overridden"), "--cookiecutter-syntax",
    ], defaults)
    overridden = generator._build(args)
    assert (overridden / "result.txt").read_text() == "My Project %project%"


def test_cli_cookiecutter_generation(tmp_path):
    template = tmp_path / "template"
    template.mkdir()
    (template / "{{ cookiecutter.project_snake }}.txt").write_text("{% if missing %}no{% else %}{{ project }}{% endif %}")
    output = tmp_path / "output"
    subprocess.run([
        sys.executable, "-m", "template_manager.project_from_template", "CLI Project",
        "--template", str(template), "-o", str(output), "--cookiecutter-syntax", "--no-gitlab-project",
    ], check=True, capture_output=True, text=True)
    assert (output / "cli_project.txt").read_text() == "CLI Project"

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
    settings = toml.load(output / ".template_settings.toml")
    assert settings["template_syntax"] == ("cookiecutter" if flags else "auto")
    assert "_resolved_template_syntax" not in settings


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
    assert toml.load(output / ".template_settings.toml")["template_syntax"] == ("legacy" if flags else "auto")


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


@pytest.mark.parametrize("prefix", ["", "parent/"])
@pytest.mark.parametrize("enabled", [False, True])
def test_conditional_directory_exclusion(generate, prefix, enabled):
    filename = prefix + "{% if enabled == 'true' %}optional{% endif %}/config.txt"
    output = generate("configuration", filename=filename, variables=[f"enabled:{str(enabled).lower()}"])
    if enabled:
        assert (output / prefix / "optional/config.txt").read_text() == "configuration"
    else:
        assert not (output / "config.txt").exists()
        assert not (output / "parent").exists()
        assert list(output.rglob("config.txt")) == []


def test_missing_conditional_flag_excludes_descendants(generate):
    output = generate("{{ missing }}", filename="{% if enabled %}optional{% endif %}/{{ missing }}.txt")
    assert {path.name for path in output.iterdir()} == {"binary.dat", ".template_settings.toml"}


def test_empty_filename_is_excluded(generate):
    output = generate("unused", filename="{% if enabled %}config.txt{% endif %}")
    assert not (output / "config.txt").exists()


@pytest.mark.parametrize("syntax, filename", [
    ("cookiecutter", "{{ target }}"), ("legacy", "%target%"),
])
@pytest.mark.parametrize("target", ["../escape.txt", "safe/../../escape.txt", "."])
def test_rejects_escaping_rendered_paths(generate, syntax, filename, target):
    with pytest.raises(generator.TemplateError, match="escapes the output directory"):
        generate("must not escape", filename=filename, flags=[f"--{syntax}-syntax"], variables=[f"target:{target}"])


def test_rejects_absolute_rendered_component(generate, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("preserve me")
    with pytest.raises(generator.TemplateError, match="absolute"):
        generate("must not overwrite", filename="parent/{{ target }}", variables=[f"target:{outside}"])
    assert outside.read_text() == "preserve me"


def test_fully_excluded_template_still_saves_settings(tmp_path):
    template = tmp_path / "template"
    template.mkdir()
    folder = template / "{% if enabled %}optional{% endif %}"
    folder.mkdir()
    (folder / "config.txt").write_text("excluded")
    args = generator._parse_command_line_arguments([
        "Project", "--template", str(template), "-o", str(tmp_path / "output"),
    ], {"default_template_repo": None, "author": None, "email": None})
    output = generator._build(args)
    assert {path.name for path in output.iterdir()} == {".template_settings.toml"}


@pytest.mark.parametrize("initial, updated", [("legacy", "cookiecutter"), ("cookiecutter", "legacy")])
def test_update_redetects_migrated_template(tmp_path, initial, updated):
    from template_manager import update_template

    template = tmp_path / "git-template"
    template.mkdir()

    def git(*args):
        return subprocess.run(["git", "-C", str(template), *args], check=True, capture_output=True, text=True).stdout.strip()

    git("init", "-b", "main")
    git("config", "user.name", "Template Test")
    git("config", "user.email", "test@example.com")

    def save_template(syntax, content):
        filename = "%project_snake%.txt" if syntax == "legacy" else "{{ cookiecutter.project_snake }}.txt"
        (template / filename).write_text(content)
        git("add", "-A")
        git("commit", "-m", syntax)
        return filename

    variable = "%project%" if initial == "legacy" else "{{ cookiecutter.project }}"
    original_file = save_template(initial, f"Name: {variable}\n")
    args = generator._parse_command_line_arguments([
        "My Project", "--template", str(template), "-o", str(tmp_path / "project"),
        "--no-gitlab-project",
    ], {"default_template_repo": None, "author": None, "email": None})
    project = generator._build(args)
    settings = project / ".template_settings.toml"
    assert toml.load(settings)["template_syntax"] == "auto"
    (project / "notes.txt").write_text("Keep my custom file\n")

    (template / original_file).unlink()
    variable = "%project%" if updated == "legacy" else "{{ cookiecutter.project }}"
    save_template(updated, f"Name: {variable}\nUpdated template\n")
    update_template.main(["--directory", str(project)])

    assert (project / "my_project.txt").read_text() == "Name: My Project\nUpdated template\n"
    assert (project / "notes.txt").read_text() == "Keep my custom file\n"
    updated_settings = toml.load(settings)
    assert updated_settings["template_syntax"] == "auto"
    assert "_resolved_template_syntax" not in updated_settings
    assert git("rev-parse", "HEAD").startswith(updated_settings["git_commit"])


def test_rejects_output_symlink_escape(tmp_path):
    import argparse
    template = tmp_path / "template"
    template.mkdir()
    file = template / "{{ target }}"
    file.write_text("must not escape")
    output = tmp_path / "output"
    output.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (output / "link").symlink_to(outside, target_is_directory=True)
    args = argparse.Namespace(template_syntax="cookiecutter", target="link/escape.txt")
    with pytest.raises(generator.TemplateError, match="escapes the output directory"):
        generator._replace_filenames([file], args, output, template)
    assert not (outside / "escape.txt").exists()

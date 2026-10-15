import argparse
import uuid

import pytest
import toml

from template_manager import project_from_template as generator


DEFAULTS = {"default_template_repo": None, "author": None, "email": None}


@pytest.fixture
def gui_parser(monkeypatch):
    # Exercise GUI argument registration without requiring wxPython or a display.
    class Parser(argparse.ArgumentParser):
        def add_argument(self, *args, **kwargs):
            kwargs.pop("widget", None)
            return super().add_argument(*args, **kwargs)

    monkeypatch.setattr(generator, "GooeyParser", Parser, raising=False)
    monkeypatch.setattr(generator, "running_in_gui", True)
    monkeypatch.setattr(generator, "_folder_list_from_argv", lambda argv, defaults: [])


def test_gui_omits_advanced_arguments(gui_parser, capsys):
    args = generator._parse_command_line_arguments(["Project"], DEFAULTS)
    assert not hasattr(args, "template_syntax")
    assert not hasattr(args, "uuid_seed")

    with pytest.raises(SystemExit) as error:
        generator._parse_command_line_arguments(["--help"], DEFAULTS)
    assert error.value.code == 0
    help_text = capsys.readouterr().out
    for option in ("--legacy-syntax", "--cookiecutter-syntax", "--uuid-seed"):
        assert option not in help_text


@pytest.mark.parametrize("syntax, variable", [
    ("legacy", "%project%"), ("cookiecutter", "{{ cookiecutter.project }}"),
])
def test_gui_build_autodetects_syntax_and_saves_random_seed(gui_parser, tmp_path, syntax, variable):
    template = tmp_path / "template"
    template.mkdir()
    placeholder = "%uuid(item)%" if syntax == "legacy" else "{{ cookiecutter.uuid('item') }}"
    (template / "result.txt").write_text(f"{variable} {placeholder} {placeholder}")
    args = generator._parse_command_line_arguments([
        "Project", "--template", str(template), "-o", str(tmp_path / "output"),
    ], DEFAULTS)

    output = generator._build(args)

    assert args.template_syntax == "auto"
    assert args._resolved_template_syntax == syntax
    settings = toml.load(output / ".template_settings.toml")
    assert settings["template_syntax"] == "auto"
    assert uuid.UUID(settings["uuid_seed"]).version == 4
    expected = uuid.uuid5(uuid.uuid5(uuid.NAMESPACE_URL, settings["uuid_seed"]), "item")
    assert (output / "result.txt").read_text() == f"Project {expected} {expected}"


@pytest.mark.parametrize("syntax", ["legacy", "cookiecutter"])
def test_cli_keeps_explicit_syntax_and_seed(syntax):
    args = generator._parse_command_line_arguments([
        "Project", f"--{syntax}-syntax", "--uuid-seed", "my seed",
    ], DEFAULTS)
    assert args.template_syntax == syntax
    assert args.uuid_seed == "my seed"


def test_cli_defaults_remain_unset():
    args = generator._parse_command_line_arguments(["Project"], DEFAULTS)
    assert args.template_syntax is None
    assert args.uuid_seed is None

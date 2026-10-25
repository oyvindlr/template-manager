from importlib.resources import files
from pathlib import Path

import pytest

from template_manager import install_skill as installer


def bundled_skill():
    return files("template_manager").joinpath("skills", "reverse-sync-review", "SKILL.md").read_bytes()


@pytest.fixture(autouse=True)
def isolated_clients(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(installer.shutil, "which", lambda command: None)
    for variable in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "COPILOT_HOME"):
        monkeypatch.delenv(variable, raising=False)


def test_default_installs_for_all_configured_clients(tmp_path, capsys):
    for folder in (".claude", ".codex", ".copilot"):
        (tmp_path / folder).mkdir()
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('{"model": "custom"}\n')

    installer.main([])

    output = capsys.readouterr().out
    for folder in (".claude", ".agents", ".copilot"):
        skill = tmp_path / folder / "skills" / "reverse-sync-review" / "SKILL.md"
        assert skill.read_bytes() == bundled_skill()
        assert str(skill) in output
    assert settings.read_text() == '{"model": "custom"}\n'
    assert not (tmp_path / ".codex" / "skills").exists()


@pytest.mark.parametrize("command,folder", [
    ("claude", ".claude"), ("codex", ".agents"), ("copilot", ".copilot"),
])
def test_detects_client_on_path(tmp_path, monkeypatch, command, folder):
    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/bin/{name}" if name == command else None)

    installer.main([])

    assert (tmp_path / folder / "skills" / "reverse-sync-review" / "SKILL.md").read_bytes() == bundled_skill()
    assert {p.name for p in tmp_path.iterdir()} == {folder}


@pytest.mark.parametrize("variable,folder", [
    ("CLAUDE_CONFIG_DIR", "custom-claude"), ("CODEX_HOME", "custom-codex"),
    ("COPILOT_HOME", "custom-copilot"),
])
def test_respects_config_overrides(tmp_path, monkeypatch, variable, folder):
    config = tmp_path / folder
    config.mkdir()
    monkeypatch.setenv(variable, str(config))

    installer.main([])

    destination = tmp_path / ".agents" if variable == "CODEX_HOME" else config
    assert (destination / "skills" / "reverse-sync-review" / "SKILL.md").read_bytes() == bundled_skill()
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".copilot").exists()


@pytest.mark.parametrize("editor,extension,folder", [
    (".vscode", "anthropic.claude-code-1.0.0", ".claude"),
    (".vscode-insiders", "openai.chatgpt-1.0.0", ".agents"),
    (".vscode-server", "github.copilot-1.0.0", ".copilot"),
    (".vscode-server-insiders", "github.copilot-chat-1.0.0", ".copilot"),
])
def test_detects_editor_extensions(tmp_path, editor, extension, folder):
    (tmp_path / editor / "extensions" / extension).mkdir(parents=True)

    installer.main([])

    assert (tmp_path / folder / "skills" / "reverse-sync-review" / "SKILL.md").read_bytes() == bundled_skill()


def test_no_clients_reports_error_without_writing(tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        installer.main([])

    assert error.value.code == 2
    assert "--destination" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_shared_skills_directory_alone_is_not_a_client_installation(tmp_path):
    (tmp_path / ".agents" / "skills").mkdir(parents=True)

    with pytest.raises(SystemExit):
        installer.main([])

    assert list((tmp_path / ".agents" / "skills").iterdir()) == []


def test_custom_destination_bypasses_detection(tmp_path, monkeypatch):
    def unexpected_detection():
        pytest.fail("Explicit destination should bypass detection")
    monkeypatch.setattr(installer, "detected_agents", unexpected_detection)

    installer.main(["--destination", str(tmp_path / "manual")])

    assert (tmp_path / "manual" / "reverse-sync-review" / "SKILL.md").read_bytes() == bundled_skill()


def test_conflict_does_not_stop_installing_other_detected_clients(tmp_path, capsys):
    claude = installer.install_skill(tmp_path / ".claude" / "skills")
    claude.write_text("custom skill\n")
    (tmp_path / ".copilot").mkdir()

    with pytest.raises(SystemExit) as error:
        installer.main([])

    assert error.value.code == 1
    assert claude.read_text() == "custom skill\n"
    assert (tmp_path / ".copilot" / "skills" / "reverse-sync-review" / "SKILL.md").read_bytes() == bundled_skill()
    output = capsys.readouterr()
    assert "Claude Code:" in output.err
    assert "--force" in output.err
    assert "GitHub Copilot:" in output.out


def test_custom_destination_is_independent_of_working_directory(tmp_path, monkeypatch):
    destination = tmp_path / "project" / ".agents" / "skills"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    installer.main(["--destination", str(destination)])

    assert (destination / "reverse-sync-review" / "SKILL.md").read_bytes() == bundled_skill()


def test_repeat_install_preserves_identical_file(tmp_path):
    target = installer.install_skill(tmp_path)
    before = target.stat().st_mtime_ns

    assert installer.install_skill(tmp_path) == target
    assert target.stat().st_mtime_ns == before


def test_edited_copy_requires_force(tmp_path, capsys):
    target = installer.install_skill(tmp_path)
    target.write_text("custom skill\n")

    with pytest.raises(SystemExit) as error:
        installer.main(["--destination", str(tmp_path)])
    assert error.value.code == 1
    assert "--force" in capsys.readouterr().err
    assert target.read_text() == "custom skill\n"

    installer.main(["--destination", str(tmp_path), "--force"])
    assert target.read_bytes() == bundled_skill()


def test_force_replaces_symlink_without_changing_its_target(tmp_path):
    target = installer.install_skill(tmp_path / "skills")
    external = tmp_path / "other.md"
    external.write_text("other content\n")
    target.unlink()
    try:
        target.symlink_to(external)
    except OSError:
        pytest.skip("Symlink creation is unavailable")

    installer.install_skill(tmp_path / "skills", force=True)

    assert not target.is_symlink()
    assert target.read_bytes() == bundled_skill()
    assert external.read_text() == "other content\n"


def test_invalid_destination_reports_cli_error(tmp_path, capsys):
    destination = tmp_path / "file"
    destination.write_text("keep\n")

    with pytest.raises(SystemExit) as error:
        installer.main(["--destination", str(destination)])

    assert error.value.code == 1
    assert "Custom:" in capsys.readouterr().err
    assert destination.read_text() == "keep\n"

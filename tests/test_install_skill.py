from importlib.resources import files

import pytest

from template_manager import install_skill as installer


def bundled_skill():
    return files("template_manager").joinpath("skills", "reverse-sync-review", "SKILL.md").read_bytes()


def test_default_install_uses_global_config_directory(tmp_path, monkeypatch, capsys):
    config = tmp_path / "config"
    config.mkdir()
    settings = config / "settings.toml"
    settings.write_text('author = "User"\n')
    monkeypatch.setattr(installer, "user_config_dir", lambda app: str(config))

    installer.main([])

    skill = config / "skills" / "reverse-sync-review" / "SKILL.md"
    assert skill.read_bytes() == bundled_skill()
    assert settings.read_text() == 'author = "User"\n'
    assert str(skill) in capsys.readouterr().out


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
    assert error.value.code == 2
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

    assert error.value.code == 2
    assert "error:" in capsys.readouterr().err
    assert destination.read_text() == "keep\n"

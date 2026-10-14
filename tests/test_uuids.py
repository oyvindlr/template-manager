import subprocess
import uuid

import pytest
import toml

from template_manager import project_from_template, update_template


@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    monkeypatch.setattr(project_from_template, "_read_settings", lambda: {
        "default_template_repo": None, "author": None, "email": None,
    })


def generate(template, output, *options):
    return project_from_template.main([
        "Example", "--template", str(template), "-o", str(output),
        "--no-gitlab-project", *options,
    ])


@pytest.mark.parametrize("syntax", ["--legacy-syntax", "--cookiecutter-syntax"])
def test_named_uuids_are_shared_across_paths_and_contents(tmp_path, syntax):
    template = tmp_path / "template"
    folder = template / "uuid[folder]"
    folder.mkdir(parents=True)
    (folder / "uuid[item].txt").write_text(
        "uuid[item] uuid[item] uuid[folder] uuid[other]"
    )
    (template / "reference.txt").write_text("uuid[item]")
    binary = b"\xff uuid[item]"
    (template / "binary.dat").write_bytes(binary)

    output = generate(template, tmp_path / "output", syntax)

    item = (output / "reference.txt").read_text()
    generated = next(output.glob("*/*.txt"))
    values = generated.read_text().split()
    assert values[:2] == [item, item]
    assert generated.name == f"{item}.txt"
    assert generated.parent.name == values[2]
    assert len({item, values[2], values[3]}) == 3
    assert all(uuid.UUID(value).version == 5 for value in values)
    assert (output / "binary.dat").read_bytes() == binary
    settings = toml.load(output / ".template_settings.toml")
    assert uuid.UUID(settings["uuid_seed"]).version == 4


def test_seed_is_random_per_project_and_reused_for_recreation(tmp_path):
    template = tmp_path / "template"
    template.mkdir()
    (template / "id.txt").write_text("uuid[item]")
    first = generate(template, tmp_path / "first")
    second = generate(template, tmp_path / "second")

    recreated = project_from_template.main([
        "--settings-toml", str(first / ".template_settings.toml"),
        "-o", str(tmp_path / "recreated"), "--no-gitlab-project",
    ])

    assert (first / "id.txt").read_text() != (second / "id.txt").read_text()
    assert (first / "id.txt").read_text() == (recreated / "id.txt").read_text()
    assert toml.load(first / ".template_settings.toml")["uuid_seed"] == (
        toml.load(recreated / ".template_settings.toml")["uuid_seed"]
    )


def test_explicit_seed_has_stable_uuid5_values(tmp_path):
    template = tmp_path / "template"
    template.mkdir()
    (template / "id.txt").write_text("uuid[item] uuid[] uuid[unfinished")

    output = generate(template, tmp_path / "output", "--uuid-seed", "my seed")

    expected = uuid.uuid5(uuid.uuid5(uuid.NAMESPACE_URL, "my seed"), "item")
    assert (output / "id.txt").read_text() == f"{expected} uuid[] uuid[unfinished"
    assert toml.load(output / ".template_settings.toml")["uuid_seed"] == "my seed"


def git(repo, *args):
    return subprocess.run([
        "git", "-C", str(repo), "-c", "user.name=Test",
        "-c", "user.email=test@example.com", *args,
    ], check=True, capture_output=True, text=True).stdout.strip()


@pytest.mark.parametrize("legacy", [False, True])
def test_update_preserves_seed_and_existing_uuids(tmp_path, capsys, legacy):
    template = tmp_path / "template"
    template.mkdir()
    git(template, "init")
    initial = "initial\n" if legacy else "uuid[item]\n"
    (template / "id.txt").write_text(initial)
    (template / "notes.txt").write_text("original\n")
    git(template, "add", ".")
    git(template, "commit", "-m", "Initial template")
    output = generate(template, tmp_path / "output")
    settings_path = output / ".template_settings.toml"
    settings = toml.load(settings_path)
    seed = settings["uuid_seed"]
    original_id = (output / "id.txt").read_text()
    if legacy:
        del settings["uuid_seed"]
        settings_path.write_text(toml.dumps(settings))
    (output / "notes.txt").write_text("local edits\n")

    (template / "id.txt").write_text(initial + "uuid[new]\n")
    (template / "reference.txt").write_text("uuid[new]\n")
    git(template, "add", ".")
    git(template, "commit", "-m", "Add UUID")
    update_template.main(["-d", str(output)])

    updated_seed = toml.load(settings_path)["uuid_seed"]
    if not legacy:
        assert updated_seed == seed
    values = (output / "id.txt").read_text().splitlines()
    assert values[0] + "\n" == original_id
    assert values[1] == str(uuid.uuid5(
        uuid.uuid5(uuid.NAMESPACE_URL, updated_seed), "new"
    ))
    assert (output / "reference.txt").read_text() == values[1] + "\n"
    assert (output / "notes.txt").read_text() == "local edits\n"
    assert "There were 0 merge conflicts" in capsys.readouterr().out

    # Another update must keep the adopted seed and all previously generated IDs.
    (template / "another.txt").write_text("uuid[new] uuid[another]")
    git(template, "add", ".")
    git(template, "commit", "-m", "Add another UUID")
    update_template.main(["-d", str(output)])
    assert toml.load(settings_path)["uuid_seed"] == updated_seed
    assert (output / "another.txt").read_text().split()[0] == values[1]
    assert "There were 0 merge conflicts" in capsys.readouterr().out

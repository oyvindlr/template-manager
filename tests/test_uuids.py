import subprocess
import uuid

import pytest
import toml

from template_manager import project_from_template, update_template
from template_manager.cookiecutter import convert_template


@pytest.fixture(params=["legacy", "cookiecutter"])
def template_text(request):
    return convert_template if request.param == "cookiecutter" else lambda text: text


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


def test_named_uuids_are_shared_across_paths_and_contents(tmp_path, template_text):
    template = tmp_path / "template"
    folder = template / template_text("%uuid(folder)%")
    folder.mkdir(parents=True)
    (folder / template_text("%uuid(item)%.txt")).write_text(template_text(
        "%uuid(item)% %uuid(item)% %uuid(folder)% %uuid(other)%"
    ))
    (template / "reference.txt").write_text(template_text("%uuid(item)%"))
    binary = b"\xff %uuid(item)%"
    (template / "binary.dat").write_bytes(binary)

    output = generate(template, tmp_path / "output")

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


def test_seed_is_random_per_project_and_reused_for_recreation(tmp_path, template_text):
    template = tmp_path / "template"
    template.mkdir()
    (template / "id.txt").write_text(template_text("%uuid(item)%"))
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


def test_explicit_seed_has_stable_uuid5_values(tmp_path, template_text):
    template = tmp_path / "template"
    template.mkdir()
    (template / "id.txt").write_text(template_text("%uuid(item)% uuid[] uuid[unfinished"))

    output = generate(template, tmp_path / "output", "--uuid-seed", "my seed")

    expected = uuid.uuid5(uuid.uuid5(uuid.NAMESPACE_URL, "my seed"), "item")
    assert (output / "id.txt").read_text() == f"{expected} uuid[] uuid[unfinished"
    assert toml.load(output / ".template_settings.toml")["uuid_seed"] == "my seed"


def test_legacy_uuid_escaping_and_literal_text(tmp_path):
    template = tmp_path / "template"
    template.mkdir()
    (template / "^%uuid(item)^%.txt").write_text(
        r"\%uuid(item)\% uuid(item) uuid[item] %uuid(item)% %message%"
    )
    output = generate(template, tmp_path / "output", "--variables", "message:uuid[item]")
    content = (output / "%uuid(item)%.txt").read_text()
    literal, generated, variable = content.rsplit(" ", 2)
    assert literal == "%uuid(item)% uuid(item) uuid[item]"
    assert uuid.UUID(generated).version == 5
    assert variable == "uuid[item]"


def test_jinja_uuid_calls_filters_and_raw_blocks(tmp_path):
    template = tmp_path / "template"
    template.mkdir()
    (template / "result.txt").write_text(
        "{{ cookiecutter.uuid('item')|upper }}\n"
        '{{ uuid("item") }}\n'
        "{% raw %}{{ cookiecutter.uuid('item') }}{% endraw %}\n"
        "uuid(item) uuid[item] %uuid(item)%\n"
        "{% if missing %}{{ cookiecutter.uuid('') }}{% endif %}"
    )
    output = generate(template, tmp_path / "output")
    lines = (output / "result.txt").read_text().splitlines()
    assert lines[0] == lines[1].upper()
    assert uuid.UUID(lines[1]).version == 5
    assert lines[2] == "{{ cookiecutter.uuid('item') }}"
    assert lines[3] == "uuid(item) uuid[item] %uuid(item)%"


@pytest.mark.parametrize("argument", ["''", "42", "missing"])
def test_jinja_rejects_invalid_uuid_names(tmp_path, capsys, argument):
    template = tmp_path / "template"
    template.mkdir()
    (template / "result.txt").write_text("{{ cookiecutter.uuid(" + argument + ") }}")
    with pytest.raises(SystemExit) as error:
        generate(template, tmp_path / "output")
    assert error.value.code == 1
    assert "UUID names must be nonempty strings" in capsys.readouterr().out


def test_conversion_preserves_uuid_names_and_values(tmp_path):
    source = '%uuid(main)% %uuid(quote"name)% %uuid(æøå)%'
    converted = convert_template(source)
    assert convert_template("%uuid(main)%") == "{{ cookiecutter.uuid('main') }}"
    assert convert_template("%uuid(main)%", namespace="") == "{{ uuid('main') }}"
    template = tmp_path / "template"
    template.mkdir()
    (template / "ids.txt").write_text(source)
    first = generate(template, tmp_path / "first", "--uuid-seed", "same seed")
    (template / "ids.txt").write_text(converted)
    second = generate(template, tmp_path / "second", "--uuid-seed", "same seed")
    assert (first / "ids.txt").read_text() == (second / "ids.txt").read_text()


def git(repo, *args):
    return subprocess.run([
        "git", "-C", str(repo), "-c", "user.name=Test",
        "-c", "user.email=test@example.com", *args,
    ], check=True, capture_output=True, text=True).stdout.strip()


@pytest.mark.parametrize("legacy", [False, True])
def test_update_preserves_seed_and_existing_uuids(tmp_path, capsys, legacy, template_text):
    template = tmp_path / "template"
    template.mkdir()
    git(template, "init")
    initial = "initial\n" if legacy else template_text("%uuid(item)%\n")
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

    (template / "id.txt").write_text(initial + template_text("%uuid(new)%\n"))
    (template / "reference.txt").write_text(template_text("%uuid(new)%\n"))
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
    (template / "another.txt").write_text(template_text("%uuid(new)% %uuid(another)%"))
    git(template, "add", ".")
    git(template, "commit", "-m", "Add another UUID")
    update_template.main(["-d", str(output)])
    assert toml.load(settings_path)["uuid_seed"] == updated_seed
    assert (output / "another.txt").read_text().split()[0] == values[1]
    assert "There were 0 merge conflicts" in capsys.readouterr().out

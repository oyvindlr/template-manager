"""Install the bundled reverse-sync review skill for use outside this repository."""

import argparse
from importlib.resources import files
import os
from pathlib import Path
import tempfile

from platformdirs import user_config_dir


SKILL_NAME = "reverse-sync-review"


def install_skill(destination=None, *, force=False):
    """Copy the skill into a skills directory, preserving edited copies by default."""
    if destination is None:
        destination = Path(user_config_dir("template-manager")) / "skills"
    target = Path(destination).expanduser() / SKILL_NAME / "SKILL.md"
    content = files("template_manager").joinpath("skills", SKILL_NAME, "SKILL.md").read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() == content:
            return target.resolve()
        if not force:
            raise FileExistsError(f"{target} already exists with different contents; use --force to replace it")

    if force:
        # Replace the file atomically, including when the old path is a symlink.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    else:
        with target.open("xb") as stream:
            stream.write(content)
    return target.resolve()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Install the bundled reverse-sync-review agent skill."
    )
    parser.add_argument(
        "--destination", type=Path,
        help="Skills directory (default: skills/ beside template-manager's global settings.toml). "
             "Use ~/.agents/skills for personal agent discovery or .agents/skills for a project.",
    )
    parser.add_argument("--force", action="store_true", help="Replace an existing edited skill")
    args = parser.parse_args(argv)
    try:
        target = install_skill(args.destination, force=args.force)
    except OSError as error:
        parser.error(str(error))
    print(f"Skill installed at {target}")
    if args.destination is None:
        print("For agent discovery, also run: template-install-skill --destination ~/.agents/skills")


def entry_point():
    main()


if __name__ == "__main__":
    entry_point()

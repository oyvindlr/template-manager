"""Install the bundled reverse-sync review skill for use outside this repository."""

import argparse
from importlib.resources import files
import os
from pathlib import Path
import shutil
import sys
import tempfile


SKILL_NAME = "reverse-sync-review"


def detected_agents():
    """Find local clients without launching them or reading their credentials."""
    home = Path.home()
    extensions = [home / folder / "extensions" for folder in (
        ".vscode", ".vscode-insiders", ".vscode-server", ".vscode-server-insiders",
    )]
    clients = (
        ("Claude Code", "claude", "CLAUDE_CONFIG_DIR", ".claude", "anthropic.claude-code"),
        ("Codex", "codex", "CODEX_HOME", ".codex", "openai.chatgpt"),
        ("GitHub Copilot", "copilot", "COPILOT_HOME", ".copilot", "github.copilot"),
    )
    destinations = []
    for name, command, variable, folder, extension in clients:
        config = Path(os.environ.get(variable) or home / folder).expanduser()
        prefixes = (extension, "github.copilot-chat") if command == "copilot" else (extension,)
        has_extension = any(
            path.is_dir()
            for root in extensions for prefix in prefixes for path in root.glob(f"{prefix}-*")
        )
        if shutil.which(command) or config.is_dir() or has_extension:
            # Codex's current personal skill directory is shared across agents;
            # CODEX_HOME selects its configuration, not that skills directory.
            skills = home / ".agents" / "skills" if command == "codex" else config / "skills"
            destinations.append((name, skills))
    return destinations


def install_skill(destination, *, force=False):
    """Copy the skill into a skills directory, preserving edited copies by default."""
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
        description="Install the bundled reverse-sync-review skill for detected Claude Code, "
                    "Codex, and GitHub Copilot clients."
    )
    parser.add_argument(
        "--destination", type=Path,
        help="Install only into this skills directory instead of detecting clients "
             "(for example, .agents/skills for a project).",
    )
    parser.add_argument("--force", action="store_true", help="Replace an existing edited skill")
    args = parser.parse_args(argv)
    destinations = [("Custom", args.destination)] if args.destination is not None else detected_agents()
    if not destinations:
        parser.error("No Claude Code, Codex, or GitHub Copilot installation detected. "
                     "Use --destination PATH to specify a skills directory.")
    failed = False
    for name, destination in destinations:
        try:
            target = install_skill(destination, force=args.force)
        except OSError as error:
            print(f"{name}: {error}", file=sys.stderr)
            failed = True
        else:
            print(f"{name}: Skill installed at {target}")
    if failed:
        parser.exit(1)


def entry_point():
    main()


if __name__ == "__main__":
    entry_point()

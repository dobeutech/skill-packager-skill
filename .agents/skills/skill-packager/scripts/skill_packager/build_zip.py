"""Build cross-platform zip with path hygiene."""
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from .path_hygiene import (
    PACKAGE_IGNORE,
    clean_text,
    path_use_lines,
    substitution_applies,
    unquoted_skill_dir_lines,
    unstrippable_lines,
    unsubstituted_path_lines,
)


def _strip_claude_skill_dir(directory):
    """Strip ${CLAUDE_SKILL_DIR}/ path uses from all .md files in directory."""
    root = Path(directory)
    for md_file in root.rglob("*.md"):
        # The token means "relative to the skill root" only where Claude Code
        # substitutes it. Stripping anywhere else rebases the path wrongly.
        if not substitution_applies(md_file.relative_to(root)):
            continue
        content = md_file.read_text(encoding="utf-8")
        cleaned = clean_text(content)
        if cleaned != content:
            md_file.write_text(cleaned, encoding="utf-8")


def _verify_no_claude_skill_dir(directory):
    """Verify no ${CLAUDE_SKILL_DIR} path use remains in any .md file.

    Occurrences that merely *document* the token are expected to survive; only
    a use as a path prefix would break on a host that cannot expand it.
    """
    root = Path(directory)
    for md_file in root.rglob("*.md"):
        rel = md_file.relative_to(root)
        text = md_file.read_text(encoding="utf-8")
        dead = unsubstituted_path_lines(text, rel)
        if dead:
            raise ValueError(
                f"${{CLAUDE_SKILL_DIR}} used as a path in {md_file} "
                f"(line{'s' if len(dead) > 1 else ''} {', '.join(map(str, dead))}). "
                "Claude Code substitutes the token only in the SKILL.md body; a "
                "reference file is read from disk, so the token stays literal and "
                "the read fails. Stripping cannot fix it either — the result would "
                "be relative to the skill root, not to this file. Use a path "
                "relative to this file, or mark the file with "
                "<!-- skill-packager:no-path-strip --> if it documents the token."
            )
        lines = path_use_lines(text)
        if lines:
            raise ValueError(
                f"${{CLAUDE_SKILL_DIR}} still used as a path in {md_file} "
                f"(line{'s' if len(lines) > 1 else ''} {', '.join(map(str, lines))})"
            )
        fenced = unstrippable_lines(text)
        if fenced:
            raise ValueError(
                f"${{CLAUDE_SKILL_DIR}} used inside a command block in {md_file} "
                f"(line{'s' if len(fenced) > 1 else ''} "
                f"{', '.join(map(str, fenced))}). No relative rewrite is "
                "correct: the path depends on the shell's working directory "
                "at run time. Resolve the skill directory once and pass an "
                "absolute path instead."
            )
        unquoted = unquoted_skill_dir_lines(text)
        if unquoted:
            raise ValueError(
                f"unquoted $SKILL_DIR in a command block in {md_file} "
                f"(line{'s' if len(unquoted) > 1 else ''} "
                f"{', '.join(map(str, unquoted))}). Quote it: an unset value "
                "word-splits to a bare `cd`, which succeeds into $HOME and lets "
                "an && chain continue. `cd \"$SKILL_DIR/scripts\"` fails loudly "
                "instead."
            )


def build_zip(skill_dir, output_path, version=None):
    """Build a zip from a skill directory with path hygiene.

    Single skill: skill_dir contains SKILL.md -> <skill-name>/ at archive root
    Multi-skill: skill_dir contains subdirectories with SKILL.md -> skills/ at archive root
    """
    skill_dir = Path(skill_dir).resolve()
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    is_single = (skill_dir / "SKILL.md").exists()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        if is_single:
            skill_name = skill_dir.name
            dest = tmp_path / skill_name
            shutil.copytree(skill_dir, dest, ignore=PACKAGE_IGNORE)
            _strip_claude_skill_dir(dest)
            if version:
                (dest / "VERSION").write_text(version)
            _verify_no_claude_skill_dir(dest)
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(dest):
                    for f in files:
                        file_path = Path(root) / f
                        arcname = str(file_path.relative_to(tmp_path))
                        zf.write(file_path, arcname)
        else:
            dest = tmp_path / "skills"
            dest.mkdir()
            for sub in skill_dir.iterdir():
                if sub.is_dir() and (sub / "SKILL.md").exists():
                    skill_dest = dest / sub.name
                    shutil.copytree(sub, skill_dest, ignore=PACKAGE_IGNORE)
                    _strip_claude_skill_dir(skill_dest)
                    if version:
                        (skill_dest / "VERSION").write_text(version)
            _verify_no_claude_skill_dir(dest)
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(dest):
                    for f in files:
                        file_path = Path(root) / f
                        arcname = str(file_path.relative_to(tmp_path))
                        zf.write(file_path, arcname)


def run_build_zip(args):
    """CLI entry point for 'build-zip' subcommand."""
    build_zip(args.skill_dir, args.output, version=args.version)
    print(f"Built zip: {args.output}")

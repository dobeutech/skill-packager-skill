#!/usr/bin/env python3
"""Build a distributable zip from a skill-packager generated repo.

Usage:
    python3 tools/build-zip.py [--version VERSION] [--output PATH]

Reads skill-packager.json (or legacy meta.json) from the repo root (parent
of tools/) to discover skill layout.  Copies skill directories, strips
``${CLAUDE_SKILL_DIR}/`` path prefixes outside code fences (a use inside a
fence is an error), writes VERSION, and creates a
zip archive.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile


SKILL_DIR_VAR = "${CLAUDE_SKILL_DIR}/"
NO_STRIP_MARKER = "<!-- skill-packager:no-path-strip -->"
# A source skill is a working directory; a distributed one is not.
PACKAGE_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.pyo", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".DS_Store",
)

# Strip the token only where it prefixes a path. A slash before whitespace or a
# closing delimiter is prose, and a preceding backslash is shell/sed escaping;
# deleting those corrupts documentation *about* the token.
PATH_USE_RE = re.compile(r"(?<!\\)\$\{CLAUDE_SKILL_DIR\}/(?=[^\s\x60\x27\x22)\],;|])")
# Inside a fenced code block nothing is stripped and any occurrence is an
# error: a command's correct path depends on the shell's working directory
# at run time, which cannot be known at build time. "cd ${CLAUDE_SKILL_DIR}"
# becomes a bare "cd" ($HOME); "cd ${CLAUDE_SKILL_DIR}/scripts" stripped to
# "cd scripts" runs a different project's scripts/ when one exists there.
ANY_USE_RE = re.compile(r"(?<!\\)\$\{CLAUDE_SKILL_DIR\}")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
# Quoting is load-bearing: `cd $SKILL_DIR` word-splits to a bare `cd` when
# unset (exit 0, $HOME, && chain continues); `cd "$SKILL_DIR"` fails loudly.
SKILL_DIR_RE = re.compile(r"\$\{?SKILL_DIR\}?")


def _unquoted(line):
    starts = {m.start() for m in SKILL_DIR_RE.finditer(line)}
    if not starts:
        return False
    in_s = in_d = esc = False
    for i, ch in enumerate(line):
        if i in starts and not in_s and not in_d:
            return True
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
        elif ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
    return False


def _fenced_flags(lines):
    inside = False
    for line in lines:
        if FENCE_RE.match(line):
            inside = not inside
            yield False
        else:
            yield inside
NEW_MANIFEST = "skill-packager.json"
LEGACY_MANIFEST = "meta.json"


def _find_meta(repo_dir):
    new = os.path.join(repo_dir, NEW_MANIFEST)
    if os.path.isfile(new):
        return new, False
    legacy = os.path.join(repo_dir, LEGACY_MANIFEST)
    if os.path.isfile(legacy):
        return legacy, True
    return None, False



def _strip_skill_dir(text):
    # Strip path prefixes outside fences; fenced lines are _verify's job.
    if NO_STRIP_MARKER in text:
        return text
    lines = text.split("\n")
    return "\n".join(
        line if fenced else PATH_USE_RE.sub("", line)
        for line, fenced in zip(lines, _fenced_flags(lines))
    )


def _copy_and_strip(src, dst):
    """Recursively copy *src* to *dst*, stripping CLAUDE_SKILL_DIR path prefixes"""
    shutil.copytree(src, dst, ignore=PACKAGE_IGNORE)
    for root, _dirs, files in os.walk(dst):
        for fname in files:
            if fname.endswith(".md"):
                fpath = os.path.join(root, fname)
                with open(fpath, "r", encoding="utf-8") as fh:
                    text = fh.read()
                cleaned = _strip_skill_dir(text)
                if cleaned != text:
                    with open(fpath, "w", encoding="utf-8") as fh:
                        fh.write(cleaned)


def _verify_no_skill_dir(directory):
    for root, _dirs, files in os.walk(directory):
        for fname in files:
            if fname.endswith(".md"):
                fpath = os.path.join(root, fname)
                with open(fpath, "r", encoding="utf-8") as fh:
                    text = fh.read()
                if NO_STRIP_MARKER in text:
                    continue
                if PATH_USE_RE.search(text):
                    print("ERROR: residual CLAUDE_SKILL_DIR path use in", fpath,
                          file=sys.stderr)
                    sys.exit(1)
                lines_ = text.split("\n")
                for num, (line, fenced) in enumerate(
                        zip(lines_, _fenced_flags(lines_)), 1):
                    if fenced and ANY_USE_RE.search(line):
                        print("ERROR: CLAUDE_SKILL_DIR in a command block in",
                              "%s:%d" % (fpath, num),
                              "- no relative rewrite is correct, because the",
                              "path depends on the shell's working directory",
                              "at run time. Resolve the skill directory once",
                              "and pass an absolute path.",
                              file=sys.stderr)
                        sys.exit(1)
                    if fenced and _unquoted(line):
                        print("ERROR: unquoted $SKILL_DIR in a command block in",
                              "%s:%d" % (fpath, num),
                              "- an unset value word-splits to a bare cd, which",
                              "succeeds into $HOME. Quote it.",
                              file=sys.stderr)
                        sys.exit(1)


def _zip_directory(source_dir, zip_path, arc_prefix):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(source_dir):
            for fname in files:
                fpath = os.path.join(root, fname)
                arcname = os.path.join(arc_prefix, os.path.relpath(fpath, source_dir))
                zf.write(fpath, arcname)


def main():
    parser = argparse.ArgumentParser(description="Build skill zip archive")
    parser.add_argument("--version", default=None, help="Version to stamp")
    parser.add_argument("--output", default=None, help="Output zip path")
    args = parser.parse_args()

    # Locate repo root (parent of tools/)
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    meta_path, is_legacy = _find_meta(repo)
    if meta_path is None:
        print("Error: skill-packager.json (or legacy meta.json) not found at", repo, file=sys.stderr)
        sys.exit(1)
    if is_legacy:
        print("[deprecation] using legacy meta.json - rename to skill-packager.json in a future release", file=sys.stderr)

    with open(meta_path, "r", encoding="utf-8") as fh:
        meta = json.load(fh)

    plugin_name = meta["plugin_name"]
    github_repo = meta.get("github_repo", plugin_name)
    skills = meta.get("skills", [])
    version = args.version or meta.get("version", "0.0.0")

    # The artifact name is what release.yml uploads and what the README links
    # to, so it must be explicit rather than derived. A mismatch attaches
    # nothing to the release and 404s every download link, silently.
    zip_rel = meta.get("zip_filename") or os.path.join("dist", plugin_name + ".zip")
    output = args.output or os.path.join(repo, zip_rel)
    os.makedirs(os.path.dirname(output), exist_ok=True)

    skill_names = [
        s if isinstance(s, str) else s.get("name", "")
        for s in skills
    ]
    if not skill_names:
        print("Error: no skills found in skill-packager.json (or legacy meta.json)", file=sys.stderr)
        sys.exit(1)

    tmpdir = tempfile.mkdtemp(prefix="skill-zip-")
    try:
        multi = len(skill_names) > 1

        for sname in skill_names:
            src = os.path.join(repo, plugin_name, "skills", sname)
            if multi:
                dst = os.path.join(tmpdir, "skills", sname)
            else:
                dst = os.path.join(tmpdir, sname)

            _copy_and_strip(src, dst)

            # Write VERSION into each skill dir
            with open(os.path.join(dst, "VERSION"), "w", encoding="utf-8") as fh:
                fh.write(version + "\n")

        _verify_no_skill_dir(tmpdir)

        if multi:
            arc_prefix = "skills"
            zip_src = os.path.join(tmpdir, "skills")
        else:
            arc_prefix = skill_names[0]
            zip_src = os.path.join(tmpdir, skill_names[0])

        _zip_directory(zip_src, output, arc_prefix)
        print("Created", output)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()

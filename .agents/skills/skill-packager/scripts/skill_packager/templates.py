"""File templates for generated skill-packager repos.

Each constant is a Python format-string. Call ``TEMPLATE.format(**vars)``
where *vars* is a dict with keys such as ``skill_name``, ``plugin_name``,
``version``, etc.  Literal braces that must appear in the output are doubled.

Templates that embed Python scripts use ``__FIND_META_HELPER__`` as a sentinel
that is replaced AFTER ``.format()`` to inject the ``_find_meta()`` helper
without doubling every brace in it.
"""

# ---------------------------------------------------------------------------
# Sentinel helper — injected into BUMP_VERSION_PY and BUILD_ZIP_PY
# ---------------------------------------------------------------------------

_FIND_META_HELPER = '''\
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
'''

# ---------------------------------------------------------------------------
# 1. Claude plugin – inner manifest
# ---------------------------------------------------------------------------

CLAUDE_PLUGIN_JSON = """\
{{
  "name": "{plugin_name}",
  "version": "{version}",
  "description": "{skill_description}",
  "author": {{
    "name": "{author_name}",
    "email": "{author_email}"
  }},
  "homepage": "{homepage}",
  "repository": "{repo_url}",
  "license": "{license}",
  "keywords": {keywords_json},
  "skills": "./skills"
}}
"""

# ---------------------------------------------------------------------------
# 2. Claude marketplace – root wrapper
# ---------------------------------------------------------------------------

MARKETPLACE_JSON = """\
{{
  "name": "{marketplace_name}",
  "owner": {{
    "name": "{author_name}",
    "email": "{author_email}"
  }},
  "metadata": {{
    "description": "{skill_description}",
    "version": "{version}"
  }},
  "plugins": [
    {{
      "name": "{plugin_name}",
      "source": "./{plugin_name}",
      "description": "{skill_description}",
      "author": {{
        "name": "{author_name}",
        "email": "{author_email}"
      }},
      "category": "{category}",
      "tags": {keywords_json}
    }}
  ]
}}
"""

# ---------------------------------------------------------------------------
# 2b. Codex (ChatGPT) native marketplace – .agents/plugins/marketplace.json
# ---------------------------------------------------------------------------
# source.path resolves against the marketplace root ($REPO_ROOT), so
# "./{plugin_name}" targets the plugin subdir holding both manifests + skills/.
# Verified live against codex-cli 0.144.4.

CODEX_MARKETPLACE_JSON = """\
{{
  "name": "{marketplace_name}",
  "interface": {{
    "displayName": "{display_name}"
  }},
  "plugins": [
    {{
      "name": "{plugin_name}",
      "source": {{
        "source": "git-subdir",
        "url": "{repo_url}.git",
        "path": "./{plugin_name}",
        "ref": "main"
      }},
      "policy": {{
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      }},
      "category": "{category}"
    }}
  ]
}}
"""

# ---------------------------------------------------------------------------
# 3. Cursor plugin manifest
# ---------------------------------------------------------------------------

CURSOR_PLUGIN_JSON = """\
{{
  "name": "{plugin_name}",
  "displayName": "{display_name}",
  "version": "{version}",
  "description": "{skill_description}",
  "author": {{
    "name": "{author_name}",
    "email": "{author_email}"
  }},
  "license": "{license}",
  "keywords": {keywords_json},
  "skills": "./{plugin_name}/skills"
}}
"""

# ---------------------------------------------------------------------------
# 4. GitHub Actions release workflow
# ---------------------------------------------------------------------------

RELEASE_YML = """\
name: Release

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.x'

      - name: Extract version from tag
        id: version
        run: echo "version=${{GITHUB_REF#refs/tags/v}}" >> "$GITHUB_OUTPUT"

      - name: Build generic zip
        run: |
          VERSION="${{{{ steps.version.outputs.version }}}}"
          python3 tools/build-zip.py --version "$VERSION"

      - name: Extract release notes from CHANGELOG.md
        id: changelog
        run: |
          VERSION="${{{{ steps.version.outputs.version }}}}"
          NOTES=$(awk "/^## \\[${{VERSION}}\\]/{{found=1; next}} /^## \\[/{{if(found) exit}} found{{print}}" CHANGELOG.md)
          echo "$NOTES" > release-notes.md

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v3
        with:
          body_path: release-notes.md
          files: |
            {zip_filename}
"""

# ---------------------------------------------------------------------------
# 5. GitHub Pages deploy workflow
# ---------------------------------------------------------------------------

DEPLOY_PAGES_YML = """\
name: Deploy Pages

on:
  push:
    branches: [main]

permissions:
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{{{ steps.deployment.outputs.page_url }}}}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - name: Build site
        run: |
          mkdir -p _site/static
          cp static/install-claude-desktop.html _site/static/
          cat > _site/index.html <<'HTML'
          <!DOCTYPE html>
          <meta charset="utf-8">
          <title>{display_name}</title>
          <meta http-equiv="refresh" content="0; url=./static/install-claude-desktop.html">
          <link rel="canonical" href="./static/install-claude-desktop.html">
          <p><a href="./static/install-claude-desktop.html">Install {display_name} in Claude Desktop</a></p>
          HTML

      - uses: actions/upload-pages-artifact@v5
        with:
          name: github-pages

      - id: deployment
        uses: actions/deploy-pages@v5
        with:
          artifact_name: github-pages
"""

# ---------------------------------------------------------------------------
# 6. Claude Desktop one-click install page
# ---------------------------------------------------------------------------

INSTALL_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Install {display_name} in Claude Desktop</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background: #f9f5f1; color: #3d3929; }}
.card {{ text-align: center; padding: 3rem; max-width: 480px; }}
h1 {{ font-size: 1.4rem; margin-bottom: 1rem; }}
p {{ color: #6b5e4f; line-height: 1.6; }}
a {{ color: #d97757; text-decoration: none; font-weight: 600; }}
a:hover {{ text-decoration: underline; }}
.fallback {{ display: none; }}
</style>
</head>
<body>
<div class="card">
<h1>Installing {display_name}</h1>
<p id="status">Opening Claude Desktop...</p>
<div id="fallback" class="fallback">
<p>Claude Desktop didn't open. You can:</p>
<p><a href="claude://claude.ai/customize/plugins/new?marketplace=https://github.com/{github_owner}/{github_repo}&plugin={plugin_name}">Try again</a></p>
<p>Or install manually: open Claude Desktop, click <strong>Customize</strong>, then <strong>Browse Plugins</strong>, add marketplace <code>{github_owner}/{github_repo}</code>.</p>
</div>
<p><a href="https://github.com/{github_owner}/{github_repo}">Back to {display_name} on GitHub</a></p>
</div>
<script>
var deepLink = "claude://claude.ai/customize/plugins/new?marketplace=https://github.com/{github_owner}/{github_repo}&plugin={plugin_name}";
var repo = "https://github.com/{github_owner}/{github_repo}";

// Try opening the deep link
window.location = deepLink;

// If the page is still visible after 5s, the deep link likely didn't work
setTimeout(function() {{
  if (!document.hidden) {{
    document.getElementById("status").textContent = "";
    document.getElementById("fallback").style.display = "block";
  }}
}}, 5000);

// If the user comes back to this tab (Claude opened then they switched back), redirect to repo
document.addEventListener("visibilitychange", function() {{
  if (!document.hidden) {{
    setTimeout(function() {{ window.location = repo; }}, 500);
  }}
}});
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# 7. VERSIONING.md
# ---------------------------------------------------------------------------

VERSIONING_MD = """\
# Versioning

This project uses [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`).

## Version Source of Truth

The canonical version lives in `skill-packager.json` (and the root `VERSION` file) at the repo root. All other version locations are updated from it.

## Version Locations

The version appears in these files (all managed by the bump script):

1. `skill-packager.json` — source of truth
2. `VERSION` — plain-text copy at repo root
3. `{plugin_name}/.claude-plugin/plugin.json` — `"version"` field
4. `.claude-plugin/marketplace.json` — `metadata.version` (if marketplace format enabled)
5. `.cursor-plugin/plugin.json` — `"version"` field (if Cursor format enabled)
6. `{plugin_name}/.codex-plugin/plugin.json` — `"version"` field (if Codex format enabled)
7. `{plugin_name}/skills/*/SKILL.md` — `metadata.version` in YAML frontmatter
8. `{plugin_name}/skills/*/VERSION` — copied from root
9. `.agents/skills/` copies (if they exist)

## Bumping the Version

```bash
# Set a new version and propagate to all locations:
python3 tools/bump-version.py . 0.2.0

# Or from the repo root with current directory:
python3 tools/bump-version.py . 0.2.0
```

## Release Process

```bash
# 1. Bump version
python3 tools/bump-version.py . X.Y.Z
# 2. Update CHANGELOG.md with release notes
# 3. Commit
git commit -am "chore: bump version to X.Y.Z"
# 4. Tag and push
git tag vX.Y.Z
git push origin main --tags
```

CI automatically creates a GitHub Release with a zip for all platforms.
"""

# ---------------------------------------------------------------------------
# 8. MIT License
# ---------------------------------------------------------------------------

LICENSE_MIT = """\
MIT License

Copyright (c) {year} {author_name}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

# ---------------------------------------------------------------------------
# 9. bump-version.py — standalone version bumper for generated repos
# ---------------------------------------------------------------------------

BUMP_VERSION_PY = """\
#!/usr/bin/env python3
\"\"\"Propagate a version string to every location in the repo.

Usage:
    python3 tools/bump-version.py REPO_DIR VERSION

Reads skill-packager.json (or legacy meta.json) from REPO_DIR to discover
the plugin name, skill names, and enabled formats, then updates every file
that contains a version.
\"\"\"
import json
import os
import re
import sys


__FIND_META_HELPER__

def _update_json_version(path, key_path, version):
    \"\"\"Set a nested key in a JSON file.  *key_path* is a dot-separated string.\"\"\"
    if not os.path.isfile(path):
        return False
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    keys = key_path.split(".")
    obj = data
    for k in keys[:-1]:
        obj = obj[k]
    obj[keys[-1]] = version
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\\n")
    return True


def _update_skill_md_version(path, version):
    \"\"\"Replace ``version: "X.Y.Z"`` in a SKILL.md metadata block.\"\"\"
    if not os.path.isfile(path):
        return False
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    new_text = re.sub(r'version:\\s*"[^"]*"', 'version: "' + version + '"', text)
    if new_text == text:
        new_text = re.sub(r"version:\\s*[0-9][^\\n]*", "version: " + version, text)
    if new_text != text:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new_text)
        return True
    return False


def _write_version_file(path, version):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(version + "\\n")
    return True


def main():
    if len(sys.argv) < 3:
        print("Usage: bump-version.py REPO_DIR VERSION", file=sys.stderr)
        sys.exit(1)

    repo = os.path.abspath(sys.argv[1])
    version = sys.argv[2]

    meta_path, is_legacy = _find_meta(repo)
    if meta_path is None:
        print("Error: skill-packager.json (or legacy meta.json) not found at", repo, file=sys.stderr)
        sys.exit(1)
    if is_legacy:
        print("[deprecation] using legacy meta.json - rename to skill-packager.json in a future release", file=sys.stderr)

    with open(meta_path, "r", encoding="utf-8") as fh:
        meta = json.load(fh)

    plugin_name = meta["plugin_name"]
    skills = meta.get("skills", [])
    formats = meta.get("formats", [])

    updated = []

    # 1. skill-packager.json / meta.json version
    if _update_json_version(meta_path, "version", version):
        updated.append(os.path.basename(meta_path))

    # 2. Root VERSION file
    _write_version_file(os.path.join(repo, "VERSION"), version)
    updated.append("VERSION")

    # 3. Inner claude plugin.json
    inner_pj = os.path.join(repo, plugin_name, ".claude-plugin", "plugin.json")
    if _update_json_version(inner_pj, "version", version):
        updated.append(inner_pj)

    # 4. Marketplace metadata.version (if exists)
    mktp = os.path.join(repo, ".claude-plugin", "marketplace.json")
    if _update_json_version(mktp, "metadata.version", version):
        updated.append(mktp)

    # 5. Cursor plugin.json (if exists)
    cursor_pj = os.path.join(repo, ".cursor-plugin", "plugin.json")
    if _update_json_version(cursor_pj, "version", version):
        updated.append(cursor_pj)

    # 5b. Codex plugin.json (if exists)
    codex_pj = os.path.join(repo, plugin_name, ".codex-plugin", "plugin.json")
    if _update_json_version(codex_pj, "version", version):
        updated.append(codex_pj)

    # 6 & 7. Each skill's SKILL.md and VERSION
    for skill in skills:
        sname = skill if isinstance(skill, str) else skill.get("name", "")
        skill_dir = os.path.join(repo, plugin_name, "skills", sname)

        md_path = os.path.join(skill_dir, "SKILL.md")
        if _update_skill_md_version(md_path, version):
            updated.append(md_path)

        ver_path = os.path.join(skill_dir, "VERSION")
        if os.path.isdir(skill_dir):
            _write_version_file(ver_path, version)
            updated.append(ver_path)

    # 8. .agents/skills/ copies. The scaffold always writes real copies; the
    #    islink guard below is for a hand-made symlink, where writing VERSION
    #    would write through to the canonical copy a second time.
    agents_skills = os.path.join(repo, ".agents", "skills")
    if os.path.isdir(agents_skills):
        for sname_entry in os.listdir(agents_skills):
            entry = os.path.join(agents_skills, sname_entry)
            if os.path.isdir(entry) and not os.path.islink(entry):
                ver_path = os.path.join(entry, "VERSION")
                _write_version_file(ver_path, version)
                updated.append(ver_path)
                md_path = os.path.join(entry, "SKILL.md")
                if _update_skill_md_version(md_path, version):
                    updated.append(md_path)

    print("Bumped to version:", version)
    for u in updated:
        print("  updated:", u)


if __name__ == "__main__":
    main()
"""

# ---------------------------------------------------------------------------
# 10. build-zip.py — standalone zip builder for generated repos
# ---------------------------------------------------------------------------

BUILD_ZIP_PY = """\
#!/usr/bin/env python3
\"\"\"Build a distributable zip from a skill-packager generated repo.

Usage:
    python3 tools/build-zip.py [--version VERSION] [--output PATH]

Reads skill-packager.json (or legacy meta.json) from the repo root (parent
of tools/) to discover skill layout.  Copies skill directories, strips
``${{CLAUDE_SKILL_DIR}}/`` path prefixes outside code fences (a use inside a
fence is an error), writes VERSION, and creates a
zip archive.
\"\"\"
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile


SKILL_DIR_VAR = "${{CLAUDE_SKILL_DIR}}/"
NO_STRIP_MARKER = "<!-- skill-packager:no-path-strip -->"
# A source skill is a working directory; a distributed one is not.
PACKAGE_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.pyo", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".DS_Store",
)

# Strip the token only where it prefixes a path. A slash before whitespace or a
# closing delimiter is prose, and a preceding backslash is shell/sed escaping;
# deleting those corrupts documentation *about* the token.
PATH_USE_RE = re.compile(r"(?<!\\\\)\\$\\{{CLAUDE_SKILL_DIR\\}}/(?=[^\\s\\x60\\x27\\x22)\\],;|])")
# Inside a fenced code block nothing is stripped and any occurrence is an
# error: a command's correct path depends on the shell's working directory
# at run time, which cannot be known at build time. "cd ${{CLAUDE_SKILL_DIR}}"
# becomes a bare "cd" ($HOME); "cd ${{CLAUDE_SKILL_DIR}}/scripts" stripped to
# "cd scripts" runs a different project's scripts/ when one exists there.
ANY_USE_RE = re.compile(r"(?<!\\\\)\\$\\{{CLAUDE_SKILL_DIR\\}}")
FENCE_RE = re.compile(r"^\\s*(```|~~~)")
# Quoting is load-bearing: `cd $SKILL_DIR` word-splits to a bare `cd` when
# unset (exit 0, $HOME, && chain continues); `cd "$SKILL_DIR"` fails loudly.
SKILL_DIR_RE = re.compile(r"\\$\\{{?SKILL_DIR\\}}?")


def _unquoted(line):
    starts = {{m.start() for m in SKILL_DIR_RE.finditer(line)}}
    if not starts:
        return False
    in_s = in_d = esc = False
    for i, ch in enumerate(line):
        if i in starts and not in_s and not in_d:
            return True
        if esc:
            esc = False
            continue
        if ch == "\\\\":
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
__FIND_META_HELPER__


def _strip_skill_dir(text):
    # Strip path prefixes outside fences; fenced lines are _verify's job.
    if NO_STRIP_MARKER in text:
        return text
    lines = text.split("\\n")
    return "\\n".join(
        line if fenced else PATH_USE_RE.sub("", line)
        for line, fenced in zip(lines, _fenced_flags(lines))
    )


def _copy_and_strip(src, dst):
    \"\"\"Recursively copy *src* to *dst*, stripping CLAUDE_SKILL_DIR path prefixes\"\"\"
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
                lines_ = text.split("\\n")
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
                fh.write(version + "\\n")

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
"""

# ---------------------------------------------------------------------------
# 11. README stub
# ---------------------------------------------------------------------------

README_STUB = """\
# {display_name}

<!-- SKILL_PACKAGER: REPLACE THIS -->

{skill_description}
"""

# ---------------------------------------------------------------------------
# 12. CHANGELOG stub
# ---------------------------------------------------------------------------

CHANGELOG_STUB = """\
# Changelog

<!-- SKILL_PACKAGER: REPLACE THIS -->

All notable changes to this project will be documented in this file.

## [{version}] - {date}

### Added
- Initial release of the {skill_name} skill
- Cross-platform support: Claude Code, Claude Desktop, Claude Cowork, Cursor, Manus, ChatGPT, Codex CLI (native plugin)
"""

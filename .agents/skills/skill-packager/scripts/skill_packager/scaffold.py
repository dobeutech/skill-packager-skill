"""Scaffold a skill-packager repository from skill-packager.json (or legacy meta.json)."""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict

from skill_packager.manifests import build_codex_plugin
from skill_packager.path_hygiene import (
    PACKAGE_IGNORE,
    substitution_applies,
    clean_text as _strip_claude_skill_dir,
)
from skill_packager.templates import (
    CHANGELOG_STUB,
    CLAUDE_PLUGIN_JSON,
    CODEX_MARKETPLACE_JSON,
    CURSOR_PLUGIN_JSON,
    DEPLOY_PAGES_YML,
    INSTALL_HTML,
    LICENSE_MIT,
    MARKETPLACE_JSON,
    README_STUB,
    RELEASE_YML,
    VERSIONING_MD,
    BUMP_VERSION_PY,
    BUILD_ZIP_PY,
    _FIND_META_HELPER,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_source(source_path: str, meta_path: Path) -> Path:
    """Resolve a skill's ``source_path`` against the manifest's directory.

    An absolute path in a committed config can only ever be right on the
    machine that wrote it. Relative paths are resolved against the manifest so
    the config is portable; absolute paths still work for a fresh extraction.
    """
    p = Path(source_path)
    return p if p.is_absolute() else (meta_path.parent / p).resolve()


def _require_source(source: Path | None, sname: str, meta_path: Path) -> None:
    """Fail loudly when a declared source directory is missing.

    Silently scaffolding an empty skill directory is worse than not
    scaffolding: the repo looks generated and contains nothing.
    """
    if source is not None and not source.exists():
        print(f"Error: source_path for skill '{sname}' does not exist: {source}\n"
              f"       (resolved from {meta_path})", file=sys.stderr)
        sys.exit(1)


def _copy_skill_files(source_path: Path, dest_path: Path) -> None:
    """Copy a skill directory preserving structure."""
    shutil.copytree(source_path, dest_path, ignore=PACKAGE_IGNORE)


def _copy_skill_files_stripped(source_path: Path, dest_path: Path) -> None:
    """Copy a skill directory, stripping ``${CLAUDE_SKILL_DIR}/`` path uses from .md files."""
    shutil.copytree(source_path, dest_path, ignore=PACKAGE_IGNORE)
    for root, _dirs, files in os.walk(dest_path):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fpath = Path(root) / fname
            if not substitution_applies(fpath.relative_to(dest_path)):
                continue
            text = fpath.read_text()
            cleaned = _strip_claude_skill_dir(text)
            if cleaned != text:
                fpath.write_text(cleaned)


def _ensure_skill_md_has_version(skill_md_path: Path, version: str) -> None:
    """Inject ``metadata.version`` into SKILL.md if it is absent."""
    text = skill_md_path.read_text()
    lines = text.split("\n")

    # Find frontmatter boundaries
    end_idx = None
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break

    if end_idx is not None:
        # Check if version already present in frontmatter (not body)
        frontmatter_text = "\n".join(lines[1:end_idx])
        if re.search(r'version:\s*["\']?[0-9]', frontmatter_text):
            return

        # Look for metadata: section
        metadata_idx = None
        for i in range(1, end_idx):
            if lines[i].strip() == "metadata:":
                metadata_idx = i
                break

        if metadata_idx is not None:
            lines.insert(metadata_idx + 1, f'  version: "{version}"')
        else:
            lines.insert(end_idx, "metadata:")
            lines.insert(end_idx + 1, f'  version: "{version}"')
        skill_md_path.write_text("\n".join(lines))
    else:
        # No frontmatter at all -- prepend one
        frontmatter = f'---\nmetadata:\n  version: "{version}"\n---\n'
        skill_md_path.write_text(frontmatter + text)


def _make_executable(path: Path) -> None:
    """Add user/group/other execute permission bits."""
    st = path.stat()
    path.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _template_vars(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Build a template variable dict from meta.json data."""
    today = date.today()
    keywords = meta.get("keywords", [])
    skills = meta.get("skills", [])
    skill_name = skills[0].get("name", "") if skills else ""
    return {
        "skill_name": skill_name,
        "plugin_name": meta.get("plugin_name", ""),
        "marketplace_name": meta.get("marketplace_name", ""),
        "display_name": meta.get("display_name", ""),
        "skill_description": meta.get("description", ""),
        "version": meta.get("version", "0.0.0"),
        "author_name": meta.get("author_name", ""),
        "author_email": meta.get("author_email", ""),
        "github_owner": meta.get("github_owner", ""),
        "github_repo": meta.get("github_repo", ""),
        "repo_url": f"https://github.com/{meta.get('github_owner', '')}/{meta.get('github_repo', '')}",
        "homepage": meta.get("homepage") or (
            f"https://github.com/{meta.get('github_owner', '')}/{meta.get('github_repo', '')}"
            if meta.get("github_owner") and meta.get("github_repo") else ""
        ),
        "license": meta.get("license", "MIT"),
        "keywords_json": json.dumps(keywords),
        "keywords": keywords,  # list form, for build_codex_plugin (keywords_json stays for templates)
        "category": meta.get("category", ""),
        "brand_color": meta.get("brand_color", "#6C5CE7"),
        "default_prompt": meta.get("default_prompt")
            or f"Use {meta.get('display_name') or meta.get('plugin_name') or 'this skill'} to accomplish its task",
        "year": str(today.year),
        "date": str(today),
        "zip_filename": meta.get("zip_filename")
                        or f"dist/{meta.get('plugin_name', 'skill')}.zip",
    }


# ---------------------------------------------------------------------------
# Format predicates
# ---------------------------------------------------------------------------

def _wants_plugin_tree(formats: list[str]) -> bool:
    return any(f in formats for f in ("universal", "claude-plugin", "claude-marketplace", "cursor-plugin", "codex-plugin"))


def _wants_marketplace(formats: list[str]) -> bool:
    # codex-plugin also emits the legacy .claude-plugin/marketplace.json (Codex/ChatGPT honor it)
    return any(f in formats for f in ("universal", "claude-marketplace", "codex-plugin"))


def _wants_codex_plugin(formats: list[str]) -> bool:
    return any(f in formats for f in ("universal", "codex-plugin"))


def _wants_cursor(formats: list[str]) -> bool:
    return any(f in formats for f in ("universal", "cursor-plugin"))


def _wants_agent_skills(formats: list[str]) -> bool:
    return any(f in formats for f in ("universal", "agent-skills"))


def _wants_ci(formats: list[str]) -> bool:
    return "universal" in formats


def _wants_tools(formats: list[str]) -> bool:
    return "universal" in formats


def _wants_static(formats: list[str]) -> bool:
    return "universal" in formats


def _wants_root_files(formats: list[str]) -> bool:
    return any(f in formats for f in ("universal", "claude-plugin", "claude-marketplace", "cursor-plugin", "codex-plugin"))


# ---------------------------------------------------------------------------
# Main scaffold function
# ---------------------------------------------------------------------------

def scaffold_repo(meta_path: Path, output_dir: Path) -> None:
    """Generate a skill-packager repository from *meta_path* into *output_dir*."""
    meta_path = Path(meta_path)
    output_dir = Path(output_dir)

    # Abort if output dir exists and is non-empty
    if output_dir.exists() and any(output_dir.iterdir()):
        print(f"Error: output directory is not empty: {output_dir}", file=sys.stderr)
        sys.exit(1)

    meta = json.loads(meta_path.read_text())
    formats = meta.get("formats", ["universal"])
    tvars = _template_vars(meta)
    version = meta.get("version", "0.0.0")
    plugin_name = meta.get("plugin_name", "")
    skills = meta.get("skills", [])

    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy manifest as skill-packager.json (new canonical name), rewriting each
    # source_path to the canonical copy inside the generated repo. The manifest
    # that ships with a repo should describe that repo, not the machine that
    # scaffolded it: an absolute path from the author's disk can never be right
    # for a second person, and scaffold reads this field back.
    shipped = json.loads(json.dumps(meta))
    if _wants_plugin_tree(formats):
        for entry in shipped.get("skills", []):
            if isinstance(entry, dict) and entry.get("source_path"):
                entry["source_path"] = f"{plugin_name}/skills/{entry['name']}"
    (output_dir / "skill-packager.json").write_text(
        json.dumps(shipped, indent=2) + "\n", encoding="utf-8")

    # --- Plugin tree ---
    if _wants_plugin_tree(formats):
        for skill in skills:
            sname = skill["name"] if isinstance(skill, dict) else skill
            source = (_resolve_source(skill["source_path"], meta_path)
                      if isinstance(skill, dict) and skill.get("source_path") else None)
            _require_source(source, sname, meta_path)

            # Canonical copy: <plugin_name>/skills/<skill_name>/
            canon_dir = output_dir / plugin_name / "skills" / sname
            if source and source.exists():
                _copy_skill_files(source, canon_dir)
            else:
                canon_dir.mkdir(parents=True, exist_ok=True)

            # Ensure SKILL.md has version
            skill_md = canon_dir / "SKILL.md"
            if skill_md.exists():
                _ensure_skill_md_has_version(skill_md, version)

        # Inner claude plugin.json
        inner_plugin_dir = output_dir / plugin_name / ".claude-plugin"
        inner_plugin_dir.mkdir(parents=True, exist_ok=True)
        (inner_plugin_dir / "plugin.json").write_text(
            CLAUDE_PLUGIN_JSON.format(**tvars)
        )

    # --- Marketplace manifest (root) ---
    if _wants_marketplace(formats):
        root_plugin_dir = output_dir / ".claude-plugin"
        root_plugin_dir.mkdir(parents=True, exist_ok=True)
        (root_plugin_dir / "marketplace.json").write_text(
            MARKETPLACE_JSON.format(**tvars)
        )

    # --- Cursor manifest ---
    if _wants_cursor(formats):
        cursor_dir = output_dir / ".cursor-plugin"
        cursor_dir.mkdir(parents=True, exist_ok=True)
        (cursor_dir / "plugin.json").write_text(
            CURSOR_PLUGIN_JSON.format(**tvars)
        )

    # --- Codex native plugin + marketplace ---
    if _wants_codex_plugin(formats):
        # plugin.json at <plugin>/.codex-plugin/ (beside skills/), skills="./skills/"
        codex_plugin_dir = output_dir / plugin_name / ".codex-plugin"
        codex_plugin_dir.mkdir(parents=True, exist_ok=True)
        # detect plugin-level assets/<name>.png so we never emit a broken asset path
        assets_dir = output_dir / plugin_name / "assets"
        assets_present = {
            name for name in ("logo", "composerIcon")
            if (assets_dir / f"{name}.png").exists()
        }
        (codex_plugin_dir / "plugin.json").write_text(
            build_codex_plugin(tvars, assets_present)
        )
        # native marketplace at .agents/plugins/marketplace.json
        codex_mkt_dir = output_dir / ".agents" / "plugins"
        codex_mkt_dir.mkdir(parents=True, exist_ok=True)
        (codex_mkt_dir / "marketplace.json").write_text(
            CODEX_MARKETPLACE_JSON.format(**tvars)
        )

    # --- .agents/skills/ stripped copy ---
    if _wants_agent_skills(formats):
        for skill in skills:
            sname = skill["name"] if isinstance(skill, dict) else skill
            source = (_resolve_source(skill["source_path"], meta_path)
                      if isinstance(skill, dict) and skill.get("source_path") else None)
            _require_source(source, sname, meta_path)

            agents_dest = output_dir / ".agents" / "skills" / sname
            if source and source.exists():
                _copy_skill_files_stripped(source, agents_dest)
            else:
                agents_dest.mkdir(parents=True, exist_ok=True)

    # --- CI/CD workflows ---
    if _wants_ci(formats):
        wf_dir = output_dir / ".github" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / "release.yml").write_text(RELEASE_YML.format(**tvars))
        (wf_dir / "deploy-pages.yml").write_text(DEPLOY_PAGES_YML.format(**tvars))

    # --- Tools ---
    if _wants_tools(formats):
        tools_dir = output_dir / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)

        bump_path = tools_dir / "bump-version.py"
        bump_path.write_text(
            BUMP_VERSION_PY.format(**tvars).replace("__FIND_META_HELPER__", _FIND_META_HELPER)
        )
        _make_executable(bump_path)

        zip_path = tools_dir / "build-zip.py"
        zip_path.write_text(
            BUILD_ZIP_PY.format(**tvars).replace("__FIND_META_HELPER__", _FIND_META_HELPER)
        )
        _make_executable(zip_path)

    # --- Static files ---
    if _wants_static(formats):
        static_dir = output_dir / "static"
        static_dir.mkdir(parents=True, exist_ok=True)
        (static_dir / "install-claude-desktop.html").write_text(
            INSTALL_HTML.format(**tvars)
        )

    # --- Root files ---
    if _wants_root_files(formats):
        (output_dir / "VERSION").write_text(version + "\n")
        (output_dir / "VERSIONING.md").write_text(VERSIONING_MD.format(**tvars))
        (output_dir / "LICENSE").write_text(LICENSE_MIT.format(**tvars))
        (output_dir / "README.md").write_text(README_STUB.format(**tvars))
        (output_dir / "CHANGELOG.md").write_text(CHANGELOG_STUB.format(**tvars))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def run_scaffold(args) -> None:
    """CLI entry: scaffold repo from metadata."""
    meta_path = Path(args.metadata)
    output_dir = Path(args.output)
    scaffold_repo(meta_path, output_dir)
    print(f"Scaffolded repo at {output_dir}")

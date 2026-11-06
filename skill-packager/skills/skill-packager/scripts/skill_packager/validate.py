"""Validate a skill-packager repository."""
from __future__ import annotations

import json
import re
import sys
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List

from skill_packager.path_hygiene import (
    IGNORE_NAMES,
    clean_text,
    path_use_lines,
    unquoted_skill_dir_lines,
    unstrippable_lines,
    unsubstituted_path_lines,
)


STUB_MARKER = "SKILL_PACKAGER: REPLACE THIS"
SKILL_MD_LINE_LIMIT = 500
NEW_MANIFEST = "skill-packager.json"
LEGACY_MANIFEST = "meta.json"


def _find_meta(repo_dir: Path):
    """Return (Path|None, is_legacy: bool). Prefers new name, falls back to legacy."""
    new = repo_dir / NEW_MANIFEST
    if new.exists():
        return new, False
    legacy = repo_dir / LEGACY_MANIFEST
    if legacy.exists():
        return legacy, True
    return None, False


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_json_valid(repo_dir: Path) -> List[Dict[str, Any]]:
    """Parse every .json file under repo_dir."""
    results: List[Dict[str, Any]] = []
    for jf in sorted(repo_dir.rglob("*.json")):
        rel = str(jf.relative_to(repo_dir))
        try:
            json.loads(jf.read_text())
            results.append({"check": f"json_valid: {rel}", "passed": True})
        except (json.JSONDecodeError, ValueError) as exc:
            results.append({"check": f"json_valid: {rel}", "passed": False,
                            "message": str(exc)})
    return results


def _extract_version_from_skill_md(path: Path) -> str | None:
    """Return the version string from a SKILL.md frontmatter, or None."""
    text = path.read_text()
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            break
        m = re.match(r'\s*version:\s*["\']?([0-9][^"\']*)', lines[i])
        if m:
            return m.group(1).strip()
    return None


def _check_version_consistency(repo_dir: Path, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compare version across VERSION, skill-packager.json, plugin.json, marketplace.json, etc."""
    results: List[Dict[str, Any]] = []
    expected = meta.get("version", "0.0.0")

    # Root VERSION file
    version_file = repo_dir / "VERSION"
    if version_file.exists():
        found = version_file.read_text().strip()
        passed = found == expected
        results.append({"check": "version_consistency: VERSION",
                         "passed": passed,
                         "message": f"expected {expected}, found {found}" if not passed else ""})

    # skill-packager.json / meta.json version (always present since we loaded it)
    manifest_path, _ = _find_meta(repo_dir)
    if manifest_path is not None:
        meta_on_disk = json.loads(manifest_path.read_text())
        found = meta_on_disk.get("version", "")
        passed = found == expected
        manifest_label = manifest_path.name
        results.append({"check": f"version_consistency: {manifest_label}",
                         "passed": passed,
                         "message": f"expected {expected}, found {found}" if not passed else ""})

    # Inner plugin.json
    plugin_name = meta.get("plugin_name", "")
    inner_plugin = repo_dir / plugin_name / ".claude-plugin" / "plugin.json"
    if inner_plugin.exists():
        try:
            data = json.loads(inner_plugin.read_text())
            found = data.get("version", "")
            passed = found == expected
            results.append({"check": "version_consistency: plugin.json",
                             "passed": passed,
                             "message": f"expected {expected}, found {found}" if not passed else ""})
        except (json.JSONDecodeError, ValueError):
            pass

    # marketplace.json (version is nested under metadata.version)
    mkt = repo_dir / ".claude-plugin" / "marketplace.json"
    if mkt.exists():
        try:
            data = json.loads(mkt.read_text())
            found = data.get("metadata", {}).get("version", "")
            passed = found == expected
            results.append({"check": "version_consistency: marketplace.json",
                             "passed": passed,
                             "message": f"expected {expected}, found {found}" if not passed else ""})
        except (json.JSONDecodeError, ValueError):
            pass

    # Cursor plugin.json
    cursor_plugin = repo_dir / ".cursor-plugin" / "plugin.json"
    if cursor_plugin.exists():
        try:
            data = json.loads(cursor_plugin.read_text())
            found = data.get("version", "")
            passed = found == expected
            results.append({"check": "version_consistency: cursor plugin.json",
                             "passed": passed,
                             "message": f"expected {expected}, found {found}" if not passed else ""})
        except (json.JSONDecodeError, ValueError):
            pass  # JSON validity is caught by _check_json_valid

    # Codex plugin.json
    codex_plugin = repo_dir / plugin_name / ".codex-plugin" / "plugin.json"
    if codex_plugin.exists():
        try:
            data = json.loads(codex_plugin.read_text())
            found = data.get("version", "")
            passed = found == expected
            results.append({"check": "version_consistency: codex plugin.json",
                             "passed": passed,
                             "message": f"expected {expected}, found {found}" if not passed else ""})
        except (json.JSONDecodeError, ValueError):
            pass  # JSON validity is caught by _check_json_valid

    # Per-skill VERSION and SKILL.md in the plugin tree
    skills = meta.get("skills", [])
    for skill in skills:
        sname = skill["name"] if isinstance(skill, dict) else skill
        skill_tree = repo_dir / plugin_name / "skills" / sname
        sv = skill_tree / "VERSION"
        if sv.exists():
            found = sv.read_text().strip()
            passed = found == expected
            results.append({"check": f"version_consistency: {sname}/VERSION",
                             "passed": passed,
                             "message": f"expected {expected}, found {found}" if not passed else ""})
        smd = skill_tree / "SKILL.md"
        if smd.exists():
            found = _extract_version_from_skill_md(smd)
            if found is not None:
                passed = found == expected
                results.append({"check": f"version_consistency: {sname}/SKILL.md",
                                 "passed": passed,
                                 "message": f"expected {expected}, found {found}" if not passed else ""})

    return results


def _skill_md_description(skill_md: Path) -> str | None:
    """The SKILL.md frontmatter description, whitespace-normalised."""
    text = skill_md.read_text(encoding="utf-8")
    m = re.search(r"^description:\s*>\s*\n((?:[ \t]+.*\n)+)", text, re.MULTILINE)
    if m:
        return " ".join(m.group(1).split())
    m = re.search(r"^description:[ \t]*(.+)$", text, re.MULTILINE)
    return " ".join(m.group(1).split()) if m else None


def _check_description_consistency(repo_dir: Path, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Manifest descriptions must be the leading text of the SKILL.md description.

    SKILL.md's own instructions say the manifest description is the skill
    description truncated to its first sentence. Nothing enforced that, and it
    drifted: the native Codex/ChatGPT format added in 0.3.0 reached SKILL.md
    but none of the five manifests, so every marketplace listing omitted it.
    Comparing against the source of truth catches that; checking each manifest
    on its own never could, since each was internally fine.

    Multi-skill repos author a separate plugin-level description, so the
    check applies only when there is exactly one skill.
    """
    results: List[Dict[str, Any]] = []
    skills = meta.get("skills", [])
    if len(skills) != 1:
        return results
    plugin_name = meta.get("plugin_name", "")
    sname = skills[0]["name"] if isinstance(skills[0], dict) else skills[0]
    skill_md = repo_dir / plugin_name / "skills" / sname / "SKILL.md"
    if not skill_md.exists():
        return results
    canonical = _skill_md_description(skill_md)
    if not canonical:
        return results

    candidates = [
        (NEW_MANIFEST, repo_dir / NEW_MANIFEST, ("description",)),
        ("plugin.json", repo_dir / plugin_name / ".claude-plugin" / "plugin.json", ("description",)),
        ("cursor plugin.json", repo_dir / ".cursor-plugin" / "plugin.json", ("description",)),
        ("codex plugin.json", repo_dir / plugin_name / ".codex-plugin" / "plugin.json", ("description",)),
    ]
    for label, path, keys in candidates:
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text())
            for k in keys:
                value = value.get(k)
        except (json.JSONDecodeError, AttributeError):
            continue
        if not value:
            continue
        passed = canonical.startswith(value.strip())
        results.append({"check": f"description_consistency: {label}",
                        "passed": passed,
                        "message": "" if passed else
                                   "does not match the start of the SKILL.md description "
                                   "(re-truncate it from the skill description)"})

    about = (meta.get("github_about") or "").strip()
    if about:
        # The GitHub About lives outside the repo, so nothing here can read the
        # published value. Keeping the intended text in the manifest puts it
        # inside the boundary; tools/sync-github-about.py publishes it.
        passed = canonical.startswith(about) and len(about) <= 350
        results.append({"check": "description_consistency: github_about",
                        "passed": passed,
                        "message": "" if passed else
                                   ("exceeds GitHub's 350-char About limit"
                                    if len(about) > 350 else
                                    "does not match the start of the SKILL.md description")})

    mk = repo_dir / ".claude-plugin" / "marketplace.json"
    if mk.exists():
        try:
            for plug in json.loads(mk.read_text()).get("plugins", []):
                value = (plug.get("description") or "").strip()
                if not value:
                    continue
                passed = canonical.startswith(value)
                results.append({"check": f"description_consistency: marketplace/{plug.get('name', '?')}",
                                "passed": passed,
                                "message": "" if passed else
                                           "does not match the start of the SKILL.md description"})
        except json.JSONDecodeError:
            pass
    return results


def _check_generated_tools(repo_dir: Path, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """tools/*.py must match what the current templates render.

    These are materialised copies. This repo's own `tools/build-zip.py` fell
    111 lines behind its template and would have re-shipped the corruption the
    templates had already been fixed for.
    """
    from skill_packager.scaffold import _template_vars
    from skill_packager.templates import BUILD_ZIP_PY, BUMP_VERSION_PY, _FIND_META_HELPER

    results: List[Dict[str, Any]] = []
    tools = repo_dir / "tools"
    if not tools.is_dir():
        return results
    try:
        tvars = _template_vars(meta)
    except Exception:
        return results
    for name, tmpl in (("build-zip.py", BUILD_ZIP_PY), ("bump-version.py", BUMP_VERSION_PY)):
        path = tools / name
        if not path.exists():
            continue
        rendered = tmpl.format(**tvars).replace("__FIND_META_HELPER__", _FIND_META_HELPER)
        passed = path.read_text(encoding="utf-8") == rendered
        results.append({"check": f"generated_tool: {name}",
                        "passed": passed,
                        "message": "" if passed else
                                   "differs from the rendered template (regenerate it)"})
    return results


def _check_release_artifact_name(repo_dir: Path, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """release.yml and the README must name the zip build-zip.py produces.

    A mismatch is silent: the release action finds no file, attaches nothing,
    and every `releases/latest/download/<name>` link 404s. That shipped twice.
    """
    results: List[Dict[str, Any]] = []
    zip_rel = meta.get("zip_filename") or f"dist/{meta.get('plugin_name', 'skill')}.zip"
    basename = zip_rel.rsplit("/", 1)[-1]

    wf = repo_dir / ".github" / "workflows" / "release.yml"
    if wf.exists():
        text = wf.read_text(encoding="utf-8")
        passed = zip_rel in text
        results.append({"check": "release_artifact: release.yml",
                        "passed": passed,
                        "message": "" if passed else
                                   f"does not upload {zip_rel}, which is what build-zip.py writes"})

    readme = repo_dir / "README.md"
    if readme.exists():
        links = re.findall(r"releases/latest/download/([^\s)\"']+)", readme.read_text(encoding="utf-8"))
        bad = sorted({l for l in links if l != basename})
        results.append({"check": "release_artifact: README links",
                        "passed": not bad,
                        "message": "" if not bad else
                                   f"link to {', '.join(bad)} but build-zip.py writes {basename}"})
    return results


def _check_skill_paths(repo_dir: Path, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Verify that manifest skill paths resolve to SKILL.md."""
    results: List[Dict[str, Any]] = []
    plugin_name = meta.get("plugin_name", "")
    skills = meta.get("skills", [])
    for skill in skills:
        sname = skill["name"] if isinstance(skill, dict) else skill
        skill_md = repo_dir / plugin_name / "skills" / sname / "SKILL.md"
        passed = skill_md.exists()
        results.append({"check": f"skill_path: {sname}",
                         "passed": passed,
                         "message": "" if passed else f"missing {skill_md.relative_to(repo_dir)}"})
    return results


def _check_source_paths(repo_dir: Path, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Each skill's source_path must resolve to a directory holding SKILL.md.

    A stale absolute path here is not inert: scaffold copies from it, and a
    missing source used to yield an empty skill directory with a zero exit.
    An absolute path is also the wrong kind of value for a committed config —
    it can never be right on a second machine. Relative paths resolve against
    the manifest.
    """
    results: List[Dict[str, Any]] = []
    for skill in meta.get("skills", []):
        if not isinstance(skill, dict) or not skill.get("source_path"):
            continue
        sname = skill.get("name", "?")
        raw = skill["source_path"]
        p = Path(raw)
        resolved = p if p.is_absolute() else (repo_dir / p)
        ok = (resolved / "SKILL.md").exists()
        note = ""
        if not ok:
            note = f"source_path does not resolve to a skill: {raw}"
        elif p.is_absolute():
            note = f"source_path is absolute and will not work elsewhere: {raw}"
        results.append({"check": f"source_path: {sname}",
                        "passed": ok and not p.is_absolute(),
                        "severity": "warn" if ok else "error",
                        "message": note})
    return results


def _check_agents_skills(repo_dir: Path) -> List[Dict[str, Any]]:
    """Verify .agents/skills/ entries have SKILL.md."""
    results: List[Dict[str, Any]] = []
    agents_dir = repo_dir / ".agents" / "skills"
    if not agents_dir.exists():
        return results
    for entry in sorted(agents_dir.iterdir()):
        if entry.is_dir():
            skill_md = entry / "SKILL.md"
            passed = skill_md.exists()
            results.append({"check": f"agents_skill: {entry.name}",
                             "passed": passed,
                             "message": "" if passed else f"missing SKILL.md in .agents/skills/{entry.name}"})
    return results


def _is_ignored(rel: Path) -> bool:
    """True if *rel* is a build artifact excluded from every packaged copy."""
    return any(fnmatch(part, pat) for part in rel.parts for pat in IGNORE_NAMES)


def _check_agents_mirror(repo_dir: Path, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Verify each .agents/skills/ copy matches its canonical source, cleaned.

    The .agents/ tree is the copy for hosts that cannot expand
    ``${CLAUDE_SKILL_DIR}``. Comparing it against the cleaned canonical source
    catches both a stale mirror and a mirror that was copied without path
    hygiene — the failure a bare ``grep`` for the token cannot distinguish
    from documentation that legitimately mentions it.
    """
    results: List[Dict[str, Any]] = []
    plugin_name = meta.get("plugin_name", "")
    agents_dir = repo_dir / ".agents" / "skills"
    if not agents_dir.exists():
        return results

    for skill in meta.get("skills", []):
        sname = skill["name"] if isinstance(skill, dict) else skill
        canonical = repo_dir / plugin_name / "skills" / sname
        mirror = agents_dir / sname
        if not canonical.is_dir() or not mirror.is_dir():
            continue

        drifted: List[str] = []
        for src in sorted(canonical.rglob("*")):
            if not src.is_file() or _is_ignored(src.relative_to(canonical)):
                continue
            rel = src.relative_to(canonical)
            dst = mirror / rel
            if not dst.exists():
                drifted.append(f"{rel} (missing)")
                continue
            if src.suffix == ".md":
                expected = clean_text(src.read_text(encoding="utf-8"))
                actual = dst.read_text(encoding="utf-8")
            else:
                expected = src.read_bytes()
                actual = dst.read_bytes()
            if expected != actual:
                drifted.append(str(rel))

        passed = not drifted
        results.append({
            "check": f"agents_mirror: {sname}",
            "passed": passed,
            "message": "" if passed else
                       "out of sync with canonical source (run tools/sync-agents-mirror.py): "
                       + ", ".join(drifted[:5])
                       + (f" +{len(drifted) - 5} more" if len(drifted) > 5 else ""),
        })
    return results


def _check_agents_path_hygiene(repo_dir: Path) -> List[Dict[str, Any]]:
    """Verify no .agents/ markdown uses ${CLAUDE_SKILL_DIR} as a path prefix."""
    results: List[Dict[str, Any]] = []
    agents_dir = repo_dir / ".agents"
    if not agents_dir.exists():
        return results
    offenders: List[str] = []
    unstrippable: List[str] = []
    unquoted: List[str] = []
    unsubstituted: List[str] = []
    for md in sorted(agents_dir.rglob("*.md")):
        text = md.read_text(encoding="utf-8")
        rel = md.relative_to(repo_dir)
        lines = path_use_lines(text)
        if lines:
            offenders.append(f"{rel}:{','.join(str(n) for n in lines)}")
        # rel is <skill-name>/<path>; the rule wants the path within the skill
        within_skill = Path(*md.relative_to(agents_dir).parts[1:])
        dead = unsubstituted_path_lines(text, within_skill)
        if dead:
            unsubstituted.append(f"{rel}:{','.join(str(n) for n in dead)}")
        bare = unstrippable_lines(text)
        if bare:
            unstrippable.append(f"{rel}:{','.join(str(n) for n in bare)}")
        loose = unquoted_skill_dir_lines(text)
        if loose:
            unquoted.append(f"{rel}:{','.join(str(n) for n in loose)}")

    passed = not offenders
    results.append({
        "check": "agents_path_hygiene",
        "passed": passed,
        "message": "" if passed else
                   "${CLAUDE_SKILL_DIR} used as a path in: " + "; ".join(offenders),
    })
    results.append({
        "check": "agents_command_block_hygiene",
        "passed": not unstrippable,
        "message": "" if not unstrippable else
                   "${CLAUDE_SKILL_DIR} inside a command block (no relative "
                   "rewrite is correct; resolve the skill directory once and "
                   "pass an absolute path): "
                   + "; ".join(unstrippable),
    })
    results.append({
        "check": "agents_token_substitution",
        "passed": not unsubstituted,
        "message": "" if not unsubstituted else
                   "${CLAUDE_SKILL_DIR} used as a path in a file Claude Code never "
                   "substitutes (use a path relative to that file): "
                   + "; ".join(unsubstituted),
    })
    results.append({
        "check": "agents_skill_dir_quoting",
        "passed": not unquoted,
        "message": "" if not unquoted else
                   "unquoted $SKILL_DIR in a command block (an unset value "
                   "word-splits to a bare `cd` into $HOME): " + "; ".join(unquoted),
    })
    return results


def _check_skill_md_length(repo_dir: Path, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Warn when SKILL.md exceeds 500 lines (NanoClaw enforces this limit)."""
    results: List[Dict[str, Any]] = []
    plugin_name = meta.get("plugin_name", "")
    skills = meta.get("skills", [])

    # Check plugin tree
    for skill in skills:
        sname = skill["name"] if isinstance(skill, dict) else skill
        skill_md = repo_dir / plugin_name / "skills" / sname / "SKILL.md"
        if skill_md.exists():
            line_count = len(skill_md.read_text().splitlines())
            if line_count > SKILL_MD_LINE_LIMIT:
                results.append({"check": f"skill_md_length: {sname}",
                                 "passed": True,
                                 "message": f"warning: SKILL.md is {line_count} lines "
                                            f"(NanoClaw enforces {SKILL_MD_LINE_LIMIT}-line limit)"})
            else:
                results.append({"check": f"skill_md_length: {sname}",
                                 "passed": True, "message": ""})

    # Check .agents/skills/ tree
    agents_dir = repo_dir / ".agents" / "skills"
    if agents_dir.exists():
        for entry in sorted(agents_dir.iterdir()):
            if entry.is_dir():
                skill_md = entry / "SKILL.md"
                if skill_md.exists():
                    line_count = len(skill_md.read_text().splitlines())
                    if line_count > SKILL_MD_LINE_LIMIT:
                        results.append({"check": f"skill_md_length: .agents/{entry.name}",
                                         "passed": True,
                                         "message": f"warning: SKILL.md is {line_count} lines "
                                                    f"(NanoClaw enforces {SKILL_MD_LINE_LIMIT}-line limit)"})

    return results


def _check_release_yml(repo_dir: Path) -> List[Dict[str, Any]]:
    """Check release.yml exists."""
    path = repo_dir / ".github" / "workflows" / "release.yml"
    passed = path.exists()
    return [{"check": "release_yml", "passed": passed,
             "message": "" if passed else "missing .github/workflows/release.yml"}]


def _check_bump_version(repo_dir: Path) -> List[Dict[str, Any]]:
    """Check bump-version.py exists."""
    path = repo_dir / "tools" / "bump-version.py"
    passed = path.exists()
    return [{"check": "bump_version_script", "passed": passed,
             "message": "" if passed else "missing tools/bump-version.py"}]


def _check_stub_readme(repo_dir: Path) -> List[Dict[str, Any]]:
    """Detect stub marker in README.md."""
    readme = repo_dir / "README.md"
    if not readme.exists():
        return [{"check": "readme_stub", "passed": False, "message": "README.md missing"}]
    text = readme.read_text()
    has_stub = STUB_MARKER in text
    return [{"check": "readme_stub", "passed": not has_stub,
             "message": "README.md still contains stub marker" if has_stub else ""}]


def _check_stub_changelog(repo_dir: Path) -> List[Dict[str, Any]]:
    """Detect stub marker in CHANGELOG.md."""
    cl = repo_dir / "CHANGELOG.md"
    if not cl.exists():
        return [{"check": "changelog_stub", "passed": False, "message": "CHANGELOG.md missing"}]
    text = cl.read_text()
    has_stub = STUB_MARKER in text
    return [{"check": "changelog_stub", "passed": not has_stub,
             "message": "CHANGELOG.md still contains stub marker" if has_stub else ""}]


# ---------------------------------------------------------------------------
# Main validation function
# ---------------------------------------------------------------------------

def validate_repo(repo_dir: Path) -> List[Dict[str, Any]]:
    """Run format-aware validation checks and return a list of result dicts."""
    repo_dir = Path(repo_dir)
    results: List[Dict[str, Any]] = []

    # Load skill-packager.json (or legacy meta.json) for format awareness
    meta_path, is_legacy = _find_meta(repo_dir)
    if meta_path is None:
        return [{"check": "manifest_exists", "passed": False,
                 "message": "skill-packager.json (or legacy meta.json) not found in repo root"}]
    if is_legacy:
        results.append({"check": "manifest_filename", "passed": True, "severity": "warn",
                         "message": "Using legacy meta.json — rename to skill-packager.json in a future release"})
    meta = json.loads(meta_path.read_text())
    formats = meta.get("formats", ["universal"])

    # Always run: JSON validity, skill paths, version consistency
    results.extend(_check_json_valid(repo_dir))
    results.extend(_check_skill_paths(repo_dir, meta))
    results.extend(_check_source_paths(repo_dir, meta))
    results.extend(_check_skill_md_length(repo_dir, meta))
    results.extend(_check_description_consistency(repo_dir, meta))
    results.extend(_check_version_consistency(repo_dir, meta))

    # Universal or agent-skills: .agents/skills/ checks
    if any(f in formats for f in ("universal", "agent-skills")):
        results.extend(_check_agents_skills(repo_dir))
        results.extend(_check_agents_mirror(repo_dir, meta))
        results.extend(_check_agents_path_hygiene(repo_dir))

    # Universal only: release.yml, bump-version.py, README/CHANGELOG stub detection
    if "universal" in formats:
        results.extend(_check_generated_tools(repo_dir, meta))
        results.extend(_check_release_artifact_name(repo_dir, meta))
        results.extend(_check_release_yml(repo_dir))
        results.extend(_check_bump_version(repo_dir))
        results.extend(_check_stub_readme(repo_dir))
        results.extend(_check_stub_changelog(repo_dir))

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def run_validate(args) -> None:
    """CLI entry: validate a skill repository."""
    repo_dir = Path(args.repo_dir)
    results = validate_repo(repo_dir)

    if args.json_output:
        print(json.dumps(results, indent=2))
    else:
        failed = [r for r in results if not r["passed"]]
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            msg = f"  -- {r.get('message', '')}" if r.get("message") else ""
            print(f"  [{status}] {r['check']}{msg}")
        print()
        if failed:
            print(f"{len(failed)} check(s) failed.")
            sys.exit(1)
        else:
            print(f"All {len(results)} checks passed.")

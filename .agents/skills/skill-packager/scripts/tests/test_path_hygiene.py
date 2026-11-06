r"""Path hygiene: strip ${CLAUDE_SKILL_DIR} where it is a path, nowhere else.

Regression cover for a bare `content.replace("${CLAUDE_SKILL_DIR}/", "")`,
which corrupted every documentation form of the token — including turning
`sed -i '' 's|\${CLAUDE_SKILL_DIR}/||g'` into the broken `sed -i '' 's|\||g'`
in shipped zips.

Two approaches that do not work, recorded so they are not retried:

* A ``\\$``-escape convention for documented literals. It collides with
  legitimate sed escaping (``s|\\${CLAUDE_SKILL_DIR}/||g``), so unescaping
  silently rewrites those commands — the same bug one layer up. The rule is
  keyed on position instead, with a whole-file opt-out marker.
* A generic "parse every fenced code block, fail the build on anything
  invalid" gate. ``bash -n`` accepts the corrupted line, because the
  corruption produces valid shell wrapping an invalid *sed* expression; only
  sed rejects it, at runtime. Nothing short of executing the expression
  catches that class, so the forms that must survive are enumerated below
  instead.

One known limit, left unimplemented on purpose: the quoting tracker is
line-based, so a heredoc inside a fence is classified by its body rather than
its delimiter. ``<<EOF`` expands ``$SKILL_DIR`` in the body (a real hazard the
tracker would miss) while ``<<'EOF'`` does not (a false positive if flagged).
No shipped skill uses a heredoc inside a fence, and an unexercised branch is
its own liability, so this is recorded rather than handled.
"""
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from skill_packager.path_hygiene import (
    NO_STRIP_MARKER,
    clean_text,
    is_exempt,
    path_use_lines,
    unquoted_skill_dir_lines,
    substitution_applies,
    unstrippable_lines,
    unsubstituted_path_lines,
)
from tests.helpers import SAMPLE_SKILL_MD


STRIPPED = [
    ("cd ${CLAUDE_SKILL_DIR}/scripts && python3 -m pkg",
     "cd scripts && python3 -m pkg"),
    ("python3 ${CLAUDE_SKILL_DIR}/scripts/validate.py x.py",
     "python3 scripts/validate.py x.py"),
    ("Read `${CLAUDE_SKILL_DIR}/references/platforms.md` now.",
     "Read `references/platforms.md` now."),
    ("[api.md](${CLAUDE_SKILL_DIR}/references/api.md)",
     "[api.md](references/api.md)"),
]

PRESERVED = [
    # prose: the slash is followed by whitespace, not a path segment
    "strip ${CLAUDE_SKILL_DIR}/ from ALL markdown files",
    "├── SKILL.md              (with ${CLAUDE_SKILL_DIR}/ stripped)",
    # prose: closing delimiter after the slash
    "keeps `${CLAUDE_SKILL_DIR}/` paths, the copy has them stripped",
    # sed/shell escaping — rewriting this changes what the command does
    r"find dist/ -name '*.md' -exec sed -i '' 's|\${CLAUDE_SKILL_DIR}/||g' {} +",
    r"          find dist/skills -name '*.md' -exec sed -i 's|\${CLAUDE_SKILL_DIR}/||g' {} +",
    # bare token, no slash at all
    "In Claude Code, `${CLAUDE_SKILL_DIR}` is expanded at runtime",
    "1. No remaining `${CLAUDE_SKILL_DIR}` references: `grep -r CLAUDE_SKILL_DIR dist/`",
]


@pytest.mark.parametrize("source,expected", STRIPPED)
def test_path_uses_are_stripped(source, expected):
    assert clean_text(source) == expected
    assert path_use_lines(source) == [1]


@pytest.mark.parametrize("source", PRESERVED)
def test_documentation_is_preserved(source):
    assert clean_text(source) == source
    assert path_use_lines(source) == []


def test_sed_command_stays_executable():
    """The corrupted form `s|\\||g` was shipped in dist/. Guard it explicitly."""
    src = r"sed -i '' 's|\${CLAUDE_SKILL_DIR}/||g'"
    assert clean_text(src) == src
    assert "s|\\||g" not in clean_text(src)


def test_no_strip_marker_exempts_whole_file():
    text = NO_STRIP_MARKER + "\ncd ${CLAUDE_SKILL_DIR}/scripts && run\n"
    assert is_exempt(text)
    assert clean_text(text) == text
    assert path_use_lines(text) == []


def test_clean_text_is_idempotent():
    once = clean_text("cd ${CLAUDE_SKILL_DIR}/scripts && x")
    assert clean_text(once) == once


def test_path_use_lines_reports_every_line():
    text = "\n".join([
        "intro ${CLAUDE_SKILL_DIR} bare",
        "cd ${CLAUDE_SKILL_DIR}/scripts",
        "prose ${CLAUDE_SKILL_DIR}/ trailing",
        "cd ${CLAUDE_SKILL_DIR}/references",
    ])
    assert path_use_lines(text) == [2, 4]


# --- the repo's own artifacts -------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[5]
SKILL_SRC = REPO_ROOT / "skill-packager" / "skills" / "skill-packager"


def test_formats_reference_opts_out():
    """formats.md teaches the token; it must ship verbatim."""
    text = (SKILL_SRC / "references" / "formats.md").read_text()
    assert is_exempt(text)
    assert clean_text(text) == text


def test_agents_mirror_has_no_path_uses():
    """The .agents/ copy is for hosts that cannot expand the token."""
    agents = REPO_ROOT / ".agents"
    if not agents.exists():
        pytest.skip(".agents/ not present")
    offenders = {
        str(md.relative_to(REPO_ROOT)): path_use_lines(md.read_text())
        for md in agents.rglob("*.md")
        if path_use_lines(md.read_text())
    }
    assert not offenders, f"run tools/sync-agents-mirror.py: {offenders}"


def _tree_fingerprint(root: Path):
    return {
        str(f.relative_to(root)): hashlib.sha256(f.read_bytes()).hexdigest()
        for f in sorted(root.rglob("*"))
        if f.is_file() and "__pycache__" not in f.parts
    }


def test_sync_agents_mirror_is_idempotent():
    """A second sync over an already-synced tree changes nothing."""
    script = REPO_ROOT / "tools" / "sync-agents-mirror.py"
    mirror = REPO_ROOT / ".agents" / "skills" / "skill-packager"
    if not (script.exists() and mirror.is_dir()):
        pytest.skip("not a checkout of this repo")
    run = lambda: subprocess.run([sys.executable, str(script)], check=True,
                                 capture_output=True, cwd=REPO_ROOT)
    run()
    first = _tree_fingerprint(mirror)
    run()
    assert _tree_fingerprint(mirror) == first, "sync is not idempotent"


def test_validate_flags_a_mirror_that_skipped_path_hygiene(tmp_path):
    """The exact bug that shipped: mirror copied without path hygiene."""
    from skill_packager.scaffold import scaffold_repo
    from skill_packager.validate import validate_repo
    from tests.helpers import make_source_skill, make_sample_meta

    skill_dir = make_source_skill(tmp_path)
    meta_path = make_sample_meta(tmp_path, skills=[{
        "name": "test-skill",
        "source_path": str(skill_dir),
        "description": "A test skill for unit testing",
        "has_scripts": True,
        "has_references": True,
        "has_assets": False,
        "has_agents": False,
        "has_evals": False,
    }])
    out = tmp_path / "output"
    scaffold_repo(meta_path, out)

    canonical = out / "test-skill" / "skills" / "test-skill"
    mirror = out / ".agents" / "skills" / "test-skill"
    assert path_use_lines((canonical / "SKILL.md").read_text())

    shutil.rmtree(mirror)
    shutil.copytree(canonical, mirror)  # bare copy, no path hygiene

    failed = {r["check"] for r in validate_repo(out) if not r["passed"]}
    assert "agents_path_hygiene" in failed
    assert "agents_mirror: test-skill" in failed


def test_non_markdown_files_carry_no_path_uses():
    """Stripping is markdown-only; nothing that ships may rely on it elsewhere.

    evals.json mentions the token in prose. If a real path use is ever added
    to a non-markdown file, no hygiene path would rewrite it — fail here.
    """
    skipped = {".md", ".pyc"}
    offenders = {}
    for f in sorted(SKILL_SRC.rglob("*")):
        if not f.is_file() or f.suffix in skipped:
            continue
        parts = set(f.parts)
        if "__pycache__" in parts or ".pytest_cache" in parts:
            continue
        if f.name in ("helpers.py", "test_path_hygiene.py"):
            continue  # fixtures that assert on the token by construction
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = path_use_lines(text)
        if lines:
            offenders[str(f.relative_to(SKILL_SRC))] = lines
    assert not offenders, (
        "path use in a non-markdown file, which nothing strips: %s" % offenders)


def test_bare_token_in_command_block_is_rejected():
    """`cd ${CLAUDE_SKILL_DIR}` cannot be stripped into anything correct."""
    doc = "prose about ${CLAUDE_SKILL_DIR} is fine\n\n```bash\ncd ${CLAUDE_SKILL_DIR} && run\n```\n"
    assert unstrippable_lines(doc) == [4]
    assert clean_text(doc) == doc  # nothing to rewrite - it must fail, not "fix"


def test_bare_token_outside_a_fence_is_prose():
    assert unstrippable_lines("see ${CLAUDE_SKILL_DIR} for details") == []


def test_slashed_token_in_a_command_block_is_also_rejected():
    """`cd ${CLAUDE_SKILL_DIR}/scripts` -> `cd scripts` is cwd-dependent.

    It fails loudly in most directories but succeeds into a *different*
    project's scripts/ when one exists there, running foreign code under the
    skill's name. No build-time rewrite can be correct.
    """
    doc = "```bash\ncd ${CLAUDE_SKILL_DIR}/scripts && run\n```\n"
    assert unstrippable_lines(doc) == [2]
    assert clean_text(doc) == doc  # left intact for the verifier to reject


def test_markdown_links_outside_fences_still_strip():
    """A link resolves relative to its file, so the relative form is correct."""
    doc = "See [api](${CLAUDE_SKILL_DIR}/references/api.md) and `${CLAUDE_SKILL_DIR}/scripts/x.py`."
    assert clean_text(doc) == "See [api](references/api.md) and `scripts/x.py`."
    assert unstrippable_lines(doc) == []


def test_fence_content_is_never_rewritten():
    doc = "```bash\ncd ${CLAUDE_SKILL_DIR}/scripts\n```\nprose ${CLAUDE_SKILL_DIR}/refs/a.md\n"
    out = clean_text(doc)
    assert "cd ${CLAUDE_SKILL_DIR}/scripts" in out   # untouched inside the fence
    assert "prose refs/a.md" in out                  # stripped outside it


def test_tilde_fences_are_recognised():
    doc = "~~~bash\ncd ${CLAUDE_SKILL_DIR}/scripts\n~~~\n"
    assert unstrippable_lines(doc) == [2]


def test_build_zip_rejects_a_token_in_a_command_block(tmp_path):
    from skill_packager.build_zip import build_zip
    from tests.helpers import make_source_skill

    skill_dir = make_source_skill(tmp_path)
    (skill_dir / "SKILL.md").write_text(
        SAMPLE_SKILL_MD + "\n```bash\ncd ${CLAUDE_SKILL_DIR} && python3 -m pkg\n```\n")
    with pytest.raises(ValueError, match="command block"):
        build_zip(skill_dir, tmp_path / "out.zip")


def test_this_skills_own_command_blocks_are_portable():
    """SKILL.md must not depend on the token inside a command block."""
    text = (SKILL_SRC / "SKILL.md").read_text()
    assert unstrippable_lines(text) == [], (
        "SKILL.md commands must resolve the skill directory themselves")


# --- the $SKILL_DIR convention the migration rests on ------------------------
#
# Verified against bash, with the variable unset:
#   cd "$SKILL_DIR/scripts"  -> cd: /scripts: No such file or directory  exit 1
#   cd "$SKILL_DIR"          -> cd: null directory                      exit 1
#   cd $SKILL_DIR            -> exit 0, lands in $HOME, && chain continues
# The quotes are what make the convention safe; unquoted it reproduces exactly
# the hazard the fence rule exists to prevent, under a different name.

QUOTED_OK = [
    'cd "$SKILL_DIR/scripts" && python3 -m pkg',
    'python3 "$SKILL_DIR/scripts/x.py"',
    "export SKILL_DIR=/absolute/path",          # assignment, nothing to split
    "echo '$SKILL_DIR is a literal here'",      # single quotes: no expansion
]

UNQUOTED_BAD = [
    "cd $SKILL_DIR && python3 -m pkg",
    "cd ${SKILL_DIR}/scripts",
    "python3 $SKILL_DIR/scripts/x.py",
]


@pytest.mark.parametrize("line", QUOTED_OK)
def test_quoted_skill_dir_is_accepted(line):
    assert unquoted_skill_dir_lines("```bash\n%s\n```\n" % line) == []


@pytest.mark.parametrize("line", UNQUOTED_BAD)
def test_unquoted_skill_dir_is_flagged(line):
    assert unquoted_skill_dir_lines("```bash\n%s\n```\n" % line) == [2]


def test_skill_dir_outside_a_fence_is_prose():
    assert unquoted_skill_dir_lines("set $SKILL_DIR to the skill's path") == []


def test_this_skills_own_commands_quote_skill_dir():
    """The property the migration rests on, asserted on the shipped file."""
    for md in sorted(SKILL_SRC.rglob("*.md")):
        assert unquoted_skill_dir_lines(md.read_text()) == [], md


def test_build_zip_rejects_unquoted_skill_dir(tmp_path):
    from skill_packager.build_zip import build_zip
    from tests.helpers import make_source_skill

    skill_dir = make_source_skill(tmp_path)
    (skill_dir / "SKILL.md").write_text(
        SAMPLE_SKILL_MD + "\n```bash\ncd $SKILL_DIR/scripts && run\n```\n")
    with pytest.raises(ValueError, match="unquoted"):
        build_zip(skill_dir, tmp_path / "out.zip")


# --- correspondence: prose vs. generated output ------------------------------
#
# A third failure class, distinct from the two above. Presence-checking (is the
# token here?) and position-checking (is this a path or prose?) both read ONE
# artifact. This one needs two: formats.md documented a release workflow that
# stripped paths with a blind `sed`, which was not wrong on its own terms — it
# was wrong relative to RELEASE_YML, which had long since moved to
# tools/build-zip.py. No single-file rule can see that, which is why grepping,
# the position rule, and a careful reading of every token occurrence all missed
# it. The fix is an equality assertion against the generated artifact.

_TEMPLATE_VARS = {
    "plugin_name": "P", "skill_name": "S", "skill_names": "S",
    "zip_filename": "z.zip", "version": "1.0.0", "display_name": "D",
    "description": "d", "author_name": "a", "author_email": "e",
    "github_owner": "o", "github_repo": "r", "license": "MIT", "year": "2026",
    "marketplace_name": "M", "category": "c", "keywords": "k",
}


def _build_step(text):
    """The 'Build generic zip' step, as a list of stripped lines."""
    out, collecting = [], False
    for line in text.split("\n"):
        if line.strip() == "- name: Build generic zip":
            collecting = True
            continue
        if collecting:
            if line.strip().startswith("- name:") or not line.strip():
                break
            out.append(line.strip())
    return out


def test_documented_release_workflow_matches_the_generated_one():
    """formats.md must not teach a build step the scaffold does not emit."""
    from skill_packager.templates import RELEASE_YML

    documented = _build_step(
        (SKILL_SRC / "references" / "formats.md").read_text())
    generated = _build_step(RELEASE_YML.format(**_TEMPLATE_VARS))

    assert documented, "no 'Build generic zip' step found in formats.md"
    assert generated, "no 'Build generic zip' step found in RELEASE_YML"
    assert documented == generated, (
        "formats.md documents a release build step that differs from the one "
        "the scaffold generates:\n  documented: %s\n  generated:  %s"
        % (documented, generated))


def test_manifest_descriptions_match_the_skill_description():
    """Every manifest description must be the leading text of SKILL.md's.

    SKILL.md instructs truncating the skill description to its first sentence
    for the manifests. Nothing enforced it, and it drifted: the native
    Codex/ChatGPT format added in 0.3.0 reached SKILL.md and none of the five
    manifests, so every marketplace listing omitted it for two releases.
    """
    from skill_packager.validate import validate_repo

    if not (REPO_ROOT / "skill-packager.json").exists():
        pytest.skip("not a checkout of this repo")
    failed = [r for r in validate_repo(REPO_ROOT)
              if not r["passed"] and r["check"].startswith("description_consistency")]
    assert not failed, [(r["check"], r["message"]) for r in failed]


# --- source_path portability -------------------------------------------------

def test_this_repos_source_path_is_relative_and_resolves():
    """A committed absolute source_path can never be right on another machine.

    This repo shipped one pointing at a pre-reorg directory. It was not inert:
    scaffold copies from it, and a missing source silently produced an empty
    skill directory with a zero exit.
    """
    import json
    if not (REPO_ROOT / "skill-packager.json").exists():
        pytest.skip("not a checkout of this repo")
    meta = json.loads((REPO_ROOT / "skill-packager.json").read_text())
    for skill in meta.get("skills", []):
        raw = skill.get("source_path")
        if not raw:
            continue
        assert not Path(raw).is_absolute(), f"{raw} is absolute"
        assert (REPO_ROOT / raw / "SKILL.md").exists(), f"{raw} does not resolve"


def test_scaffold_fails_loudly_on_a_missing_source(tmp_path):
    import json
    from skill_packager.scaffold import scaffold_repo
    from tests.helpers import make_source_skill, make_sample_meta

    skill_dir = make_source_skill(tmp_path)
    meta_path = make_sample_meta(tmp_path, skills=[{
        "name": "test-skill", "source_path": str(tmp_path / "gone"),
        "description": "d", "has_scripts": True, "has_references": True,
        "has_assets": False, "has_agents": False, "has_evals": False}])
    with pytest.raises(SystemExit) as e:
        scaffold_repo(meta_path, tmp_path / "out")
    assert e.value.code == 1


def test_scaffold_resolves_a_relative_source_against_the_manifest(tmp_path):
    from skill_packager.scaffold import scaffold_repo
    from tests.helpers import make_source_skill, make_sample_meta

    make_source_skill(tmp_path)                     # tmp_path/test-skill
    meta_path = make_sample_meta(tmp_path, skills=[{
        "name": "test-skill", "source_path": "test-skill",   # relative
        "description": "d", "has_scripts": True, "has_references": True,
        "has_assets": False, "has_agents": False, "has_evals": False}])
    out = tmp_path / "out"
    scaffold_repo(meta_path, out)
    assert (out / "test-skill" / "skills" / "test-skill" / "SKILL.md").exists()


# --- where the token is actually substituted ---------------------------------
#
# ${CLAUDE_SKILL_DIR} is a load-time text substitution into the skill's
# definition text, not a runtime environment variable — nothing exports it.
# Measured with the same token in two places in one skill, reading the
# DELIVERED content rather than the model's report of it:
#
#     SKILL.md body        BODY_PATH=/sessions/…/skills/ref-probe/scripts/y.py
#     references/paths.md  SCRIPT_PATH=${CLAUDE_SKILL_DIR}/scripts/y.py
#
# So a reference file's token stays literal and the read fails. Stripping does
# not repair it either: the result is relative to the skill root, while a link
# in references/guide.md resolves against references/.

def test_substitution_scope():
    """Only the SKILL.md body. Commands are a substitution surface but not
    for this token — the replace sites are guarded on isSkillMode, which the
    command loader passes as false. Measured:

        SKILL.md body          SKILL_SKILLDIR=/sessions/.../scripts/y.py  substituted
        commands/pathprobe.md  CMD_SKILLDIR=${CLAUDE_SKILL_DIR}/...       literal
    """
    assert substitution_applies("SKILL.md")
    assert not substitution_applies("commands/deploy.md")
    assert not substitution_applies("references/api.md")
    assert not substitution_applies("scripts/notes.md")
    assert not substitution_applies("agents/reviewer.md")


def test_token_in_a_command_file_is_an_error():
    doc = "Run `${CLAUDE_SKILL_DIR}/scripts/deploy.py` now.\n"
    assert unsubstituted_path_lines(doc, "commands/deploy.md") == [1]


def test_token_in_a_reference_file_is_an_error():
    doc = "See [api](${CLAUDE_SKILL_DIR}/references/api.md).\n"
    assert unsubstituted_path_lines(doc, "references/guide.md") == [1]
    assert unsubstituted_path_lines(doc, "SKILL.md") == []


def test_documenting_the_token_in_a_reference_file_is_still_allowed():
    doc = NO_STRIP_MARKER + "\nUse `${CLAUDE_SKILL_DIR}/scripts/x.py` in SKILL.md.\n"
    assert unsubstituted_path_lines(doc, "references/formats.md") == []


def test_reference_files_are_not_stripped(tmp_path):
    """Stripping a reference file would rebase the path against the wrong dir."""
    from skill_packager.scaffold import scaffold_repo
    from tests.helpers import make_source_skill, make_sample_meta

    skill_dir = make_source_skill(tmp_path)
    (skill_dir / "references" / "guide.md").write_text(
        NO_STRIP_MARKER + "\ntoken `${CLAUDE_SKILL_DIR}/scripts/x.py` documented here\n")
    meta_path = make_sample_meta(tmp_path, skills=[{
        "name": "test-skill", "source_path": str(skill_dir), "description": "d",
        "has_scripts": True, "has_references": True, "has_assets": False,
        "has_agents": False, "has_evals": False}])
    out = tmp_path / "out"
    scaffold_repo(meta_path, out)
    mirrored = (out / ".agents" / "skills" / "test-skill" / "references" / "guide.md").read_text()
    assert "${CLAUDE_SKILL_DIR}/scripts/x.py" in mirrored


def test_build_zip_rejects_a_token_in_a_reference_file(tmp_path):
    from skill_packager.build_zip import build_zip
    from tests.helpers import make_source_skill

    skill_dir = make_source_skill(tmp_path)
    (skill_dir / "references" / "guide.md").write_text(
        "See [api](${CLAUDE_SKILL_DIR}/references/api.md).\n")
    with pytest.raises(ValueError, match="read from disk"):
        build_zip(skill_dir, tmp_path / "out.zip")

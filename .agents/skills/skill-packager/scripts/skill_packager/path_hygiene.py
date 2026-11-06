"""Path hygiene for ``${CLAUDE_SKILL_DIR}`` references.

Claude Code expands ``${CLAUDE_SKILL_DIR}`` at runtime to the skill's absolute
path on disk. No other host does, so copies built for other hosts (the
``.agents/`` mirror, zips) must not depend on it.

Presence of the token is not the same as use of it as a path. A skill whose
documentation explains the token contains the literal in prose and inside
``sed`` expressions that operate on it; deleting every occurrence corrupts
both. Handling is therefore keyed on *position*, in two dimensions.

Outside a fenced code block, a path use is stripped to a relative path::

    [api.md](${CLAUDE_SKILL_DIR}/references/api.md)  ->  [api.md](references/api.md)

That is correct: a markdown link resolves relative to the file containing it,
so the relative form means the same thing on every host.

Inside a fenced code block, nothing is stripped and any occurrence is an
error, because no rewrite can be correct. A command runs with the shell's
current directory, which the packager cannot know at build time:

* ``cd ${CLAUDE_SKILL_DIR}`` becomes a bare ``cd`` — succeeds, lands in
  ``$HOME``, and lets an ``&&`` chain continue from the wrong place.
* ``cd ${CLAUDE_SKILL_DIR}/scripts`` stripped to ``cd scripts`` fails loudly
  in most directories, but succeeds into a *different project's* ``scripts/``
  when one happens to exist there, running foreign code under the skill's name.

The fix a skill should apply instead is to resolve its own directory once and
pass an absolute path downstream — see the error text raised by the build.

Forms left untouched everywhere: prose (``strip ${CLAUDE_SKILL_DIR}/ from
…``), a closing delimiter after the slash (```${CLAUDE_SKILL_DIR}/```), a
preceding backslash (shell/sed escaping), and the bare token with no slash.

A file that is *about* the token — a reference page teaching it — can opt out
entirely by containing NO_STRIP_MARKER anywhere in its text.

Scope: rewriting is markdown-only, deliberately. Markdown is instruction text
a model reads; a .py, .json or .sh is code and data whose meaning a blind
rewrite would change. In this repo the only non-markdown files containing the
token as a path are test fixtures that assert on it — stripping or flagging
those would be a false positive of exactly the kind this module exists to
avoid. Non-markdown files that ship a *real* path use are a gap the position
rule cannot close on its own; a skill needing one should resolve the skill
directory itself and pass an absolute path.
"""
import re
import shutil
from pathlib import Path

TOKEN = "${CLAUDE_SKILL_DIR}"
NO_STRIP_MARKER = "<!-- skill-packager:no-path-strip -->"

# Transient build artifacts that must never enter a packaged copy. A source
# skill is a working directory; a distributed one is not.
IGNORE_NAMES = (
    "__pycache__", "*.pyc", "*.pyo", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".DS_Store",
)
PACKAGE_IGNORE = shutil.ignore_patterns(*IGNORE_NAMES)

# The token followed by "/" and a path character. A slash before whitespace or
# a closing delimiter is prose, not a path. A preceding backslash is shell/sed
# escaping and is left strictly alone.
_PATH_USE = re.compile(r"(?<!\\)\$\{CLAUDE_SKILL_DIR\}/(?=[^\s\x60\x27\x22)\],;|])")
# Any unescaped occurrence, for the inside-a-fence check.
_ANY_USE = re.compile(r"(?<!\\)\$\{CLAUDE_SKILL_DIR\}")
_FENCE = re.compile(r"^\s*(```|~~~)")

# The convention skills migrate to. Quoting is load-bearing, not cosmetic:
#   cd "$SKILL_DIR"          unset -> cd: null directory   exit 1, loud
#   cd $SKILL_DIR            unset -> bare cd, $HOME, exit 0, && chain continues
# The quoted form turns an unset value into an error; the unquoted form
# reproduces exactly the hazard the fence rule exists to prevent, under a
# different name, where a check keyed on ${CLAUDE_SKILL_DIR} cannot see it.
_SKILL_DIR_VAR = re.compile(r"\$\{?SKILL_DIR\}?")


def substitution_applies(rel_path) -> bool:
    """True if Claude Code substitutes the token in this file.

    Only the SKILL.md body and its ``allowed-tools`` frontmatter. Not commands,
    not reference files, not anything else in the skill.

    ``${CLAUDE_SKILL_DIR}`` is not a runtime environment variable — nothing
    exports it, and it is empty in a shell. It is a load-time text substitution
    on the skill's definition text, and in the 2.1.251 binary both replacement
    sites are guarded on ``isSkillMode``, which the command loader passes as
    false: ``await WLt(C.commandsPath, …, {isSkillMode:!1})``.

    Measured, reading the delivered text rather than the model's report of it:

        SKILL.md body            SKILL_SKILLDIR=/sessions/…/scripts/y.py   substituted
        commands/pathprobe.md    CMD_SKILLDIR=${CLAUDE_SKILL_DIR}/…        literal
        references/paths.md      SCRIPT_PATH=${CLAUDE_SKILL_DIR}/…         literal

    The trap this closes: commands *are* a substitution surface, just not for
    this token. ``${CLAUDE_PLUGIN_ROOT}`` is substituted there, and
    ``${CLAUDE_SESSION_ID}`` and ``${CLAUDE_EFFORT}`` are replaced one
    statement away from the guarded site, outside the guard. So "does
    substitution happen in commands?" answers yes and is the wrong question.
    Only the token-specific one is decisive.
    """
    return Path(rel_path).parts == ("SKILL.md",)


def is_exempt(text: str) -> bool:
    """True if *text* opts out of path handling entirely."""
    return NO_STRIP_MARKER in text


def _fenced_flags(lines):
    """Yield True for each line that sits inside a fenced code block."""
    inside = False
    for line in lines:
        if _FENCE.match(line):
            inside = not inside
            yield False        # the fence marker itself is not content
        else:
            yield inside


def clean_text(text: str) -> str:
    """Strip ``${CLAUDE_SKILL_DIR}/`` path prefixes outside fenced code blocks.

    Occurrences inside a fence are deliberately left in place so the build's
    verification step can reject them; there is no correct rewrite.
    """
    if is_exempt(text):
        return text
    lines = text.split("\n")
    return "\n".join(
        line if fenced else _PATH_USE.sub("", line)
        for line, fenced in zip(lines, _fenced_flags(lines))
    )


def path_use_lines(text: str):
    """1-indexed lines outside fences where the token still prefixes a path."""
    if is_exempt(text):
        return []
    lines = text.split("\n")
    return [i for i, (line, fenced) in enumerate(zip(lines, _fenced_flags(lines)), 1)
            if not fenced and _PATH_USE.search(line)]


def unstrippable_lines(text: str):
    """1-indexed lines inside a fenced code block that use the token.

    These cannot be fixed by stripping — the correct value depends on the
    shell's working directory at run time, which the packager cannot know.
    The skill must resolve its own directory and pass an absolute path.
    """
    if is_exempt(text):
        return []
    lines = text.split("\n")
    return [i for i, (line, fenced) in enumerate(zip(lines, _fenced_flags(lines)), 1)
            if fenced and _ANY_USE.search(line)]


def _unquoted_spans(line, pattern):
    """Start offsets of *pattern* matches that sit outside any quoting.

    Inside double quotes the value is safe. Inside single quotes it does not
    expand at all, so it is not this hazard. Everything else is exposed to
    word splitting.
    """
    starts = {m.start() for m in pattern.finditer(line)}
    if not starts:
        return []
    found, in_single, in_double, escaped = [], False, False, False
    for i, ch in enumerate(line):
        if i in starts and not in_single and not in_double:
            found.append(i)
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
        elif ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
    return found


def unquoted_skill_dir_lines(text: str):
    """1-indexed fenced lines using $SKILL_DIR without quotes.

    `cd $SKILL_DIR` word-splits to a bare `cd` when the variable is unset:
    exit 0, lands in $HOME, and an `&&` chain keeps going from there. The
    quoted form fails loudly instead.
    """
    if is_exempt(text):
        return []
    lines = text.split("\n")
    return [i for i, (line, fenced) in enumerate(zip(lines, _fenced_flags(lines)), 1)
            if fenced and _unquoted_spans(line, _SKILL_DIR_VAR)]


def unsubstituted_path_lines(text: str, rel_path):
    """1-indexed path-uses in a file where the token is never substituted.

    These cannot be repaired by stripping. Stripping yields a path relative to
    the *skill root*, which is correct only for a file at the root. A link
    inside ``references/guide.md`` resolves against ``references/``, so
    ``${CLAUDE_SKILL_DIR}/references/api.md`` would have to become ``api.md``
    there, not ``references/api.md`` — a broken link rewritten into a
    differently broken one. So it is an error, like a fenced command.
    """
    if is_exempt(text) or substitution_applies(rel_path):
        return []
    return path_use_lines(text)

---
name: skill-packager
description: >
  Package AI agent skills into deployment formats — .zip, .skill, Claude plugin, Claude marketplace,
  Cursor plugin, Cursor marketplace, native Codex/ChatGPT plugin, ChatGPT/Manus zip, Codex CLI,
  NanoClaw marketplace, OpenClaw/ClawHub, Agent Skills standard (.agents/), or a universal repo with all formats + CI/CD.
  Use when the user says "package this skill", "deploy my skill", "create a plugin from this skill",
  "make this work on Cursor/ChatGPT/Codex/NanoClaw/OpenClaw", "set up a repo for my skill",
  or wants to distribute a SKILL.md to any platform.
metadata:
  author: Yaniv Golan
  version: "0.5.0"
---

# Skill Packager

You package one or more skills (directories containing SKILL.md) into deployment-ready formats for distribution across AI platforms.

## Step 1: Discover the input

Ask the user for the skill directory path(s).

**If the user provides a name instead of a path** (e.g., `fiction-studio` rather than `/some/path/fiction-studio`), search these locations in order before asking the user:
1. `~/.claude/plugins/` — installed Claude Code plugins
2. `~/.claude/skills/` — personal skills directory
3. `.agents/skills/` relative to CWD — cross-platform skills
4. CWD itself

If not found in the above, do a broader search under `~/Library/Application Support/Claude/` (macOS) or `~/.config/claude/` (Linux).

Then read each skill's SKILL.md to extract:
- `name` — the skill identifier
- `description` — what it does
- `metadata.author`, `metadata.version` — if present
- `license` — if present
- Whether it has `scripts/`, `references/`, `assets/`, `agents/`, `evals/`

If packaging multiple skills, confirm the list before proceeding.

## Step 2: Gather metadata

You need these values to generate manifests. Extract what you can from the SKILL.md frontmatter and the git repo (if any). Ask the user for anything missing:

| Field | Source | Fallback |
|-------|--------|----------|
| Skill name(s) | SKILL.md `name` | required |
| Description | SKILL.md `description` | required |
| Author name | SKILL.md `metadata.author` or git config | ask user |
| Author email | git config `user.email` | ask user |
| Version | SKILL.md `metadata.version` or `VERSION` file | default `0.1.0` |
| License | SKILL.md `license` | default `MIT` |
| GitHub owner/repo | git remote or ask | needed for marketplace/repo formats |
| Plugin name | derived from skill name | user can override |
| Keywords/tags | extracted from description | user can refine |

For multi-skill packages, also ask for an overall plugin/marketplace name and description.

When asking for fields that have a fixed set of choices (like license), use the **AskUserQuestion** tool to present structured options. For free-form fields (author name, email, description), ask in plain text — batch related free-form questions together to minimize back-and-forth.

## Step 3: Choose destination(s)

Ask **where the skill will run**, not which file format to emit — users think in destinations (Claude Code, ChatGPT, Cursor…), and several destinations share one artifact. Use the **AskUserQuestion** tool. Because it allows at most 4 options per question, use two questions.

**Question 1** (single-select, header: "Scope"):
> "How do you want to distribute this skill?"

| Option | Description |
|--------|-------------|
| All destinations / public distribution (Recommended) | Universal repo — every format below + CI/CD, version management, README, GitHub Pages install page |
| Pick specific destinations | Choose exactly where it should run |
| Just a ZIP (manual upload) | Clean zip of the skill folder(s), for one-off upload anywhere |

If the user picks **All destinations**, use `formats: ["universal"]` and skip Question 2.
If the user picks **Just a ZIP**, do NOT scaffold — run `python -m skill_packager build-zip --skill-dir <skill-dir> --output <zip>` (see Step 4). Do not put a format key in `skill-packager.json` for this.

**Question 2** (multiSelect, header: "Destinations", only if "Pick specific" was chosen):
> "Which destinations should this skill install into?"

| Option | Covers | Format key |
|--------|--------|-----------|
| Anthropic (Claude Code, Cowork, NanoClaw) | All install from one `.claude-plugin/` marketplace repo | `claude-marketplace` |
| Codex / ChatGPT | Native `.codex-plugin/` + `.agents/plugins/marketplace.json` (+ legacy `.claude-plugin/`) | `codex-plugin` |
| Cursor | `.cursor-plugin/plugin.json` | `cursor-plugin` |
| OpenClaw / cross-client | `.agents/skills/` (Agent Skills standard) | `agent-skills` |

### Destination → format-key mapping (resolve the answer, then write `formats` in `skill-packager.json`)

| Destination | Format key |
|-------------|-----------|
| Claude Code · Claude Cowork · NanoClaw | `claude-marketplace` |
| Codex · ChatGPT | `codex-plugin` |
| Cursor | `cursor-plugin` |
| OpenClaw / ClawHub · any Agent-Skills client | `agent-skills` |
| Generic ZIP upload | *(no key — use the `build-zip` subcommand)* |
| All / public distribution | `universal` |

Collect the chosen destinations, map each to its key, de-duplicate, and set `formats` to that list. Notes:
- **Collapse:** Claude Code, Cowork, and NanoClaw all resolve to the single `claude-marketplace` repo — if the user picked several of those, tell them "these all install from one repo."
- **Codex/ChatGPT** additionally keeps the legacy `.claude-plugin/marketplace.json`, so a `codex-plugin` package is installable in *both* ecosystems.
- If the user picked 3+ ecosystems or wants public distribution, recommend `universal` instead.

If the user asks for a `.skill` file specifically, use the `package_skill.py` script from the skill-creator-plus plugin if available, or tell them to run it separately.

<details>
<summary>Advanced: full internal format-key table</summary>

| Format key | What it produces |
|---|---|
| `universal` | Full repo with ALL formats + CI/CD + version management |
| `claude-plugin` | Inner `.claude-plugin/plugin.json` + plugin tree |
| `claude-marketplace` | Above + root `.claude-plugin/marketplace.json` |
| `cursor-plugin` | `.cursor-plugin/plugin.json` (also serves Cursor marketplace) |
| `codex-plugin` | `<plugin>/.codex-plugin/plugin.json` + `.agents/plugins/marketplace.json` + legacy `.claude-plugin/marketplace.json` |
| `agent-skills` | `.agents/skills/` stripped copy (Agent Skills standard) |

Generic ZIP is not a format key — build it with `python -m skill_packager build-zip`.
</details>

## Step 4: Generate the output

### Output directory

Use the **AskUserQuestion** tool to confirm the output directory (header: "Output"):
> "Where should the packaged output go?"

| Option | Description |
|--------|-------------|
| `../<skill-name>-skill/` (Recommended) | New directory relative to **CWD** (not relative to the skill source — use this unless the skill source is already in a convenient location) |
| `./dist/` | Subdirectory inside the current project |

The user can also pick "Other" to specify a custom path.

### Generation process

Use the bundled scripts to handle all deterministic generation:

#### 1. Extract metadata from source skill(s)

The scripts are a Python package and must be run with `-m` from the `scripts/` directory.

**First, resolve this skill's directory once.** Every command below uses `$SKILL_DIR`; a relative path would resolve against whatever directory the shell happens to be in, which is the project or session root, not this skill. In Claude Code the value is `${CLAUDE_SKILL_DIR}`; on other hosts it is the absolute path of the directory containing this SKILL.md. Keep the quotes — `cd $SKILL_DIR` unquoted word-splits to a bare `cd` into `$HOME` if the variable is unset, while the quoted form fails loudly.

```bash
export SKILL_DIR=/absolute/path/to/skill-packager
```

```bash
# Single skill:
cd "$SKILL_DIR/scripts" && python3 -m skill_packager metadata \
  --skill-path /path/to/skill > /tmp/partial-skill-packager.json

# Multi-skill:
cd "$SKILL_DIR/scripts" && python3 -m skill_packager metadata \
  --skill-path /path/to/skill-a --skill-path /path/to/skill-b > /tmp/partial-skill-packager.json
```

Read the output JSON. Fill in any empty fields — paying special attention to these:

- **`marketplace_name`** — the script sets this to the same value as `plugin_name`. You must append `-marketplace` manually: `"marketplace_name": "<plugin-name>-marketplace"`.
- **`description`** — the script copies the full SKILL.md description, which may be hundreds of words. Truncate it to the first sentence only (the one-liner that will appear in `plugin.json`, `marketplace.json`, and the README).
- `github_repo`, `formats`, `keywords`, `category`, `targets` — fill as needed.
- For multi-skill: also fill `plugin_name`, `display_name`, `version`.

Write the complete metadata to `skill-packager.json`.

#### 2. Scaffold the repo

```bash
cd "$SKILL_DIR/scripts" && python3 -m skill_packager scaffold \
  --metadata /path/to/skill-packager.json --output ./my-skill-repo/
```

This creates the full directory structure, copies skill files, renders all manifests, and creates the `.agents/skills/` copy. The canonical copy (under `<plugin-name>/skills/`) keeps `${CLAUDE_SKILL_DIR}/` paths; in the `.agents/skills/` copy they are stripped to relative paths *outside* code fences, where a relative path is correct. Inside a fence the token is a build error rather than something to rewrite — see [What gets stripped](references/formats.md#what-gets-stripped).

#### 3. Write README.md and CHANGELOG.md

These are the creative parts that require judgment. Read `references/platforms.md` for the per-platform installation instructions template.

The scaffolded README.md and CHANGELOG.md contain `<!-- SKILL_PACKAGER: REPLACE THIS -->` markers. Replace the entire file content with real content. The README should include:
- Title and badges (Agent Skills compatible, Claude Code plugin, Cursor plugin, license)
- Brief description of what the skill(s) do
- Installation sections for every supported platform
- Usage examples (pulled from the skill's description or examples)
- License

#### 4. Build zip (if needed)

For formats that need a zip (ZIP, ChatGPT/Manus, Codex CLI):

```bash
cd "$SKILL_DIR/scripts" && python3 -m skill_packager build-zip \
  --skill-dir ./my-skill-repo/<plugin-name>/skills/<skill-name> \
  --output dist/<skill-name>.zip
```

## Step 5: Verify the output

Run the validation script:

```bash
cd "$SKILL_DIR/scripts" && python3 -m skill_packager validate ./my-skill-repo/
```

This checks JSON validity, version consistency across all locations, skill path resolution, `.agents/skills/` entries, and stub detection (README/CHANGELOG must not still contain the placeholder marker). It also checks path hygiene: that the `.agents/` mirror matches the cleaned canonical source byte-for-byte, that no markdown still uses `${CLAUDE_SKILL_DIR}` as a path prefix or inside a command block, and that `$SKILL_DIR` is quoted wherever it appears in one. Fix any failures and rerun until all checks pass.

For machine-readable output, add `--json`.

## Step 6: Present results

Tell the user what was generated with a file tree. Highlight:
- How to do the first release (bump version, tag, push)
- Which platforms are supported and how to install on each
- Any manual steps needed (e.g., marketplace registration)
- **GitHub Pages setup**: Remind the user to enable GitHub Pages in repo Settings → Pages → Source: GitHub Actions. This powers the "Install in Claude Desktop" button.

## Edge cases and gotchas

**Skills with dependencies.** If a skill's `compatibility` field mentions required tools (Python, ffmpeg, etc.), include a note in the README about prerequisites. For ChatGPT specifically, warn if the skill requires tools that won't work in ChatGPT's sandbox.

**Skills with scripts.** Scripts are included in the zip. Do not rely on a relative path in a *command* — it resolves against the shell's working directory, which is the project or session root, not the skill. Have the skill resolve its own directory once and use `cd "$SKILL_DIR/scripts"` (see Step 4). Relative paths in markdown *links* are fine: those resolve against the file.

**The `.agents/skills/` copy.** This is a real directory copy, not a symlink, so it works on Windows and in zips. It is *not* byte-identical to the canonical copy: `${CLAUDE_SKILL_DIR}/` path prefixes are stripped outside code fences. Regenerate it with the scaffold rather than editing it by hand — `validate` compares it against the cleaned canonical source and fails on any drift.

**ChatGPT limitations.** ChatGPT Skills are in beta (Business/Enterprise/Edu/Teachers/Healthcare plans only). Always include this caveat. If the skill requires network access or specific CLI tools, warn that it may not work in ChatGPT.

**Codex CLI.** Supports `$skill-installer <github-url>` for automated install, or manual extraction to `~/.codex/skills/`. Both should be documented.

**npx skills add.** The `vercel-labs/skills` package provides cross-platform install via `npx skills add <owner>/<repo>`. Include this in the README when generating a universal repo.

**Cursor plugin path.** The `.cursor-plugin/plugin.json` at repo root needs `"skills"` to point to the inner plugin's skills directory (e.g., `"./pretext/skills"`), not the repo root.

**Marketplace naming.** The marketplace name is `<plugin-name>-marketplace`. The inner plugin name is just `<plugin-name>`.

**NanoClaw.** [NanoClaw](https://github.com/qwibitai/nanoclaw) is a containerized AI assistant built on Anthropic's Agent SDK. It uses standard Claude Code skills distributed via marketplace repos — the Claude marketplace format works directly. NanoClaw has four skill types; this packager covers operational and utility skills (standard Claude Code skills). Feature skills (`skill/*` branches) and container skills (`container/skills/`) are NanoClaw-internal patterns outside packaging scope. NanoClaw enforces a 500-line SKILL.md limit.

**OpenClaw / ClawHub.** [OpenClaw](https://github.com/openclaw/openclaw) uses standard Claude Code skills with an optional `metadata.openclaw` frontmatter block for runtime gating (required binaries, env vars, install specs). The Agent Skills standard format (#8), Claude marketplace, or ZIP all work for distribution. Skills can also be published to [ClawHub](https://github.com/openclaw/clawhub) via `clawhub skill publish`. ClawHub requires a `version` field in frontmatter and enforces MIT-0 licensing.

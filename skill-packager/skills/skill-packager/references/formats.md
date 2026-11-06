<!-- skill-packager:no-path-strip -->
# Deployment Format Templates

This file documents `${CLAUDE_SKILL_DIR}` itself, so it carries the
`no-path-strip` marker above and is copied verbatim into every packaged
format. See [What gets stripped](#what-gets-stripped).

This reference contains the exact file templates for each deployment format. Variables in `{{double braces}}` should be replaced with actual values from the skill metadata.

## Table of Contents

- [Common variables](#common-variables)
- [ZIP format](#zip-format)
- [Claude plugin](#claude-plugin)
- [Claude marketplace](#claude-marketplace)
- [Cursor plugin](#cursor-plugin)
- [Cursor marketplace](#cursor-marketplace)
- [Codex / ChatGPT plugin](#codex--chatgpt-plugin)
- [Agent Skills standard](#agent-skills-standard)
- [NanoClaw marketplace](#nanoclaw-marketplace)
- [GitHub Actions release workflow](#github-actions-release-workflow)
- [Version management](#version-management)
- [Universal repo — full file list](#universal-repo--full-file-list)

---

## Common variables

These are used across all templates. Collect them in Step 2 of the main skill.

| Variable | Example | Notes |
|----------|---------|-------|
| `{{skill-name}}` | `proof-engine` | From SKILL.md `name` field |
| `{{skill-description}}` | `Create formal proofs...` | From SKILL.md `description` |
| `{{plugin-name}}` | `proof-engine` | Usually same as skill name; for multi-skill, user chooses |
| `{{marketplace-name}}` | `proof-engine-marketplace` | `{{plugin-name}}-marketplace` |
| `{{version}}` | `0.1.0` | From metadata or VERSION file |
| `{{author-name}}` | `Yaniv Golan` | From metadata or git config |
| `{{author-email}}` | `yaniv@golan.name` | From git config |
| `{{github-owner}}` | `yaniv-golan` | GitHub username or org |
| `{{github-repo}}` | `proof-engine-skill` | Repository name |
| `{{license}}` | `MIT` | From SKILL.md or default |
| `{{keywords}}` | `["proof", "verification"]` | JSON array of strings |
| `{{category}}` | `development` | One of: development, productivity, data, creative, devops |
| `{{repo-url}}` | `https://github.com/yaniv-golan/proof-engine-skill` | Full repo URL |
| `{{zip-filename}}` | `proof-engine-skill.zip` | `{{github-repo}}.zip` |

Optional `skill-packager.json` fields (used by the Codex/ChatGPT plugin manifest; all have sensible fallbacks):
| Field | Example | Notes |
|-------|---------|-------|
| `homepage` | `https://…github.io/…/` | Feeds ChatGPT's "Website" row + Claude `homepage`. Falls back to `{{repo-url}}`. |
| `brand_color` | `#6C5CE7` | Codex `interface.brandColor`. Defaults to a neutral hex. |
| `default_prompt` | `Use Proof Engine to verify a proof` | Codex `interface.defaultPrompt` (a single string). Defaults to `Use {{display-name}} to accomplish its task`. |

For multi-skill packages, also collect:
| Variable | Example |
|----------|---------|
| `{{plugin-description}}` | Overall description for the plugin |
| `{{skill-names}}` | Array of all skill names |

---

## ZIP format

The ZIP contains the full skill folder(s) — SKILL.md, scripts, references, assets, agents, and any other files — with `${CLAUDE_SKILL_DIR}/` path references stripped for cross-platform compatibility.

### Why path hygiene is needed

In Claude Code, `${CLAUDE_SKILL_DIR}` is a **load-time text substitution**, not a runtime environment variable. Claude Code replaces the literal string with the skill's absolute path when it loads the skill's definition text, before the model sees it. Nothing exports it — it is empty in a shell, which is why leaving it in a command is a defect rather than a fallback. (Verified against the 2.1.251 binary: every site is a literal `.replace(/\${CLAUDE_SKILL_DIR}/g, …)` in prompt and allowed-tools construction, gated on a resolved skill root.) Claude Code separately tells the model `Base directory for this skill: <path>`, which is where the value for a `SKILL_DIR` export comes from.

The substitution reaches **the SKILL.md body and its `allowed-tools` frontmatter, and nothing else** — not `commands/*.md`, not reference files. Both replacement sites are guarded on `isSkillMode`, which the command loader passes as false (`await WLt(C.commandsPath, …, {isSkillMode:!1})`).

Beware a truthful answer to the wrong question here: commands *are* a substitution surface. `${CLAUDE_PLUGIN_ROOT}` works in them, and `${CLAUDE_SESSION_ID}` and `${CLAUDE_EFFORT}` are replaced one statement away from the guarded site, outside the guard. So "does substitution happen in commands?" is yes, and misleading. The question that decides it is per-token.

Use the token for:
- **Script invocations** in SKILL.md: `python3 ${CLAUDE_SKILL_DIR}/scripts/validate.py proof.py`
- **Markdown links to references** in SKILL.md: `[api.md](${CLAUDE_SKILL_DIR}/references/api.md)`

Anywhere else — a **reference file**, a `commands/*.md`, an agent definition — the token is a build error, because it can never work there. A `references/*.md` is read from disk at runtime and never passes through the substitution, so the token arrives as literal characters and the read fails. Measured with the same token in two places in one skill, inspecting the delivered content rather than the model's report of it:

```
SKILL.md body          BODY_PATH=/sessions/.../skills/ref-probe/scripts/y.py   substituted
commands/pathprobe.md  CMD_SKILLDIR=${CLAUDE_SKILL_DIR}/scripts/y.py          literal
references/paths.md    SCRIPT_PATH=${CLAUDE_SKILL_DIR}/scripts/y.py           literal
```

Stripping is not the fix and is not applied there: it yields a path relative to the *skill root*, so `${CLAUDE_SKILL_DIR}/references/api.md` inside `references/guide.md` would become `references/api.md` where the correct link is `api.md` — one broken link rewritten into another. Use a path relative to the file instead (`api.md`, `../scripts/x.py`), which is correct on every host. A file that *documents* the token is exempt via the `no-path-strip` marker.

Other platforms (Manus, ChatGPT, Codex, Windsurf, etc.) don't expand this variable. Left in place, a POSIX shell expands the undefined variable to nothing and runs `cd /scripts`. Stripping the prefix converts absolute paths to relative paths (`scripts/validate.py`, `references/api.md`), which resolve correctly wherever paths are read relative to the skill directory — markdown reference links, and hosts that extract the skill as a flat structure with these subdirectories as siblings of SKILL.md.

### What gets stripped

Handling is keyed on *position*, in two dimensions: whether the token is used as a path, and whether it sits inside a fenced code block.

**Outside a fence**, a path use is stripped to a relative path. That is correct — a markdown link resolves relative to the file containing it, so the relative form means the same thing on every host.

| Form | Treated as | Result |
|---|---|---|
| `[api.md](${CLAUDE_SKILL_DIR}/references/api.md)` | link | stripped to `references/api.md` |
| `strip ${CLAUDE_SKILL_DIR}/ from …` | prose (slash ends the run) | kept |
| `` `${CLAUDE_SKILL_DIR}/` `` | prose (closing delimiter) | kept |
| `'s|\${CLAUDE_SKILL_DIR}/||g'` | shell/sed escape | kept, backslash untouched |
| `${CLAUDE_SKILL_DIR}` (no slash) | bare token | kept |

**Inside a fence**, nothing is stripped and any occurrence is a build error. A command runs against the shell's working directory, which the packager cannot know at build time, so no rewrite is correct:

- `cd ${CLAUDE_SKILL_DIR}` becomes a bare `cd` — it *succeeds*, lands in `$HOME`, and lets an `&&` chain continue from the wrong place. The failure surfaces later as an unrelated import error.
- `cd ${CLAUDE_SKILL_DIR}/scripts` stripped to `cd scripts` fails loudly in most directories, but succeeds into a **different project's** `scripts/` when one happens to exist there — running foreign code under your skill's name. The same applies to `python3 ${CLAUDE_SKILL_DIR}/scripts/validate.py` → `python3 scripts/validate.py`, and `validate.py` is a common enough filename that the collision is not exotic.

Write commands so they resolve the skill directory once and use an absolute path from then on:

```bash
export SKILL_DIR=/absolute/path/to/your-skill
cd "$SKILL_DIR/scripts" && python3 -m your_package
```

**Quote the variable.** `cd "$SKILL_DIR/scripts"` fails loudly if `SKILL_DIR` is unset or empty; `cd $SKILL_DIR` word-splits to a bare `cd`, which *succeeds* into `$HOME` and lets an `&&` chain continue from there — the same silent failure this rule exists to prevent, under a different name. The build rejects an unquoted `$SKILL_DIR` inside a fence for exactly this reason.

Tell the model in prose where that value comes from — in Claude Code it is `${CLAUDE_SKILL_DIR}`; on other hosts it is the directory the SKILL.md was read from. Prose is not stripped, so that instruction survives into every packaged format.

A reference file that is *about* the token can opt out of stripping entirely by containing the marker `<!-- skill-packager:no-path-strip -->` anywhere in its text. This file does.

### Build process

```bash
mkdir -p dist

# For single skill — copy the ENTIRE skill directory (not just SKILL.md)
cp -r {{plugin-name}}/skills/{{skill-name}} dist/{{skill-name}}

# For multi-skill:
# for skill in {{skill-names}}; do
#   cp -r {{plugin-name}}/skills/$skill dist/$skill
# done

# Path hygiene — do NOT do this with a blind sed (see below)
python3 tools/build-zip.py --version {{version}}

# Write version
echo "{{version}}" > dist/{{skill-name}}/VERSION

cd dist && zip -r ../{{zip-filename}} {{skill-name}}/
```

> **Do not hand-roll path hygiene with `sed`.** A blind
> `sed 's|\${CLAUDE_SKILL_DIR}/||g'` deletes the token everywhere it appears,
> not only where it prefixes a path — it corrupts prose, mangles the `sed`
> expressions in documentation *about* the token, and cannot enforce the
> command-block rule below. Earlier versions of this file recommended exactly
> that, and it shipped malformed commands in the 0.3.x release zips. Use
> `tools/build-zip.py` (or `python3 -m skill_packager build-zip`), which applies
> the position-keyed rules and fails the build on a command block that cannot be
> made portable.

### What gets included in the zip

The zip should contain everything in the skill directory:

```
{{skill-name}}/
├── SKILL.md              (with ${CLAUDE_SKILL_DIR}/ stripped)
├── VERSION
├── scripts/              (if exists — copied as-is, these are executed by the agent)
├── references/           (if exists — .md files have paths stripped too)
├── assets/               (if exists — templates, data files, etc.)
├── agents/               (if exists — subagent definitions)
└── evals/                (if exists — test cases)
```

### Verification

After building the zip, verify:
1. All `.md` files have no remaining `${CLAUDE_SKILL_DIR}` references: `grep -r 'CLAUDE_SKILL_DIR' dist/`
2. Scripts are present and have the same relative paths referenced in SKILL.md
3. Reference files are present and their cross-references resolve

The resulting zip works for: Claude.ai upload, Manus upload, ChatGPT upload, Codex CLI manual install, and extraction to `.agents/skills/` for any agent. (For a *native* Codex/ChatGPT install via a marketplace — not just a manual zip — see [Codex / ChatGPT plugin](#codex--chatgpt-plugin).)

---

## Claude plugin

The inner plugin directory that Claude Code discovers.

### Directory structure

```
{{plugin-name}}/
├── .claude-plugin/
│   └── plugin.json
└── skills/
    └── {{skill-name}}/
        ├── SKILL.md
        ├── VERSION
        └── ... (scripts/, references/, etc.)
```

### `{{plugin-name}}/.claude-plugin/plugin.json`

```json
{
  "name": "{{plugin-name}}",
  "version": "{{version}}",
  "description": "{{skill-description}}",
  "author": {
    "name": "{{author-name}}",
    "email": "{{author-email}}"
  },
  "repository": "{{repo-url}}",
  "license": "{{license}}",
  "keywords": {{keywords}},
  "skills": "./skills"
}
```

For multi-skill plugins, `skills` still points to `"./skills"` — Claude Code discovers all subdirectories containing SKILL.md.

---

## Claude marketplace

A root-level marketplace manifest that wraps the inner plugin.

### Directory structure (additions to repo root)

```
.claude-plugin/
└── marketplace.json
```

### `.claude-plugin/marketplace.json`

```json
{
  "name": "{{marketplace-name}}",
  "owner": {
    "name": "{{author-name}}",
    "email": "{{author-email}}"
  },
  "metadata": {
    "description": "{{skill-description}}",
    "version": "{{version}}"
  },
  "plugins": [
    {
      "name": "{{plugin-name}}",
      "source": "./{{plugin-name}}",
      "description": "{{skill-description}}",
      "author": {
        "name": "{{author-name}}",
        "email": "{{author-email}}"
      },
      "category": "{{category}}",
      "tags": {{keywords}}
    }
  ]
}
```

**Installation commands** (for README):

```bash
# CLI
claude plugin marketplace add https://github.com/{{github-owner}}/{{github-repo}}
claude plugin install {{plugin-name}}@{{marketplace-name}}

# Or from within a Claude Code session:
/plugin marketplace add {{github-owner}}/{{github-repo}}
/plugin install {{plugin-name}}@{{marketplace-name}}
```

---

## Cursor plugin

### Directory structure (at repo root)

```
.cursor-plugin/
└── plugin.json
```

### `.cursor-plugin/plugin.json`

```json
{
  "name": "{{plugin-name}}",
  "displayName": "{{display-name}}",
  "version": "{{version}}",
  "description": "{{skill-description}}",
  "author": {
    "name": "{{author-name}}",
    "email": "{{author-email}}"
  },
  "license": "{{license}}",
  "keywords": {{keywords}},
  "skills": "./{{plugin-name}}/skills"
}
```

Note: `skills` path is relative from repo root and points into the inner plugin's skills directory.

**Installation** (for README):

```
1. Open Cursor Settings
2. Paste https://github.com/{{github-owner}}/{{github-repo}} into "Search or Paste Link"
```

---

## Cursor marketplace

Same as Cursor plugin. The `.cursor-plugin/plugin.json` at repo root is what the Cursor marketplace indexes. No separate marketplace manifest is needed — Cursor discovers plugins from the repo directly.

---

## Codex / ChatGPT plugin

Since July 2026, ChatGPT and Codex support a plugin + marketplace system that structurally mirrors Claude Code. This format makes a skill natively installable there. **Schema verified live against codex-cli 0.144.4 and OpenAI's shipped plugins.**

### Directory structure (at repo root)

```
{{plugin-name}}/
├── .codex-plugin/
│   └── plugin.json          ← native Codex manifest (interface block)
└── skills/                  ← skills live at the plugin root, NOT under .codex-plugin/
    └── {{skill-name}}/SKILL.md
.agents/plugins/
└── marketplace.json         ← native Codex marketplace
.claude-plugin/
└── marketplace.json         ← legacy path; Codex/ChatGPT ALSO honor this
```

### `{{plugin-name}}/.codex-plugin/plugin.json`

Key differences from the Claude plugin manifest:
- `"skills": "./skills/"` — **trailing slash** (Claude uses `"./skills"`). Resolves against the plugin root, i.e. `{{plugin-name}}/skills/`.
- Adds an `interface` block: `displayName`, `shortDescription`, `developerName`, `category`, `brandColor`, `defaultPrompt` (a **string**, not an array), and optional `logo`/`composerIcon` (emitted only if `{{plugin-name}}/assets/<name>.png` exists — never a broken path).
- `homepage` is included (feeds ChatGPT's "Website" row).

### `.agents/plugins/marketplace.json`

```json
{
  "name": "{{marketplace-name}}",
  "interface": { "displayName": "{{display-name}}" },
  "plugins": [
    {
      "name": "{{plugin-name}}",
      "source": { "source": "git-subdir", "url": "{{repo-url}}.git", "path": "./{{plugin-name}}", "ref": "main" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "{{category}}"
    }
  ]
}
```

`source.path` resolves against the **marketplace root** (`$REPO_ROOT`), so `./{{plugin-name}}` correctly targets the plugin subdir. Marketplace files are recognized at `$REPO_ROOT/.agents/plugins/marketplace.json`, `~/.agents/plugins/marketplace.json`, and the legacy `$REPO_ROOT/.claude-plugin/marketplace.json`.

### Install

```bash
# From a GitHub repo (shorthand, git URL, or SSH all accepted):
codex plugin marketplace add {{github-owner}}/{{github-repo}}
codex plugin add {{plugin-name}}@{{marketplace-name}}
# Update later:
codex plugin marketplace upgrade
```

Because Codex honors the legacy `.claude-plugin/marketplace.json`, a Claude-marketplace repo is already installable in Codex/ChatGPT without this native format — the `.codex-plugin/` manifest just adds a first-class install surface (display name, category, website, default prompt). There is **no web-page deep link** to trigger install (unlike Claude's `claude://` button); install happens in the CLI or the desktop Plugins UI.

---

## Agent Skills standard

The `.agents/skills/` directory provides cross-client skill discovery per the agentskills.io spec.

### Directory structure (at repo root)

```
.agents/
└── skills/
    └── {{skill-name}}/        (a real copy, with path hygiene applied)
```

Create it as a **copy, not a symlink** — the scaffold does this for you:

```bash
python3 -m skill_packager scaffold --metadata skill-packager.json --output ./repo/
```

For multi-skill packages one copy is made per skill.

**Why not a symlink?** A symlink would point at the canonical files, which deliberately keep `${CLAUDE_SKILL_DIR}/` path prefixes. `.agents/` is the tree read by hosts that *cannot expand that token*, so a symlink hands them exactly the paths they cannot resolve — a shell expands the undefined variable to nothing and runs `cd /scripts`. The copy exists so path hygiene can be applied to it. A symlink also does not survive a zip on Windows, and it defeats the `agents_mirror` drift check, which compares the copy byte-for-byte against the cleaned canonical source.

**Keeping it in sync:** regenerate with the scaffold, or run a sync script that re-applies the hygiene. Never edit `.agents/` by hand — `validate` will fail on the drift.

---

## NanoClaw marketplace

[NanoClaw](https://github.com/qwibitai/nanoclaw) is a lightweight, containerized AI assistant built on Anthropic's Agent SDK. It connects to WhatsApp, Telegram, Slack, Discord, Gmail and other messaging apps, running each agent in an isolated Docker container.

NanoClaw has four skill types: **feature skills** (branch-based, for adding capabilities to NanoClaw itself), **utility skills** (self-contained code + SKILL.md), **operational skills** (instruction-only workflows), and **container skills** (loaded inside agent containers at runtime). The skill packager covers **operational and utility skills** — these are standard Claude Code skills distributed via marketplace repos. Feature skills (which use `skill/*` git branches) and container skills (which live in `container/skills/` with `allowed-tools` frontmatter) are NanoClaw-internal patterns outside the scope of generic skill packaging.

The Claude marketplace format (`.claude-plugin/marketplace.json`) works directly with NanoClaw. No separate format is needed.

NanoClaw users install via:
```bash
# In .claude/settings.json, add to extraKnownMarketplaces:
# Or use Claude Code:
claude plugin marketplace add https://github.com/{{github-owner}}/{{github-repo}}
claude plugin install {{plugin-name}}@{{marketplace-name}} --scope project
```

**NanoClaw-specific note:** NanoClaw enforces a 500-line limit on SKILL.md files. Keep skill instructions concise and move detail to separate reference files.

---

## OpenClaw / ClawHub

[OpenClaw](https://github.com/openclaw/openclaw) is a personal AI assistant that connects Claude and other LLMs to messaging platforms (Slack, WhatsApp, Telegram, Discord). [ClawHub](https://github.com/openclaw/clawhub) is OpenClaw's public skill registry.

OpenClaw skills use the same SKILL.md format as Claude Code, with an optional `metadata.openclaw` frontmatter block for runtime gating (required binaries, env vars, OS restrictions, dependency install specs). These extensions are content the skill author adds to their SKILL.md — they don't affect packaging structure.

**Distribution options:**

1. **Claude marketplace** — OpenClaw discovers skills from `.agents/skills/` and `~/.agents/skills/`, so the Agent Skills standard format (#8) or a Claude marketplace repo both work.
2. **ClawHub** — publish directly via `clawhub skill publish <path>`. ClawHub requires a `version` field in SKILL.md frontmatter and enforces MIT-0 licensing.
3. **ZIP** — users can extract into `~/.openclaw/skills/` or workspace `skills/` directory.

OpenClaw's skill discovery order: workspace `skills/` > `.agents/skills/` > `~/.agents/skills/` > `~/.openclaw/skills/` > bundled. Same-named skills at higher precedence override lower ones.

**OpenClaw-specific note:** If your skill requires specific binaries or env vars, add a `metadata.openclaw` block to your SKILL.md frontmatter so OpenClaw can gate loading. Example: `metadata: { "openclaw": { "requires": { "bins": ["ffmpeg"], "env": ["API_KEY"] } } }`

---

## GitHub Actions release workflow

### `.github/workflows/release.yml`

```yaml
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

      - name: Extract version from tag
        id: version
        run: echo "version=${GITHUB_REF#refs/tags/v}" >> "$GITHUB_OUTPUT"

      - name: Build generic zip
        run: |
          VERSION="${{ steps.version.outputs.version }}"
          python3 tools/build-zip.py --version "$VERSION"

      - name: Extract release notes from CHANGELOG.md
        id: changelog
        run: |
          VERSION="${{ steps.version.outputs.version }}"
          NOTES=$(awk "/^## \\[${VERSION}\\]/{found=1; next} /^## \\[/{if(found) exit} found{print}" CHANGELOG.md)
          echo "$NOTES" > release-notes.md

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          body_path: release-notes.md
          files: |
            {{zip-filename}}
```

For multi-skill packages the build step is identical — `tools/build-zip.py`
reads `skill-packager.json` to discover the layout and handles single- and
multi-skill repos the same way, including path hygiene and the command-block
check.

---

## Version management

### `VERSION`

```
{{version}}
```

Plain text, no trailing newline issues. This is the single source of truth.

### `tools/bump-version.py`

This is a **Python** script (generated from the packager's `BUMP_VERSION_PY` template), not a shell script. It reads `skill-packager.json` (the source of truth) to discover the plugin name, skills, and enabled formats, then propagates the version to every location, skipping any file that doesn't exist.

```bash
# Usage — both arguments required:
python3 tools/bump-version.py <REPO_DIR> <VERSION>

# From the repo root:
python3 tools/bump-version.py . 0.3.0
```

Locations updated (each is a no-op if the file is absent, so the script works for any format subset):
`skill-packager.json`, root `VERSION`, `{{plugin-name}}/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json` (`metadata.version`), `.cursor-plugin/plugin.json`, `{{plugin-name}}/.codex-plugin/plugin.json`, each `{{plugin-name}}/skills/*/SKILL.md` frontmatter, each `{{plugin-name}}/skills/*/VERSION`, and the `.agents/skills/` copies.

### `VERSIONING.md`

The generated `VERSIONING.md` documents the above: source of truth is `skill-packager.json` (+ root `VERSION`); all 9 location types are managed by the bump script; the release process is bump → update CHANGELOG → commit → `git tag vX.Y.Z` → `git push origin main --tags` (CI then builds the zip and creates the GitHub Release). See the `VERSIONING_MD` template for the exact text emitted.

### `CHANGELOG.md`

```markdown
# Changelog

All notable changes to this project will be documented in this file.

## [{{version}}] - {{date}}

### Added
- Initial release of the {{skill-name}} skill
- Cross-platform support: Claude Code, Claude Desktop, Claude Cowork, Cursor, Manus, ChatGPT, Codex CLI (native plugin)
- Claude Code plugin marketplace support
- Cursor plugin support
- GitHub Release workflow for zip distribution
```

Replace `{{date}}` with the current date in YYYY-MM-DD format.

### `LICENSE` (MIT)

```
MIT License

Copyright (c) {{year}} {{author-name}}

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
```

---

## Claude Desktop install button

A one-click install button for Claude Desktop. Requires GitHub Pages enabled on the repo.

### `static/install-claude-desktop.html`

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Install {{Skill Display Name}} in Claude Desktop</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background: #f9f5f1; color: #3d3929; }
.card { text-align: center; padding: 3rem; max-width: 480px; }
h1 { font-size: 1.4rem; margin-bottom: 1rem; }
p { color: #6b5e4f; line-height: 1.6; }
a { color: #d97757; text-decoration: none; font-weight: 600; }
a:hover { text-decoration: underline; }
.fallback { display: none; }
</style>
</head>
<body>
<div class="card">
<h1>Installing {{Skill Display Name}}</h1>
<p id="status">Opening Claude Desktop...</p>
<div id="fallback" class="fallback">
<p>Claude Desktop didn't open. You can:</p>
<p><a href="claude://claude.ai/customize/plugins/new?marketplace=https://github.com/{{github-owner}}/{{github-repo}}&plugin={{plugin-name}}">Try again</a></p>
<p>Or install manually: open Claude Desktop, click <strong>Customize</strong>, then <strong>Browse Plugins</strong>, add marketplace <code>{{github-owner}}/{{github-repo}}</code>.</p>
</div>
<p><a href="https://github.com/{{github-owner}}/{{github-repo}}">Back to {{Skill Display Name}} on GitHub</a></p>
</div>
<script>
var deepLink = "claude://claude.ai/customize/plugins/new?marketplace=https://github.com/{{github-owner}}/{{github-repo}}&plugin={{plugin-name}}";
var repo = "https://github.com/{{github-owner}}/{{github-repo}}";

// Try opening the deep link
window.location = deepLink;

// If the page is still visible after 5s, the deep link likely didn't work
setTimeout(function() {
  if (!document.hidden) {
    document.getElementById("status").textContent = "";
    document.getElementById("fallback").style.display = "block";
  }
}, 5000);

// If the user comes back to this tab (Claude opened then they switched back), redirect to repo
document.addEventListener("visibilitychange", function() {
  if (!document.hidden) {
    setTimeout(function() { window.location = repo; }, 500);
  }
});
</script>
</body>
</html>
```

### `.github/workflows/deploy-pages.yml`

```yaml
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
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - name: Build site
        run: |
          mkdir -p _site/static
          cp static/install-claude-desktop.html _site/static/

      - uses: actions/upload-pages-artifact@v3

      - id: deployment
        uses: actions/deploy-pages@v4
```

### README badge

Add this badge near the top of the README (requires GitHub Pages to be enabled in repo settings):

```markdown
[![Install in Claude Desktop](https://img.shields.io/badge/Install_in_Claude_Desktop-D97757?style=for-the-badge&logo=claude&logoColor=white)](https://{{github-owner}}.github.io/{{github-repo}}/static/install-claude-desktop.html)
```

### Setup note

GitHub Pages must be enabled on the repo for the install button to work:
1. Go to repo **Settings** → **Pages**
2. Set **Source** to **GitHub Actions**
3. The `deploy-pages.yml` workflow handles the rest

---

## Universal repo — full file list

When generating a universal repo, create all of the following:

```
{{github-repo}}/
├── .github/
│   └── workflows/
│       ├── release.yml              ← GitHub Actions release workflow
│       └── deploy-pages.yml         ← GitHub Pages for install button
├── .claude-plugin/
│   └── marketplace.json             ← Claude marketplace wrapper (Codex/ChatGPT honor this too)
├── .cursor-plugin/
│   └── plugin.json                  ← Cursor plugin manifest (root)
├── .agents/
│   ├── plugins/
│   │   └── marketplace.json         ← Native Codex/ChatGPT marketplace
│   └── skills/
│       └── {{skill-name}} → …      ← Symlink for agentskills.io compat
├── {{plugin-name}}/
│   ├── .claude-plugin/
│   │   └── plugin.json              ← Claude plugin manifest (inner)
│   ├── .codex-plugin/
│   │   └── plugin.json              ← Native Codex/ChatGPT plugin manifest
│   └── skills/
│       └── {{skill-name}}/
│           ├── SKILL.md             ← Copied from source
│           ├── VERSION              ← Copied from root VERSION
│           ├── scripts/             ← Copied from source (if exists)
│           ├── references/          ← Copied from source (if exists)
│           ├── assets/              ← Copied from source (if exists)
│           └── agents/              ← Copied from source (if exists)
├── static/
│   └── install-claude-desktop.html  ← One-click install page (GitHub Pages)
├── tools/
│   └── bump-version.py             ← Version propagation script
├── VERSION                          ← Source of truth for version
├── VERSIONING.md                    ← How versioning works
├── CHANGELOG.md                     ← Release notes
├── README.md                        ← With per-platform install instructions
└── LICENSE                          ← License file
```

Generation order:
1. Create directory structure
2. Copy skill files into `{{plugin-name}}/skills/{{skill-name}}/`
3. Generate VERSION file
4. Generate all JSON manifests (Claude plugin, Claude marketplace, Cursor plugin, Codex plugin + Codex marketplace)
5. Generate bump-version.py (make executable: `chmod +x`)
6. Generate release.yml and deploy-pages.yml
7. Generate static/install-claude-desktop.html
8. Create `.agents/skills/` copy (path hygiene applied; not a symlink)
9. Generate VERSIONING.md, CHANGELOG.md, LICENSE
10. Generate README.md (using platforms.md template, include install button badge)
11. Validate all JSON files

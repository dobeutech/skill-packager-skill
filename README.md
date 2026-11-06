# Skill Packager

[![Agent Skills compatible](https://img.shields.io/badge/Agent%20Skills-compatible-blue)](https://agentskills.io)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-green)](https://claude.ai)
[![Cursor plugin](https://img.shields.io/badge/Cursor-plugin-purple)](https://cursor.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Package AI agent skills (directories containing SKILL.md) into deployment-ready formats for distribution across AI platforms: .zip, .skill, Claude plugin/marketplace, Cursor plugin, native Codex/ChatGPT plugin, Agent Skills standard, and a universal repo with CI/CD.

## Installation

### Claude Code
```
/plugin marketplace add dobeutech/skill-packager-skill
/plugin install skill-packager@skill-packager-marketplace
```

### Cursor
Open Cursor Settings → Plugins & MCPs → Add Marketplace → Import from Repo: `https://github.com/dobeutech/skill-packager-skill`

### Any agent (npx)
```
npx skills add dobeutech/skill-packager-skill
```

### Claude Desktop / ChatGPT / others
Download the marketplace zip from Releases or follow platform-specific upload for the skill folder.

## Usage

Invoke with `/skill-packager` or by saying "package this skill", "create a plugin from this skill", or "set up a marketplace repo for my skill".

Provide the path to one or more skill directories. The skill gathers metadata, asks for destinations, scaffolds the output repo with manifests, README, and CI, then validates.

## License

MIT

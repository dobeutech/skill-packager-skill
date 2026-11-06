"""Builders for manifests that need conditional (omit-when-absent) fields.

Flat string templates in templates.py cannot omit keys, so manifests with
optional fields (Codex plugin.json: homepage, interface asset paths) are
assembled here as dicts and JSON-serialized.
"""
import json
from typing import Dict, Set


def build_codex_plugin(tvars: Dict, assets_present: Set) -> str:
    """Build a native Codex/ChatGPT ``.codex-plugin/plugin.json`` string.

    *assets_present* is the subset of {"logo", "composerIcon"} whose backing
    file exists at ``<plugin>/assets/<name>.png``. Asset keys are emitted only
    when present, so the manifest never points at a nonexistent file.

    Schema verified against codex-cli 0.144.4 and OpenAI's shipped plugins:
    the manifest lives at ``<plugin>/.codex-plugin/plugin.json`` and ``skills``
    uses a trailing slash (``"./skills/"``), which differs from Claude's
    ``"./skills"``; ``defaultPrompt`` is a string, not an array.
    """
    manifest: Dict = {
        "name": tvars["plugin_name"],
        "version": tvars["version"],
        "description": tvars["skill_description"],
    }
    if tvars.get("homepage"):
        manifest["homepage"] = tvars["homepage"]
    manifest["repository"] = tvars["repo_url"]
    manifest["license"] = tvars["license"]
    manifest["keywords"] = tvars["keywords"]
    manifest["skills"] = "./skills/"  # trailing slash — Codex convention (not Claude's "./skills")

    interface: Dict = {
        "displayName": tvars["display_name"],
        "shortDescription": tvars["skill_description"],
        "developerName": tvars.get("author_name", ""),
        "category": tvars["category"],
        "brandColor": tvars.get("brand_color", "#6C5CE7"),
        "defaultPrompt": tvars["default_prompt"],
    }
    if tvars.get("homepage"):
        interface["websiteURL"] = tvars["homepage"]
    if "logo" in assets_present:
        interface["logo"] = "./assets/logo.png"
    if "composerIcon" in assets_present:
        interface["composerIcon"] = "./assets/composerIcon.png"

    manifest["interface"] = interface
    return json.dumps(manifest, indent=2) + "\n"

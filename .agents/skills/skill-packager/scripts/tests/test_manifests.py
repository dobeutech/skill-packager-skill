"""Tests for skill_packager.manifests."""
import json

from skill_packager.manifests import build_codex_plugin


def _tvars():
    return {
        "plugin_name": "proof-engine",
        "version": "1.0.0",
        "skill_description": "Create formal proofs",
        "repo_url": "https://github.com/test-owner/proof-engine-skill",
        "license": "MIT",
        "keywords": ["proof", "verification"],
        "display_name": "Proof Engine",
        "category": "development",
        "homepage": "https://github.com/test-owner/proof-engine-skill",
        "brand_color": "#6C5CE7",
        "default_prompt": "Use Proof Engine to verify claims",
        "author_name": "Test Author",
    }


class TestBuildCodexPlugin:
    def test_valid_json_and_core_fields(self):
        data = json.loads(build_codex_plugin(_tvars(), set()))
        assert data["name"] == "proof-engine"
        assert data["version"] == "1.0.0"
        assert data["skills"] == "./skills/"          # trailing slash — Codex convention
        assert data["homepage"] == "https://github.com/test-owner/proof-engine-skill"
        assert data["keywords"] == ["proof", "verification"]

    def test_interface_text_fields(self):
        iface = json.loads(build_codex_plugin(_tvars(), set()))["interface"]
        assert iface["displayName"] == "Proof Engine"
        assert iface["category"] == "development"
        assert iface["websiteURL"] == "https://github.com/test-owner/proof-engine-skill"
        assert iface["brandColor"] == "#6C5CE7"
        assert iface["defaultPrompt"] == "Use Proof Engine to verify claims"
        assert isinstance(iface["defaultPrompt"], str)   # string, not array

    def test_omits_asset_keys_when_absent(self):
        iface = json.loads(build_codex_plugin(_tvars(), set()))["interface"]
        assert "logo" not in iface
        assert "composerIcon" not in iface

    def test_emits_asset_keys_when_present(self):
        iface = json.loads(build_codex_plugin(_tvars(), {"logo", "composerIcon"}))["interface"]
        assert iface["logo"] == "./assets/logo.png"
        assert iface["composerIcon"] == "./assets/composerIcon.png"

    def test_omits_empty_homepage_and_website(self):
        tv = _tvars()
        tv["homepage"] = ""
        data = json.loads(build_codex_plugin(tv, set()))
        assert "homepage" not in data
        assert "websiteURL" not in data["interface"]

    def test_no_literal_braces_in_default_prompt(self):
        data = json.loads(build_codex_plugin(_tvars(), set()))
        assert "{" not in data["interface"]["defaultPrompt"]

"""Guards that the version Home Assistant reports matches the released version.

These two numbers are maintained by different things and silently drifted apart
once already: manifest.json's version was hardcoded to 2.0.0 while release-please
tracked its own line in .release-please-manifest.json, so the installed
integration reported 2.0.0 while HACS saw 0.8.0.

release-please now rewrites manifest.json via the extra-files entry in
release-please-config.json. This test fails if that wiring is ever removed or
if someone hand-edits the version back out of step.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "custom_components" / "spond_tracker" / "manifest.json"
RELEASE_MANIFEST = REPO_ROOT / ".release-please-manifest.json"
RELEASE_CONFIG = REPO_ROOT / "release-please-config.json"


def test_manifest_version_matches_released_version() -> None:
    """The version HA displays must equal the version release-please last cut."""
    manifest_version = json.loads(MANIFEST.read_text())["version"]
    released_version = json.loads(RELEASE_MANIFEST.read_text())["."]

    assert manifest_version == released_version, (
        f"manifest.json reports {manifest_version!r} but the released version is "
        f"{released_version!r}. Home Assistant shows the manifest value, so users "
        f"would see the wrong version. Do not hand-edit it - release-please keeps "
        f"it in sync via the extra-files entry in release-please-config.json."
    )


def test_release_please_updates_the_manifest() -> None:
    """release-please must be configured to rewrite manifest.json on release."""
    config = json.loads(RELEASE_CONFIG.read_text())
    extra_files = config["packages"]["."].get("extra-files", [])

    manifest_rel_path = MANIFEST.relative_to(REPO_ROOT).as_posix()
    targets = [
        entry
        for entry in extra_files
        if isinstance(entry, dict) and entry.get("path") == manifest_rel_path
    ]

    assert targets, (
        f"release-please-config.json has no extra-files entry for {manifest_rel_path}. "
        f"Without it, releases never update the version Home Assistant reports and it "
        f"will drift away from the release tag again."
    )
    assert targets[0].get("jsonpath") == "$.version", (
        f"extra-files entry for {manifest_rel_path} must target '$.version', "
        f"got {targets[0].get('jsonpath')!r}."
    )

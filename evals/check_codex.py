#!/usr/bin/env python3
"""Read-only native parser checks; no inference, login, or global config edits."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from council_checks import ROOT


def run(args):
    return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=45)


def checked(args):
    result = run(args)
    if result.returncode:
        # Deliberately avoid dumping provider config or parent prompt on failure.
        raise RuntimeError("Codex check failed: " + result.stderr[-1200:])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-input-json", type=Path,
                        help="Inspect a previously captured native prompt without rerunning debug")
    options = parser.parse_args()
    codex = shutil.which("codex")
    if not codex:
        raise SystemExit("UNVERIFIED: codex executable unavailable")
    print(checked([codex, "--version"]).stdout.strip())
    root = tomllib.loads((ROOT / ".codex/config.toml").read_text())
    args = [codex, "--strict-config"]
    for key in ("sandbox_mode", "approval_policy"):
        args += ["-c", key + "=" + json.dumps(root[key])]
    for key, value in root["agents"].items():
        args += ["-c", "agents." + key + "=" + json.dumps(value)]
    checked(args + ["app-server", "--print-startup-config"])
    # Unknown-key negative control proves strict parsing is actually active.
    bad = run([codex, "--strict-config", "-c",
               "perspective_council_unknown_key=true", "app-server",
               "--print-startup-config"])
    if bad.returncode == 0:
        raise RuntimeError("strict-config negative control unexpectedly accepted")
    print("PASS: native strict parser accepts root keys and rejects unknown key")
    for path in sorted((ROOT / ".codex/agents").glob("*.toml")):
        agent = tomllib.loads(path.read_text())
        # This checks supported config-layer fields, NOT standalone discovery.
        layer = [codex, "--strict-config", "-c",
                 "model_reasoning_effort=" + json.dumps(agent["model_reasoning_effort"]),
                 "-c", "developer_instructions=" + json.dumps(agent["developer_instructions"])]
        checked(layer + ["app-server", "--print-startup-config"])
    print("PASS: 10 role instruction/reasoning config layers accepted")
    if options.prompt_input_json:
        prompt_text = options.prompt_input_json.read_text()
    else:
        prompt = run([codex, "debug", "prompt-input", "Project maintenance: inspect instructions only."])
        if prompt.returncode:
            print("UNVERIFIED: prompt discovery blocked by local runtime permissions")
            return
        prompt_text = prompt.stdout
    # Never print the parent prompt, which may contain user-specific settings.
    discovered = "Perspective Council — Council Orchestrator" in prompt_text
    descriptions = []

    def inspect(value):
        if isinstance(value, dict):
            if isinstance(value.get("agent_type"), dict):
                descriptions.append(value["agent_type"].get("description", ""))
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)

    inspect(json.loads(prompt_text))
    # Match the native spawn tool's role descriptions, not mentions in AGENTS.md.
    found_agents = [p.stem for p in (ROOT / ".codex/agents").glob("*.toml")
                    if any("\n" + p.stem + ": {\n" in d for d in descriptions)]
    print("AGENTS.md discovery: " + ("PASS" if discovered else "UNVERIFIED"))
    print("Native spawn role descriptions observed: %d/10 (not a spawn test)" % len(found_agents))


if __name__ == "__main__":
    main()

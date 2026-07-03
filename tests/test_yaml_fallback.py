"""Regression tests for the built-in YAML fallback.

The fallback is intentionally a conservative OKF subset, not a full YAML
implementation.  These tests run in a subprocess with
``OKF_LOOM_FORCE_BUILTIN_YAML=1`` so they exercise the fallback even when PyYAML is
installed in the test environment.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap

from conftest import TOOLKIT_ROOT


def test_builtin_yaml_fallback_rejects_unsupported_and_malformed_yaml() -> None:
    """Fallback YAML rejects advanced or ambiguous YAML instead of guessing."""
    code = r'''
from okf_loom import _yaml_compat as yaml

cases = {
    "anchor": "base: &base {x: 1}\n",
    "alias": "copy: *base\n",
    "tag": "x: !foo bar\n",
    "directive": "%YAML 1.2\n---\nx: 1\n",
    "merge": "<<: {x: 1}\n",
    "multi_doc_start": "---\nx: 1\n---\ny: 2\n",
    "multi_doc_end": "x: 1\n...\n",
    "flow_alias": "tags: [*base]\n",
    "flow_anchor": "tags: [&base x]\n",
    "flow_tag": "tags: [!foo]\n",
    "flow_map_alias": "meta: {type: *base}\n",
    "flow_map_tag": "meta: {type: !foo}\n",
    "duplicate_key": "type: Reference\ntype: Tutorial\n",
    "flow_duplicate_key": "meta: {type: Reference, type: Tutorial}\n",
    "unclosed_quote": "title: \"unterminated\n",
    "unbalanced_flow": "tags: [a, {b: c]\n",
}

for name, text in cases.items():
    try:
        yaml.safe_load(text)
    except yaml.YAMLError:
        continue
    raise AssertionError(f"{name} was accepted")

assert yaml.safe_load("type: Reference\ntags: [cli, reference]\n") == {
    "type": "Reference",
    "tags": ["cli", "reference"],
}
'''
    env = os.environ.copy()
    env["OKF_LOOM_FORCE_BUILTIN_YAML"] = "1"
    env["PYTHONPATH"] = str(TOOLKIT_ROOT / "scripts")
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=TOOLKIT_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

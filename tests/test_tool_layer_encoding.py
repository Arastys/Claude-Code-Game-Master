"""The tool layer must survive non-ASCII output on any platform.

Windows consoles default to cp1252. Campaign content is full of em-dashes and
non-ASCII names, and `gm-session.sh context` died with a UnicodeEncodeError
before printing a single line.
"""

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMON_SH = REPO_ROOT / "tools" / "common.sh"


def test_common_sh_forces_utf8_stdio():
    assert "PYTHONIOENCODING=utf-8" in COMMON_SH.read_text(encoding="utf-8")


def test_a_wrapper_can_print_non_ascii_under_a_legacy_codepage(isolated_world_state):
    """Simulate the cp1252 console that broke this."""
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    script = (
        'source "$(dirname "$0")/common.sh"\n'
        '$PYTHON_CMD -c "print(\'Käthe — Y Bedd\')"\n'
    )
    runner = REPO_ROOT / "tools" / "_zz_encoding_probe.sh"
    runner.write_text(script, encoding="utf-8")
    try:
        proc = subprocess.run(["bash", str(runner)], capture_output=True,
                              text=True, encoding="utf-8", env=env,
                              cwd=str(REPO_ROOT))
    finally:
        runner.unlink()
    assert proc.returncode == 0, proc.stderr
    assert "Käthe" in proc.stdout

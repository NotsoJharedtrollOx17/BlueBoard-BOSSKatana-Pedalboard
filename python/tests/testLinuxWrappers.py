import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

repositoryRoot = Path(__file__).resolve().parents[2]


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux Bash wrapper tests")
class LinuxWrapperTests(unittest.TestCase):
    def makeFixture(self, scriptName: str, fakePython: str | None = None):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        shutil.copy2(repositoryRoot / scriptName, root / scriptName)
        python = root / "python" / ".venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text(fakePython or """#!/usr/bin/env bash
if [[ "${1:-}" == "-c" ]]; then
  if [[ "${2:-}" == *"float(sys.argv[1])"* ]]; then printf '30.0\\n'; else printf '1\\n'; fi
  exit 0
fi
printf '%s\\n' "$@" > "$CAPTURE_FILE"
exit "${FAKE_EXIT:-0}"
""", encoding="utf-8")
        python.chmod(0o755)
        config = root / "python" / "config" / "katana-pedalboard.local.json"
        config.parent.mkdir(parents=True)
        config.write_text("{}\n", encoding="utf-8")
        capture = root / "arguments.txt"
        environment = {**os.environ, "CAPTURE_FILE": str(capture)}
        return temporary, root, capture, environment

    def testOnboardingForwardsLinuxProfileOptionsAndExitStatus(self) -> None:
        temporary, root, capture, environment = self.makeFixture("onboardPedalboard.sh")
        self.addCleanup(temporary.cleanup)
        environment["FAKE_EXIT"] = "23"
        completed = subprocess.run(
            ["bash", str(root / "onboardPedalboard.sh"), "--verify-existing", "--debug", "--input", "MIDI 1"],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 23)
        arguments = capture.read_text(encoding="utf-8").splitlines()
        self.assertEqual(arguments[:3], ["-m", "blueboard_macro_handler", "onboard"])
        self.assertIn("--verify-existing", arguments)
        self.assertIn("--debug", arguments)
        self.assertIn("MIDI 1", arguments)

    def testDiagnosticsIsReadOnlyAndPreservesExitStatus(self) -> None:
        temporary, root, capture, environment = self.makeFixture("diagnosePedalboard.sh")
        self.addCleanup(temporary.cleanup)
        environment["FAKE_EXIT"] = "17"
        completed = subprocess.run(
            ["bash", str(root / "diagnosePedalboard.sh"), "--json-logs"],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 17)
        arguments = capture.read_text(encoding="utf-8").splitlines()
        self.assertIn("doctor", arguments)
        self.assertNotIn("--execute-actions", arguments)
        self.assertIn("--json-logs", arguments)

    def testSessionDefaultsToDryRunCreatesJsonlNameAndForwardsOverrides(self) -> None:
        temporary, root, capture, environment = self.makeFixture("recordPedalboardSession.sh")
        self.addCleanup(temporary.cleanup)
        environment["FAKE_EXIT"] = "29"
        logDirectory = root / "session logs"
        completed = subprocess.run(
            [
                "bash", str(root / "recordPedalboardSession.sh"),
                "--duration-minutes", "0.5", "--log-directory", str(logDirectory),
                "--led-feedback", "--name", "iRig BlueBoard",
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 29)
        arguments = capture.read_text(encoding="utf-8").splitlines()
        self.assertNotIn("--execute-actions", arguments)
        self.assertIn("--led-feedback", arguments)
        self.assertIn("30.0", arguments)
        logFile = arguments[arguments.index("--log-file") + 1]
        self.assertRegex(Path(logFile).name, r"^pedalboard-session-\d{8}-\d{6}\.jsonl$")
        self.assertIn("DRY-RUN", completed.stdout)

    def testActiveSessionEnablesOnlyKatanaActions(self) -> None:
        temporary, root, capture, environment = self.makeFixture("recordPedalboardSession.sh")
        self.addCleanup(temporary.cleanup)
        completed = subprocess.run(
            ["bash", str(root / "recordPedalboardSession.sh"), "--active"],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0)
        self.assertIn("--execute-actions", capture.read_text(encoding="utf-8").splitlines())
        self.assertIn("configured Katana actions", completed.stdout)

    def testSessionForwardsTermAndReturnsChildStatus(self) -> None:
        fakePython = """#!/usr/bin/env bash
trap 'exit 77' TERM
printf 'ready\\n' > "$READY_FILE"
while true; do sleep 0.05; done
"""
        temporary, root, _capture, environment = self.makeFixture("recordPedalboardSession.sh", fakePython)
        self.addCleanup(temporary.cleanup)
        ready = root / "ready"
        environment["READY_FILE"] = str(ready)
        process = subprocess.Popen(
            ["bash", str(root / "recordPedalboardSession.sh")],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(ready.exists(), "fake runtime did not start")
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 77, (stdout, stderr))


if __name__ == "__main__":
    unittest.main()

import sys
import types
import unittest
from unittest.mock import patch

from blueboard_macro_handler.linuxDiagnostics import inspectLinuxEnvironment


class LinuxDiagnosticsTests(unittest.TestCase):
    def testQualifiedMintEnvironmentReportsEveryReadOnlyLayer(self) -> None:
        paths = {
            "bluetoothctl": "/usr/bin/bluetoothctl",
            "busctl": "/usr/bin/busctl",
            "systemctl": "/usr/bin/systemctl",
            "gatttool": "/usr/bin/gatttool",
        }

        def run(command, timeout=5.0):
            del timeout
            if command[-1] == "--version":
                return 0, "bluetoothctl: 5.72"
            if "status" in command:
                return 0, "org.bluez"
            if "is-active" in command:
                return 0, "active"
            return 0, "Controller AA:BB test"

        fakeMido = types.SimpleNamespace(
            backend=types.SimpleNamespace(module=types.SimpleNamespace(get_api_names=lambda: ["LINUX_ALSA"]))
        )
        with (
            patch("blueboard_macro_handler.linuxDiagnostics.platform.freedesktop_os_release", return_value={
                "ID": "linuxmint", "VERSION_ID": "22.2", "PRETTY_NAME": "Linux Mint 22.2",
            }),
            patch("blueboard_macro_handler.linuxDiagnostics.platform.machine", return_value="x86_64"),
            patch("blueboard_macro_handler.linuxDiagnostics.platform.release", return_value="7.0.0-test"),
            patch("blueboard_macro_handler.linuxDiagnostics.shutil.which", side_effect=paths.get),
            patch("blueboard_macro_handler.linuxDiagnostics._runReadOnly", side_effect=run),
            patch("blueboard_macro_handler.linuxDiagnostics.Path.exists", return_value=True),
            patch("blueboard_macro_handler.linuxDiagnostics._packageVersion", return_value="test-version"),
            patch.dict(sys.modules, {"mido": fakeMido}),
        ):
            checks = inspectLinuxEnvironment()

        byArea = {check.area: check for check in checks}
        self.assertIn("supported target", byArea["Linux distribution"].message)
        for area in (
            "Architecture", "Kernel", "BlueZ", "BlueZ D-Bus", "BlueZ service",
            "Bluetooth adapter", "BlueBoard compatibility", "ALSA sequencer", "Mido backend",
        ):
            self.assertEqual(byArea[area].status, "PASS", area)

    def testMissingBluezAndAlsaFailClosedWithoutMutatingTheHost(self) -> None:
        fakeMido = types.SimpleNamespace(
            backend=types.SimpleNamespace(module=types.SimpleNamespace(get_api_names=list))
        )
        with (
            patch("blueboard_macro_handler.linuxDiagnostics.platform.freedesktop_os_release", return_value={
                "ID": "ubuntu", "VERSION_ID": "24.04", "PRETTY_NAME": "Ubuntu 24.04",
            }),
            patch("blueboard_macro_handler.linuxDiagnostics.platform.machine", return_value="x86_64"),
            patch("blueboard_macro_handler.linuxDiagnostics.platform.release", return_value="test"),
            patch("blueboard_macro_handler.linuxDiagnostics.shutil.which", return_value=None),
            patch("blueboard_macro_handler.linuxDiagnostics.Path.exists", return_value=False),
            patch("blueboard_macro_handler.linuxDiagnostics._packageVersion", return_value=None),
            patch.dict(sys.modules, {"mido": fakeMido}),
        ):
            checks = inspectLinuxEnvironment()

        failures = {check.area for check in checks if check.status == "FAIL"}
        self.assertTrue({"BlueZ", "Bluetooth adapter", "BlueBoard compatibility", "ALSA sequencer"} <= failures)


if __name__ == "__main__":
    unittest.main()

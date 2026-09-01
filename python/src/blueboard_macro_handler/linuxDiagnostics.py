# ruff: noqa: N999 - retained project camelCase module naming convention.
from __future__ import annotations

import importlib.metadata
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LinuxEnvironmentCheck:
    status: str
    area: str
    message: str


def _runReadOnly(command: tuple[str, ...], timeout: float = 5.0) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)
    output = "\n".join(value.strip() for value in (completed.stdout, completed.stderr) if value.strip())
    return completed.returncode, output


def _distributionCheck() -> LinuxEnvironmentCheck:
    try:
        osRelease = platform.freedesktop_os_release()
    except OSError as error:
        return LinuxEnvironmentCheck("WARN", "Linux distribution", f"could not read os-release: {error}")
    identifier = osRelease.get("ID", "unknown")
    version = osRelease.get("VERSION_ID", "unknown")
    prettyName = osRelease.get("PRETTY_NAME", f"{identifier} {version}")
    if identifier == "linuxmint" and version == "22.2":
        status = "PASS"
        message = f"{prettyName}; v1.0.0 supported target"
    elif identifier in {"linuxmint", "ubuntu"}:
        status = "WARN"
        message = f"{prettyName}; compatible APT-family system, hardware qualification is best-effort"
    else:
        status = "WARN"
        message = f"{prettyName}; outside the v1.0.0 Linux Mint support boundary"
    return LinuxEnvironmentCheck(status, "Linux distribution", message)


def _packageVersion(distributionName: str) -> str | None:
    try:
        return importlib.metadata.version(distributionName)
    except importlib.metadata.PackageNotFoundError:
        return None


def inspectLinuxEnvironment() -> tuple[LinuxEnvironmentCheck, ...]:
    checks = [_distributionCheck()]
    architecture = platform.machine()
    checks.append(LinuxEnvironmentCheck(
        "PASS" if architecture in {"x86_64", "AMD64"} else "FAIL",
        "Architecture",
        architecture,
    ))
    checks.append(LinuxEnvironmentCheck("PASS", "Kernel", platform.release()))

    bluetoothctl = shutil.which("bluetoothctl")
    if bluetoothctl is None:
        checks.append(LinuxEnvironmentCheck("FAIL", "BlueZ", "bluetoothctl is unavailable; install bluez"))
        checks.append(LinuxEnvironmentCheck("FAIL", "Bluetooth adapter", "not checked because BlueZ is unavailable"))
    else:
        versionStatus, versionOutput = _runReadOnly((bluetoothctl, "--version"))
        checks.append(LinuxEnvironmentCheck(
            "PASS" if versionStatus == 0 else "FAIL",
            "BlueZ",
            versionOutput or "version query returned no output",
        ))
        busctl = shutil.which("busctl")
        if busctl is None:
            checks.append(LinuxEnvironmentCheck("WARN", "BlueZ D-Bus", "busctl is unavailable"))
        else:
            busStatus, busOutput = _runReadOnly((busctl, "--system", "status", "org.bluez"))
            checks.append(LinuxEnvironmentCheck(
                "PASS" if busStatus == 0 else "FAIL",
                "BlueZ D-Bus",
                "org.bluez is reachable on the system bus"
                if busStatus == 0
                else (busOutput or "org.bluez is not reachable on the system bus"),
            ))
        serviceTool = shutil.which("systemctl")
        if serviceTool is None:
            checks.append(LinuxEnvironmentCheck("WARN", "BlueZ service", "systemctl is unavailable"))
        else:
            serviceStatus, serviceOutput = _runReadOnly((serviceTool, "is-active", "bluetooth"))
            checks.append(LinuxEnvironmentCheck(
                "PASS" if serviceStatus == 0 and serviceOutput == "active" else "FAIL",
                "BlueZ service",
                serviceOutput or "could not reach the system D-Bus",
            ))
        adapterStatus, adapterOutput = _runReadOnly((bluetoothctl, "list"))
        adapterCount = sum(line.startswith("Controller ") for line in adapterOutput.splitlines())
        checks.append(LinuxEnvironmentCheck(
            "PASS" if adapterStatus == 0 and adapterCount else "FAIL",
            "Bluetooth adapter",
            f"{adapterCount} adapter(s) reported by BlueZ"
            if adapterStatus == 0 and adapterCount
            else (adapterOutput or "no adapter returned; check BlueZ and system D-Bus access"),
        ))

    gatttool = shutil.which("gatttool")
    checks.append(LinuxEnvironmentCheck(
        "PASS" if gatttool else "FAIL",
        "BlueBoard compatibility",
        gatttool or "gatttool is unavailable; the tested BlueZ omitted-service path cannot run",
    ))

    alsaSequencer = Path("/dev/snd/seq")
    checks.append(LinuxEnvironmentCheck(
        "PASS" if alsaSequencer.exists() else "FAIL",
        "ALSA sequencer",
        str(alsaSequencer) if alsaSequencer.exists() else "/dev/snd/seq is unavailable",
    ))

    for distributionName, label in (("bleak", "Bleak"), ("mido", "Mido"), ("python-rtmidi", "python-rtmidi")):
        version = _packageVersion(distributionName)
        checks.append(LinuxEnvironmentCheck(
            "PASS" if version else "FAIL",
            label,
            version or f"{distributionName} is not installed in this environment",
        ))

    try:
        import mido

        apiNames = tuple(mido.backend.module.get_api_names())
        apiMessage = ", ".join(apiNames) or "no RtMidi APIs reported"
        apiReady = "LINUX_ALSA" in apiNames
    except Exception as error:  # noqa: BLE001 - backend import/API errors are environment-specific.
        apiMessage = str(error)
        apiReady = False
    checks.append(LinuxEnvironmentCheck(
        "PASS" if apiReady else "FAIL",
        "Mido backend",
        apiMessage,
    ))
    return tuple(checks)

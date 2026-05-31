#!/usr/bin/env python3
"""Start Blender with the bundled Blender MCP bridge and BlendGraph Tracker enabled.

This script intentionally uses only Python standard library modules.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys


LOGGER_NAME = "start_blender"
ENV_PATHS = ("BLENDER_EXECUTABLE", "BLENDER_BIN", "BLENDER_PATH")
WINDOWS_EXE_NAMES = ("blender.exe", "blender")
POSIX_EXE_NAMES = ("blender",)


class LauncherError(Exception):
    """Raised when Blender cannot be launched."""


def repo_root() -> Path:
    return Path(__file__).resolve().parent


def mcp_startup_script() -> Path:
    return repo_root() / "tools" / "blender_mcp" / "blender_mcp" / "startup.py"


def default_log_file() -> Path:
    return repo_root() / "tools" / "blender_mcp" / "logs" / "start_blender.log"


def configure_logging(log_file: str, verbose: bool) -> logging.Logger:
    resolved = Path(log_file).expanduser().resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(resolved, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(console_handler)

    logger.debug("Logging to %s", resolved)
    return logger


def executable_names() -> tuple[str, ...]:
    return WINDOWS_EXE_NAMES if os.name == "nt" else POSIX_EXE_NAMES


def expand_candidate(value: str):
    raw_path = Path(value).expanduser()
    if not raw_path.is_absolute():
        raw_path = (Path.cwd() / raw_path).resolve()

    if raw_path.is_dir():
        for exe_name in executable_names():
            yield raw_path / exe_name
        if platform.system() == "Darwin":
            yield raw_path / "Contents" / "MacOS" / "Blender"
    else:
        yield raw_path


def unique_paths(paths):
    seen = set()
    for path in paths:
        resolved = Path(path).expanduser()
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        yield resolved


def path_candidates():
    for exe_name in executable_names():
        found = shutil.which(exe_name)
        if found:
            yield Path(found)


def local_build_candidates():
    root = repo_root()
    build_root = root.parent
    build_dirs = (
        build_root / "build_windows",
        build_root / "build_windows_x64_vc17_Release",
        build_root / "build_windows_x64_vc17_Debug",
        build_root / "build_windows_x64_vc17_RelWithDebInfo",
        build_root / "build_windows_x64_vc17_MinSizeRel",
        build_root / "build_windows_x64_vc16_Release",
        build_root / "build_windows_x64_vc16_Debug",
        root / "build",
        root / "out" / "build",
    )
    bin_dirs = ("bin", "bin/Release", "bin/Debug", "bin/RelWithDebInfo", "bin/MinSizeRel")

    for build_dir in build_dirs:
        for bin_dir in bin_dirs:
            for exe_name in executable_names():
                yield build_dir / bin_dir / exe_name


def local_portable_candidates():
    root = repo_root()
    roots = (
        root / "blender-portable",
        root.parent / "blender-portable",
        root / "portable_blender",
        root.parent / "portable_blender",
        Path.home() / "blender-portable",
    )
    child_patterns = ("blender-*", "Blender *", "Blender", "current")

    for base_dir in roots:
        for exe_name in executable_names():
            yield base_dir / exe_name
        for child_pattern in child_patterns:
            for child_dir in base_dir.glob(child_pattern):
                for exe_name in executable_names():
                    yield child_dir / exe_name


def windows_install_candidates():
    if os.name != "nt":
        return
    roots = (
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("LOCALAPPDATA"),
    )
    for root_value in roots:
        if not root_value:
            continue
        root = Path(root_value)
        yield root / "Blender Foundation" / "Blender" / "blender.exe"
        for path in (root / "Blender Foundation").glob("Blender *"):
            yield path / "blender.exe"

    for steam_root in (
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Steam",
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Steam",
    ):
        yield steam_root / "steamapps" / "common" / "Blender" / "blender.exe"


def macos_install_candidates():
    if platform.system() != "Darwin":
        return
    yield Path("/Applications/Blender.app/Contents/MacOS/Blender")
    for path in Path("/Applications").glob("Blender*.app"):
        yield path / "Contents" / "MacOS" / "Blender"


def resolve_blender(cli_path: str | None, logger: logging.Logger) -> Path:
    if cli_path:
        for candidate in unique_paths(expand_candidate(cli_path)):
            logger.debug("Checking --blender candidate: %s", candidate)
            if candidate.is_file():
                return candidate
        raise LauncherError(f"--blender did not point to an executable file: {cli_path}")

    for env_name in ENV_PATHS:
        env_value = os.environ.get(env_name)
        if not env_value:
            continue
        for candidate in unique_paths(expand_candidate(env_value)):
            logger.debug("Checking %s candidate: %s", env_name, candidate)
            if candidate.is_file():
                return candidate
        logger.warning("%s is set but no Blender executable was found there: %s", env_name, env_value)

    searches = (
        path_candidates(),
        local_build_candidates(),
        local_portable_candidates(),
        windows_install_candidates() or (),
        macos_install_candidates() or (),
    )
    checked = []
    for search in searches:
        for candidate in unique_paths(search):
            checked.append(candidate)
            logger.debug("Checking candidate: %s", candidate)
            if candidate.is_file():
                return candidate

    checked_text = "\n".join(f"  - {path}" for path in checked[:60])
    if len(checked) > 60:
        checked_text += f"\n  - ... {len(checked) - 60} more"
    raise LauncherError(
        "No Blender executable was found. Pass --blender PATH or set BLENDER_EXECUTABLE.\n"
        f"Checked:\n{checked_text}"
    )


def command_to_string(command: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return shlex.join(command)


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Start Blender with the Blender MCP bridge and BlendGraph Tracker enabled.",
    )
    parser.add_argument("--blender", help="Path to blender.exe or a directory containing it.")
    parser.add_argument("--background", action="store_true", help="Run Blender headless.")
    parser.add_argument("--wait", action="store_true", help="Wait for Blender to exit.")
    parser.add_argument("--timeout", type=float, help="Seconds to wait when --wait is used.")
    parser.add_argument("--port", type=int, default=8765, help="MCP bridge TCP port.")
    parser.add_argument("--host", default="127.0.0.1", help="MCP bridge TCP host.")
    parser.add_argument("--cwd", help="Working directory for Blender.")
    parser.add_argument("--log-file", default=str(default_log_file()), help="Launcher log file.")
    parser.add_argument("--dry-run", action="store_true", help="Print the Blender command without starting it.")
    parser.add_argument("--verbose", action="store_true", help="Print debug logs to the console.")
    args, blender_args = parser.parse_known_args(argv)
    if blender_args and blender_args[0] == "--":
        blender_args = blender_args[1:]
    return args, blender_args


def main(argv: list[str]) -> int:
    args, blender_args = parse_args(argv)
    logger = configure_logging(args.log_file, args.verbose)
    logger.info("Blender MCP and BlendGraph Tracker launcher started.")

    try:
        startup_script = mcp_startup_script()
        if not startup_script.is_file():
            raise LauncherError(f"MCP startup script was not found: {startup_script}")

        blender_path = resolve_blender(args.blender, logger)
        command = [str(blender_path)]
        if args.background:
            command.append("--background")
        command.extend(["--python", str(startup_script)])
        command.extend(blender_args)

        env = os.environ.copy()
        env["BLENDER_MCP_HOST"] = args.host
        env["BLENDER_MCP_PORT"] = str(args.port)

        cwd = Path(args.cwd).expanduser().resolve() if args.cwd else repo_root()
        logger.info("Command: %s", command_to_string(command))
        logger.info("Working directory: %s", cwd)
        logger.info("MCP bridge: %s:%s", args.host, args.port)

        if args.dry_run:
            logger.info("Dry run enabled; Blender was not launched.")
            return 0

        if args.wait:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=args.timeout,
            )
            if completed.stdout:
                for line in completed.stdout.splitlines():
                    logger.info("Blender output: %s", line)
            logger.info("Blender exited with code %s", completed.returncode)
            return completed.returncode

        process = subprocess.Popen(command, cwd=str(cwd), env=env)
        logger.info("Blender started with process id %s", process.pid)
        return 0
    except subprocess.TimeoutExpired as exc:
        logger.error("Blender timed out after %s seconds.", exc.timeout)
        return 124
    except (OSError, LauncherError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

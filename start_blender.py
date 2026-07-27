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
    return repo_root() / "logs" / "start_blender.log"


def ensure_submodules(logger: logging.Logger) -> Path:
    startup_script = mcp_startup_script()
    if startup_script.is_file():
        return startup_script

    logger.info("MCP startup script not found. Attempting to initialize git submodules...")
    git_bin = shutil.which("git")
    if git_bin:
        try:
            res = subprocess.run(
                [
                    git_bin,
                    "submodule",
                    "update",
                    "--init",
                    "--recursive",
                    "tools/blender_mcp",
                    "tools/blender_graph_tracker",
                    "tools/blender_read_mode",
                ],
                cwd=str(repo_root()),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if res.returncode == 0 and startup_script.is_file():
                logger.info("Git submodules initialized successfully.")
                return startup_script
        except Exception as exc:
            logger.debug("Failed to run git submodule update: %s", exc)

    raise LauncherError(
        f"MCP startup script was not found: {startup_script}\n"
        "Please initialize git submodules by running:\n"
        "  git submodule update --init --recursive tools/blender_mcp tools/blender_graph_tracker tools/blender_read_mode"
    )


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


def cmake_bin_candidates() -> list[Path]:
    root = repo_root()
    search_dirs = (
        root.parent,
        root,
        root.parent / "cmake",
        Path.home(),
    )
    patterns = ("cmake-*", "CMake-*", "cmake", "CMake")
    candidates = []

    existing_cmake = shutil.which("cmake")
    if existing_cmake:
        candidates.append(Path(existing_cmake).parent)

    for base in search_dirs:
        if not base.is_dir():
            continue
        for pattern in patterns:
            for match in base.glob(pattern):
                if match.is_dir():
                    bin_dir = match / "bin"
                    exe_name = "cmake.exe" if os.name == "nt" else "cmake"
                    if (bin_dir / exe_name).is_file():
                        candidates.append(bin_dir)
                    elif (match / exe_name).is_file():
                        candidates.append(match)

    return list(unique_paths(candidates))


def prepare_build_env(logger: logging.Logger) -> dict[str, str]:
    env = os.environ.copy()
    existing_cmake = shutil.which("cmake", path=env.get("PATH"))
    if not existing_cmake:
        candidates = cmake_bin_candidates()
        if candidates:
            cmake_dir = candidates[0]
            logger.info("Found CMake at: %s (adding to PATH)", cmake_dir)
            env["PATH"] = str(cmake_dir) + os.pathsep + env.get("PATH", "")
        else:
            logger.warning("No CMake installation found in PATH or adjacent directories.")
    return env


def detect_vs_build_tools_arg() -> list[str]:
    if os.name != "nt":
        return []
    vswhere = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if vswhere.is_file():
        try:
            res_ide = subprocess.run(
                [str(vswhere), "-latest", "-version", "[17.0,18.0)", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            if not res_ide.stdout.strip():
                res_bt = subprocess.run(
                    [str(vswhere), "-latest", "-products", "Microsoft.VisualStudio.Product.BuildTools", "-version", "[17.0,18.0)", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if res_bt.stdout.strip():
                    return ["2022b"]
        except Exception:
            pass
    return []


def vs_install_path() -> Path | None:
    """Locate the latest Visual Studio 2022 installation directory via vswhere.

    Returns the ``installationPath`` (e.g. ``C:\\Program Files\\Microsoft Visual Studio\\2022\\Community``)
    or ``None`` if VS 2022 with the VC tools is not installed.
    """
    if os.name != "nt":
        return None
    vswhere = Path(
        os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")
    ) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        return None
    try:
        res = subprocess.run(
            [
                str(vswhere),
                "-latest",
                "-version", "[17.0,18.0)",
                "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property", "installationPath",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        path = res.stdout.strip()
        if not path:
            # Fall back to Build Tools product if the IDE is not installed.
            res = subprocess.run(
                [
                    str(vswhere),
                    "-latest",
                    "-products", "Microsoft.VisualStudio.Product.BuildTools",
                    "-version", "[17.0,18.0)",
                    "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                    "-property", "installationPath",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            path = res.stdout.strip()
        return Path(path) if path else None
    except Exception:
        return None


def prepare_run_env(logger: logging.Logger) -> dict[str, str]:
    """Build the environment for the launched Blender process.

    On Windows, when Visual Studio 2022 is detected, this captures the MSVC
    toolchain environment (``cl.exe`` + Windows SDK on ``PATH``) by running
    ``vcvars64.bat`` and merges it into ``os.environ.copy()``. This lets
    Cycles' ``nvcc`` CUDA JIT find ``cl.exe`` at render time without the user
    having to launch Blender from a Developer Command Prompt.

    On non-Windows or when VS is not found, returns ``os.environ.copy()``
    unchanged (no-op).
    """
    env = os.environ.copy()
    if os.name != "nt":
        return env
    vs_root = vs_install_path()
    if vs_root is None:
        logger.warning(
            "Visual Studio 2022 not detected; Cycles CUDA JIT (nvcc) may fail to "
            "find cl.exe. Launch from a Developer Command Prompt or install VS Build Tools."
        )
        return env
    vcvars = vs_root / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    if not vcvars.is_file():
        logger.warning("vcvars64.bat not found at %s; skipping MSVC env injection.", vcvars)
        return env
    try:
        # Run vcvars64.bat and dump the resulting environment as KEY=VALUE lines.
        # Use shell=True so cmd.exe receives the command string verbatim (passing
        # a list makes subprocess.list2cmdline add extra quotes that confuse
        # cmd's quote-stripping rules). `call` lets cmd handle the quoted path.
        res = subprocess.run(
            f'call "{vcvars}" >nul && set',
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        if res.returncode != 0:
            logger.warning("vcvars64.bat exited %s; skipping MSVC env injection. stderr: %s",
                            res.returncode, res.stderr.strip())
            return env
        # Merge the vcvars environment. PATH is merged with os.pathsep so the
        # MSVC bin dirs are prepended (taking precedence) while preserving the
        # existing PATH. Other vars (INCLUDE, LIB, etc.) are set from vcvars.
        # Windows env vars are case-insensitive; `set` may emit `Path` while the
        # parent process has `PATH`. Preserve the existing key casing to avoid
        # creating duplicate (case-variant) entries that confuse CreateProcess.
        existing_path_key = next((k for k in env if k.lower() == "path"), "PATH")
        for line in res.stdout.splitlines():
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.lower() == "path":
                env[existing_path_key] = value + os.pathsep + env.get(existing_path_key, "")
            else:
                env[key] = value
        cl_exe = shutil.which("cl.exe", path=env.get(existing_path_key))
        if cl_exe:
            logger.info("MSVC cl.exe env injected for Cycles CUDA JIT (cl.exe at %s)", cl_exe)
        else:
            logger.warning("MSVC env applied but cl.exe still not found on PATH.")
        return env
    except subprocess.TimeoutExpired:
        logger.warning("vcvars64.bat timed out; skipping MSVC env injection.")
        return env
    except Exception as exc:
        logger.warning("Failed to capture MSVC env (%s); skipping injection.", exc)
        return env


def trigger_build(logger: logging.Logger, dry_run: bool = False) -> None:
    logger.info("No Blender executable found. Attempting to build Blender...")
    root = repo_root()
    if os.name == "nt":
        make_bat = root / "make.bat"
        if not make_bat.is_file():
            raise LauncherError(f"Cannot build Blender: {make_bat} was not found.")
        command = ["cmd.exe", "/c", str(make_bat)] + detect_vs_build_tools_arg()
    else:
        make_bin = shutil.which("make")
        if make_bin:
            command = [make_bin]
        else:
            make_bat = root / "make.bat"
            if make_bat.is_file():
                command = [str(make_bat)]
            else:
                raise LauncherError("Cannot build Blender: 'make' command was not found.")

    env = prepare_build_env(logger)

    logger.info("Build command: %s", command_to_string(command))
    if dry_run:
        logger.info("Dry run enabled; Blender build was not executed.")
        return

    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            env=env,
            text=True,
        )
        if completed.returncode != 0:
            raise LauncherError(f"Blender build failed with return code {completed.returncode}.")
    except Exception as exc:
        if isinstance(exc, LauncherError):
            raise
        raise LauncherError(f"Failed to execute Blender build: {exc}")


def resolve_blender(
    cli_path: str | None,
    logger: logging.Logger,
    allow_build: bool = True,
    dry_run: bool = False,
) -> Path:
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

    def find_existing() -> tuple[Path | None, list[Path]]:
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
                    return candidate, checked
        return None, checked

    found, checked = find_existing()
    if found:
        return found

    if allow_build:
        trigger_build(logger, dry_run=dry_run)
        if dry_run:
            return repo_root().parent / "build_windows" / "bin" / "Release" / "blender.exe"
        found_after_build, checked_after_build = find_existing()
        if found_after_build:
            return found_after_build
        checked.extend(checked_after_build)

    checked_text = "\n".join(f"  - {path}" for path in checked[:60])
    if len(checked) > 60:
        checked_text += f"\n  - ... {len(checked) - 60} more"
    raise LauncherError(
        "No Blender executable was found and building did not produce a binary.\n"
        "Pass --blender PATH or set BLENDER_EXECUTABLE.\n"
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
    parser.add_argument("--build", action="store_true", help="Force building Blender before starting.")
    parser.add_argument("--no-build", action="store_true", help="Do not automatically build Blender if no executable is found.")
    parser.add_argument(
        "--no-msvc-env",
        action="store_true",
        help="Do not inject the MSVC (cl.exe) environment into the launched Blender. "
             "By default the launcher captures vcvars64.bat so Cycles CUDA JIT (nvcc) can find cl.exe.",
    )
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
        startup_script = ensure_submodules(logger)
        if args.build and not args.dry_run:
            trigger_build(logger, dry_run=args.dry_run)
        blender_path = resolve_blender(
            args.blender,
            logger,
            allow_build=not args.no_build,
            dry_run=args.dry_run,
        )
        command = [str(blender_path)]
        if args.background:
            command.append("--background")
        command.extend(["--python", str(startup_script)])
        command.extend(blender_args)

        if not args.no_msvc_env:
            env = prepare_run_env(logger)
        else:
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

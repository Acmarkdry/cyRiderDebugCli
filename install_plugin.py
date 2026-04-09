#!/usr/bin/env python3
"""One-click installer for the Rider Debug MCP Bridge plugin.

Usage:
    python install_plugin.py

What it does:
    1. Finds Rider installation (for JBR / JDK and IDE JARs)
    2. Compiles the plugin Java source using Rider's bundled JDK
    3. Packages into a proper plugin directory structure
    4. Installs to Rider's plugins directory
    5. Done — restart Rider

No Gradle, no external JDK, no downloads needed.
"""

import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

PLUGIN_ID = "rider-debug-mcp-plugin"
SCRIPT_DIR = Path(__file__).parent.resolve()
PLUGIN_SRC = SCRIPT_DIR / "rider-plugin"
JAVA_SRC = PLUGIN_SRC / "src" / "main" / "java"
RESOURCES_DIR = PLUGIN_SRC / "src" / "main" / "resources"


def find_rider_install_dir() -> Path | None:
    """Find the Rider IDE installation directory."""
    system = platform.system()

    if system == "Windows":
        search_roots = [
            Path("C:/Program Files/JetBrains"),
            Path("C:/Program Files (x86)/JetBrains"),
            Path.home() / "AppData" / "Local" / "JetBrains" / "Toolbox" / "apps",
        ]
    elif system == "Darwin":
        search_roots = [
            Path("/Applications"),
            Path.home() / "Applications",
        ]
    else:
        search_roots = [
            Path.home() / ".local" / "share" / "JetBrains" / "Toolbox" / "apps",
            Path("/opt/JetBrains"),
            Path("/snap/rider/current"),
        ]

    for root in search_roots:
        if not root.exists():
            continue
        # Find directories matching Rider pattern
        candidates = []
        for d in root.iterdir():
            name = d.name.lower()
            if d.is_dir() and "rider" in name:
                # Check for jbr inside
                if (d / "jbr" / "bin").exists():
                    candidates.append(d)
                # Toolbox nested structure
                for sub in d.iterdir():
                    if sub.is_dir() and (sub / "jbr" / "bin").exists():
                        candidates.append(sub)

        if candidates:
            candidates.sort(key=lambda d: d.name, reverse=True)
            return candidates[0]

    return None


def find_rider_plugins_dir() -> Path | None:
    """Find the Rider user plugins directory."""
    system = platform.system()

    if system == "Windows":
        base = Path(os.environ.get("APPDATA", "")) / "JetBrains"
        if not base.exists():
            base = Path.home() / "AppData" / "Roaming" / "JetBrains"
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "JetBrains"
    else:
        base = Path.home() / ".local" / "share" / "JetBrains"

    if not base.exists():
        return None

    rider_dirs = sorted(
        [d for d in base.iterdir() if d.is_dir() and d.name.startswith("Rider")],
        key=lambda d: d.name, reverse=True,
    )
    if not rider_dirs:
        return None

    plugins_dir = rider_dirs[0] / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Rider config: {rider_dirs[0].name}")
    return plugins_dir


def find_jbr_javac(rider_dir: Path) -> Path | None:
    """Find javac in Rider's bundled JBR."""
    ext = ".exe" if platform.system() == "Windows" else ""
    javac = rider_dir / "jbr" / "bin" / f"javac{ext}"
    if javac.exists():
        return javac
    # Some distributions
    javac = rider_dir / "jbr" / "bin" / f"javac{ext}"
    return javac if javac.exists() else None


def find_ide_classpath(rider_dir: Path) -> list[Path]:
    """Collect the JARs needed to compile against IntelliJ Platform APIs."""
    lib_dir = rider_dir / "lib"
    needed_patterns = [
        "platform-api*", "platform-impl*", "util*",
        "app*", "openapi*", "extensions*",
        "netty-*", "gson-*", "kotlin-stdlib*",
        "jps-model*", "xdebugger-api*", "xdebugger-impl*",
        "execution-*", "indexing-api*",
    ]
    jars = []

    if lib_dir.exists():
        for jar in lib_dir.glob("*.jar"):
            jars.append(jar)

    # Also add modules dir
    modules_dir = rider_dir / "lib" / "modules"
    if modules_dir.exists():
        for jar in modules_dir.glob("*.jar"):
            jars.append(jar)

    # Plugins dir for xdebugger
    plugins_dir = rider_dir / "plugins"
    if plugins_dir.exists():
        for jar in plugins_dir.rglob("*.jar"):
            jars.append(jar)

    return jars


def compile_java(javac: Path, jars: list[Path], src_dir: Path, out_dir: Path) -> bool:
    """Compile Java source files using the found javac.

    Uses @argfile to avoid Windows command line length limits.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    java_files = list(src_dir.rglob("*.java"))
    if not java_files:
        print("  ❌ No .java source files found!")
        return False

    classpath = os.pathsep.join(str(j) for j in jars)

    # Write args to a temp file to avoid Windows 32k char limit
    argfile = PLUGIN_SRC / "build" / "_javac_args.txt"
    argfile.parent.mkdir(parents=True, exist_ok=True)
    # javac @argfile treats backslashes as escape chars, so use forward slashes
    def fwd(p: Path | str) -> str:
        return str(p).replace("\\", "/")

    with open(argfile, "w", encoding="utf-8") as f:
        f.write(f'-d\n"{fwd(out_dir)}"\n')
        f.write(f'-cp\n"{fwd(classpath)}"\n')
        f.write("-source\n17\n")
        f.write("-target\n17\n")
        f.write("-encoding\nUTF-8\n")
        f.write("-nowarn\n")
        for jf in java_files:
            f.write(f'"{fwd(jf)}"\n')

    cmd = [str(javac), f"@{argfile}"]

    print(f"  Compiling {len(java_files)} source file(s)...")
    result = subprocess.run(cmd, capture_output=True, timeout=120)

    # Cleanup argfile
    try:
        argfile.unlink()
    except OSError:
        pass

    if result.returncode != 0:
        print("  ❌ Compilation failed:")
        stderr = ""
        for encoding in ("utf-8", "gbk", "cp1252", "latin-1"):
            try:
                stderr = result.stderr.decode(encoding) if result.stderr else ""
                break
            except (UnicodeDecodeError, AttributeError):
                continue
        stdout = ""
        for encoding in ("utf-8", "gbk", "cp1252", "latin-1"):
            try:
                stdout = result.stdout.decode(encoding) if result.stdout else ""
                break
            except (UnicodeDecodeError, AttributeError):
                continue
        if stderr:
            print(stderr[:2000])
        if stdout:
            print(stdout[:2000])
        return False

    return True


def package_plugin(out_dir: Path, resources_dir: Path, target_dir: Path) -> Path:
    """Package compiled classes + resources into plugin directory structure."""
    plugin_dir = target_dir / PLUGIN_ID
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)

    lib_dir = plugin_dir / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)

    # Create JAR
    jar_path = lib_dir / f"{PLUGIN_ID}.jar"
    with zipfile.ZipFile(str(jar_path), "w", zipfile.ZIP_DEFLATED) as zf:
        # Add compiled classes
        for class_file in out_dir.rglob("*.class"):
            arcname = class_file.relative_to(out_dir).as_posix()
            zf.write(str(class_file), arcname)

        # Add resources (plugin.xml etc)
        if resources_dir.exists():
            for res in resources_dir.rglob("*"):
                if res.is_file():
                    arcname = res.relative_to(resources_dir).as_posix()
                    zf.write(str(res), arcname)

    return plugin_dir


def main():
    print("🔌 Rider Debug MCP Plugin Installer")
    print("=" * 40)

    # Step 1: Find Rider IDE installation
    print("\n🔍 Finding Rider IDE installation...")
    rider_dir = find_rider_install_dir()
    if not rider_dir:
        print("  ❌ Rider IDE not found!")
        print("     Install JetBrains Rider and try again.")
        sys.exit(1)
    print(f"  ✅ Rider: {rider_dir.name}")

    # Step 2: Find JBR javac
    print("\n🔍 Finding Rider's bundled JDK...")
    javac = find_jbr_javac(rider_dir)
    if not javac:
        print("  ❌ javac not found in Rider's JBR!")
        sys.exit(1)
    print(f"  ✅ javac: {javac}")

    # Step 3: Find plugins dir
    print("\n🔍 Finding Rider plugins directory...")
    plugins_dir = find_rider_plugins_dir()
    if not plugins_dir:
        print("  ❌ Rider config directory not found!")
        sys.exit(1)
    print(f"  📁 Plugins: {plugins_dir}")

    # Step 4: Check source exists
    if not JAVA_SRC.exists():
        print(f"\n  ❌ Java source not found at {JAVA_SRC}")
        sys.exit(1)

    # Step 5: Collect classpath
    print("\n📚 Collecting IDE libraries...")
    jars = find_ide_classpath(rider_dir)
    print(f"  Found {len(jars)} JARs in classpath")

    # Step 6: Compile
    print("\n🔨 Compiling plugin...")
    build_dir = PLUGIN_SRC / "build" / "classes"
    if build_dir.exists():
        shutil.rmtree(build_dir)

    if not compile_java(javac, jars, JAVA_SRC, build_dir):
        print("\n❌ Build failed. Check source code for errors.")
        sys.exit(1)
    print("  ✅ Compiled successfully")

    # Step 7: Package & install
    print("\n� Packaging and installing...")
    plugin_dir = package_plugin(build_dir, RESOURCES_DIR, plugins_dir)
    print(f"  ✅ Installed to: {plugin_dir}")

    # Done
    print("\n" + "=" * 40)
    print("✅ Installation complete!")
    print()
    print("👉 Next steps:")
    print("   1. Restart Rider")
    print("   2. The plugin auto-activates (no config needed)")
    print("   3. Run: python -m rider_debug_mcp")
    print()
    print("   Verify: http://localhost:63342/api/rider-debug-mcp/status")


if __name__ == "__main__":
    main()
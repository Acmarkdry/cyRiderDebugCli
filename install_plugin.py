#!/usr/bin/env python3
"""One-click installer for the Rider Debug MCP Bridge plugin.

Usage:
    python install_plugin.py          # Auto-detect Rider and install
    python install_plugin.py --build  # Build from source then install

What it does:
    1. Finds your Rider plugins directory
    2. Copies the pre-built plugin JAR (or builds it first with --build)
    3. Tells you to restart Rider

That's it. No Gradle needed for normal installs.
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_ID = "rider-debug-mcp-plugin"
SCRIPT_DIR = Path(__file__).parent.resolve()
PLUGIN_SRC = SCRIPT_DIR / "rider-plugin"
PREBUILT_DIR = SCRIPT_DIR / "rider-plugin" / "prebuilt"


def find_rider_plugins_dir() -> Path | None:
    """Find the Rider plugins directory for the current OS."""
    system = platform.system()

    if system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            base = Path(appdata) / "JetBrains"
        else:
            base = Path.home() / "AppData" / "Roaming" / "JetBrains"
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "JetBrains"
    else:  # Linux
        base = Path.home() / ".local" / "share" / "JetBrains"

    if not base.exists():
        return None

    # Find Rider directories, sorted newest first
    rider_dirs = sorted(
        [d for d in base.iterdir() if d.is_dir() and d.name.startswith("Rider")],
        key=lambda d: d.name,
        reverse=True,
    )

    if not rider_dirs:
        return None

    plugins_dir = rider_dirs[0] / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Found Rider config: {rider_dirs[0].name}")
    return plugins_dir


def find_prebuilt_jar() -> Path | None:
    """Find a pre-built plugin JAR."""
    if PREBUILT_DIR.exists():
        jars = list(PREBUILT_DIR.glob("*.jar"))
        if jars:
            return jars[0]

    # Also check build output
    dist_dir = PLUGIN_SRC / "build" / "distributions"
    if dist_dir.exists():
        zips = list(dist_dir.glob("*.zip"))
        if zips:
            return zips[0]

    return None


def build_plugin() -> Path | None:
    """Build the plugin from source using Gradle."""
    print("\n📦 Building plugin from source...")

    if not (PLUGIN_SRC / "build.gradle.kts").exists():
        print("  ❌ rider-plugin/build.gradle.kts not found!")
        return None

    # Check for Gradle wrapper or system Gradle
    gradlew = PLUGIN_SRC / ("gradlew.bat" if platform.system() == "Windows" else "gradlew")
    if gradlew.exists():
        cmd = [str(gradlew), "buildPlugin"]
    else:
        cmd = ["gradle", "buildPlugin"]

    try:
        result = subprocess.run(
            cmd, cwd=str(PLUGIN_SRC), capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            print(f"  ❌ Build failed:\n{result.stderr[:500]}")
            return None
    except FileNotFoundError:
        print("  ❌ Gradle not found. Install Gradle or use the Gradle wrapper.")
        print("     Run: cd rider-plugin && gradle wrapper")
        return None
    except subprocess.TimeoutExpired:
        print("  ❌ Build timed out (5 min)")
        return None

    dist_dir = PLUGIN_SRC / "build" / "distributions"
    zips = list(dist_dir.glob("*.zip"))
    if zips:
        print(f"  ✅ Built: {zips[0].name}")
        return zips[0]

    # Try lib dir for JAR
    lib_dir = PLUGIN_SRC / "build" / "libs"
    jars = list(lib_dir.glob("*.jar"))
    if jars:
        print(f"  ✅ Built: {jars[0].name}")
        return jars[0]

    print("  ❌ Build succeeded but no output found")
    return None


def install_plugin(artifact: Path, plugins_dir: Path) -> bool:
    """Install the plugin artifact to the Rider plugins directory."""
    target = plugins_dir / PLUGIN_ID

    # Clean old install
    if target.exists():
        print(f"  Removing old installation...")
        shutil.rmtree(target)

    if artifact.suffix == ".zip":
        print(f"  Extracting {artifact.name}...")
        shutil.unpack_archive(str(artifact), str(plugins_dir))
        # Rename extracted dir if needed
        extracted = [d for d in plugins_dir.iterdir() if d.is_dir() and d.name != PLUGIN_ID and "rider-debug" in d.name.lower()]
        if extracted:
            extracted[0].rename(target)
    elif artifact.suffix == ".jar":
        target.mkdir(parents=True, exist_ok=True)
        lib_dir = target / "lib"
        lib_dir.mkdir(exist_ok=True)
        shutil.copy2(str(artifact), str(lib_dir / artifact.name))
    else:
        print(f"  ❌ Unknown artifact type: {artifact.suffix}")
        return False

    return True


def main():
    build_first = "--build" in sys.argv

    print("🔌 Rider Debug MCP Plugin Installer")
    print("=" * 40)

    # Step 1: Find Rider
    print("\n🔍 Finding Rider installation...")
    plugins_dir = find_rider_plugins_dir()
    if not plugins_dir:
        print("  ❌ Rider not found! Please install JetBrains Rider first.")
        print("     Or manually install the plugin:")
        print("     Rider → Settings → Plugins → ⚙ → Install from Disk")
        sys.exit(1)
    print(f"  📁 Plugins dir: {plugins_dir}")

    # Step 2: Get the plugin artifact
    artifact = None
    if build_first:
        artifact = build_plugin()
    else:
        artifact = find_prebuilt_jar()
        if not artifact:
            print("\n📦 No pre-built plugin found, building from source...")
            artifact = build_plugin()

    if not artifact:
        print("\n❌ Could not get plugin artifact.")
        print("   Try building manually:")
        print("     cd rider-plugin")
        print("     gradle buildPlugin")
        print("   Then run this script again.")
        sys.exit(1)

    # Step 3: Install
    print(f"\n📥 Installing plugin...")
    if install_plugin(artifact, plugins_dir):
        print(f"  ✅ Installed to: {plugins_dir / PLUGIN_ID}")
    else:
        print("  ❌ Installation failed")
        sys.exit(1)

    # Step 4: Done!
    print("\n" + "=" * 40)
    print("✅ Installation complete!")
    print("")
    print("👉 Next steps:")
    print("   1. Restart Rider")
    print("   2. The plugin auto-activates (no config needed)")
    print("   3. Run: python -m rider_debug_mcp")
    print("")
    print("   To verify: open http://localhost:63342/api/rider-debug-mcp/status")
    print("   in your browser after restarting Rider.")


if __name__ == "__main__":
    main()

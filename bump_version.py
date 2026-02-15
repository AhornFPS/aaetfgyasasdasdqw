"""
Helper script for build-windows.bat to bump the version in version.py.
Usage: python bump_version.py <choice>
  choice: 1=patch, 2=minor, 3=major, 4=skip
"""
import sys

def bump():
    choice = sys.argv[1] if len(sys.argv) > 1 else "1"

    # Read current version
    with open("version.py", "r") as f:
        content = f.read()

    # Extract version
    for line in content.splitlines():
        if line.startswith("VERSION"):
            current = line.split('"')[1]
            break
    else:
        print("ERROR: Could not find VERSION in version.py")
        sys.exit(1)

    parts = current.split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

    if choice == "2":
        minor += 1
        patch = 0
    elif choice == "3":
        major += 1
        minor = 0
        patch = 0
    elif choice == "4":
        pass  # Skip
    else:
        patch += 1

    new_ver = f"{major}.{minor}.{patch}"

    # Write back
    with open("version.py", "w") as f:
        f.write('"""\n')
        f.write("Single source of truth for the application version.\n")
        f.write("Updated automatically by build script (build-windows.bat).\n")
        f.write("Format: MAJOR.MINOR.PATCH\n")
        f.write('"""\n')
        f.write(f'VERSION = "{new_ver}"\n')

    print(new_ver)

if __name__ == "__main__":
    bump()

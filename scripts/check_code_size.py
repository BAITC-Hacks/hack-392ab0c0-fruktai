"""Guard readable source modules: maximum 350 physical lines, including blanks."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_LINES = 350
SOURCE_DIRS = (
    "agent",
    "backend",
    "database",
    "scripts",
    "tests",
    "frontend/src",
    "frontend/scripts",
    "frontend/e2e",
)
EXTENSIONS = {".py", ".ts", ".tsx", ".mjs", ".css", ".sql"}
IGNORED_DIRS = {"__pycache__", "node_modules", ".venv", "venv", "dist", "build"}


def source_files(root: Path = ROOT) -> list[Path]:
    files = set((root / "frontend").glob("*.ts"))
    for folder in SOURCE_DIRS:
        for path in (root / folder).rglob("*"):
            if (
                path.is_file()
                and path.suffix in EXTENSIONS
                and not IGNORED_DIRS.intersection(path.relative_to(root).parts)
            ):
                files.add(path)
    return sorted(files)


def main() -> None:
    sizes = [
        (len(path.read_text(encoding="utf-8-sig").splitlines()), path) for path in source_files()
    ]
    oversized = [(count, path) for count, path in sizes if count > MAX_LINES]
    for count, path in oversized:
        print(f"{path.relative_to(ROOT)}: {count} lines (limit {MAX_LINES})")
    if oversized:
        raise SystemExit(1)
    largest, path = max(sizes)
    print(
        f"Source size: OK ({len(sizes)} files, largest {largest} lines: {path.relative_to(ROOT)})"
    )


if __name__ == "__main__":
    main()

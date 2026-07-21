#!/usr/bin/env python3
"""Create a JLCEDA-oriented PCB project skeleton."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import sys


VALID_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
SKILL_ROOT = Path(__file__).resolve().parents[1]


def create_project(name: str, goal: str, projects_root: Path) -> Path:
    if not VALID_NAME.fullmatch(name):
        raise ValueError("Project name must use lowercase letters, digits, and underscores.")

    project_dir = projects_root / name
    if project_dir.exists():
        raise FileExistsError(f"Project already exists: {project_dir}")

    project_dir.mkdir(parents=True)
    for directory in (
        "easyeda/source",
        "easyeda/exports",
        "datasheets",
        "reference_designs",
        "docs",
        "review",
        "release",
        "_artifacts",
    ):
        (project_dir / directory).mkdir(parents=True)

    template_dir = SKILL_ROOT / "templates"
    replacements = {"{{PROJECT_NAME}}": name, "{{GOAL}}": goal or "(待确认)"}
    for source_name, target_name in (
        ("PROJECT.md.tmpl", "PROJECT.md"),
        ("STATUS.md.tmpl", "STATUS.md"),
    ):
        content = (template_dir / source_name).read_text(encoding="utf-8")
        for marker, value in replacements.items():
            content = content.replace(marker, value)
        (project_dir / target_name).write_text(content, encoding="utf-8")

    shutil.copyfile(template_dir / "project.gitignore", project_dir / ".gitignore")
    return project_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a JLCEDA project skeleton.")
    parser.add_argument("name", help="Lowercase project name, for example buck_5v_3a")
    parser.add_argument("--goal", default="", help="One-sentence project goal")
    parser.add_argument("--projects-root", default="Projects", type=Path)
    args = parser.parse_args()

    try:
        project_dir = create_project(args.name, args.goal, args.projects_root)
    except (ValueError, FileExistsError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Created {project_dir}")
    print("Next: record requirements in PROJECT.md, then start the circuit-design phase.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

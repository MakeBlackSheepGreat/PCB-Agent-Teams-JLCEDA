from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


init_project = load_module("jlc_init_project", SKILL_ROOT / "scripts" / "init_project.py")
validate_export = load_module("jlc_validate_export", SKILL_ROOT / "scripts" / "validate_export.py")


class WorkflowToolsTests(unittest.TestCase):
    def test_create_project_creates_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = init_project.create_project(
                "buck_5v_3a", "5V power board", Path(directory) / "Projects"
            )

            self.assertTrue((project / "PROJECT.md").is_file())
            self.assertTrue((project / "STATUS.md").is_file())
            self.assertTrue((project / "easyeda" / "source").is_dir())
            self.assertTrue((project / "easyeda" / "exports").is_dir())

    def test_validate_export_accepts_matching_jlc_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            bom = temporary / "bom.csv"
            cpl = temporary / "cpl.csv"
            gerber = temporary / "gerbers.zip"
            bom.write_text("Designator,Comment,Quantity\nC1,C_100nF,1\nR1,R_10k,1\n", encoding="utf-8")
            cpl.write_text("Designator,Mid X,Mid Y,Layer,Rotation\nC1,12.0,10.5,TopLayer,0\nR1,15.0,10.5,TopLayer,90\n", encoding="utf-8")
            with zipfile.ZipFile(gerber, "w") as archive:
                archive.writestr("board.GTL", "G04 copper*")
                archive.writestr("board.TXT", "M48")

            report = validate_export.validate(bom, cpl, gerber, require_all_cpl=True)

            self.assertEqual(report["verdict"], "pass")

    def test_validate_export_rejects_unknown_cpl_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            bom = temporary / "bom.csv"
            cpl = temporary / "cpl.csv"
            bom.write_text("Designator,Comment\nC1,C_100nF\n", encoding="utf-8")
            cpl.write_text("Designator,Mid X,Mid Y,Layer,Rotation\nC2,12.0,10.5,TopLayer,0\n", encoding="utf-8")

            report = validate_export.validate(bom, cpl, None, require_all_cpl=False)

            self.assertEqual(report["verdict"], "fail")
            self.assertTrue(any(finding["code"] == "CPL_UNKNOWN_REF" for finding in report["findings"]))

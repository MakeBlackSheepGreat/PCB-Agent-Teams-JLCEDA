from __future__ import annotations

import importlib.util
import json
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
kicad_handoff = load_module("jlc_kicad_handoff", SKILL_ROOT / "scripts" / "prepare_kicad_handoff.py")
board_constraints = load_module("jlc_board_constraints", SKILL_ROOT / "scripts" / "validate_board_constraints.py")


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
            self.assertTrue((project / "kicad").is_dir())
            constraints = project / "constraints" / "board_constraints.json"
            self.assertTrue(constraints.is_file())
            self.assertEqual(json.loads(constraints.read_text(encoding="utf-8"))["project"], "buck_5v_3a")

    def test_prepare_kicad_handoff_records_sources_and_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "buck"
            kicad = project / "kicad"
            kicad.mkdir(parents=True)
            (kicad / "buck.kicad_sch").write_text("(kicad_sch (version 20240101))\n", encoding="utf-8")
            (kicad / "buck.kicad_pcb").write_text(
                "(kicad_pcb\n"
                "  (net 0 \"\")\n"
                "  (net 1 \"GND\")\n"
                "  (footprint \"Test:Part\")\n"
                "  (segment (start 0 0) (end 1 1))\n"
                "  (via (at 1 1))\n"
                ")\n",
                encoding="utf-8",
            )

            manifest = kicad_handoff.prepare_handoff(project)

            self.assertEqual(manifest["format"], "jlceda-kicad-handoff/v1")
            self.assertEqual(manifest["source_of_truth"], "kicad")
            self.assertEqual(manifest["source_files"]["board"]["path"], "kicad/buck.kicad_pcb")
            self.assertEqual(manifest["board_metrics"]["footprints"], 1)
            self.assertTrue((project / "handoff" / "kicad_to_easyeda.json").is_file())

    def test_prepare_kicad_handoff_requires_both_design_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "buck"
            kicad = project / "kicad"
            kicad.mkdir(parents=True)
            (kicad / "buck.kicad_sch").write_text("(kicad_sch)\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "No .kicad_pcb"):
                kicad_handoff.prepare_handoff(project)

    def test_validate_board_constraints_rejects_impossible_via_geometry(self) -> None:
        report = board_constraints.validate(
            {
                "format": "pcb-agent-constraints/v1",
                "board": {"width_mm": 20, "height_mm": 20, "layer_count": 2},
                "manufacturing": {
                    "minimum_track_width_mm": 0.15,
                    "minimum_clearance_mm": 0.15,
                    "minimum_via_diameter_mm": 0.4,
                    "minimum_via_drill_mm": 0.4,
                    "board_edge_clearance_mm": 0.25,
                },
                "net_classes": [],
                "differential_pairs": [],
            }
        )

        self.assertEqual(report["verdict"], "fail")
        self.assertTrue(any(finding["code"] == "VIA_GEOMETRY" for finding in report["findings"]))

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

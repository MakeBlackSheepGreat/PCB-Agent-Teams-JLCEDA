"""
Coordinate transformation between EasyEDA Pro (1mil units) and KiCad (mm units).
"""

MIL_TO_MM = 0.0254
MM_TO_MIL = 1.0 / MIL_TO_MM


def mil_to_mm(value_mil: float) -> float:
    return round(value_mil * MIL_TO_MM, 6)


def mm_to_mil(value_mm: float) -> float:
    return round(value_mm * MM_TO_MIL, 3)

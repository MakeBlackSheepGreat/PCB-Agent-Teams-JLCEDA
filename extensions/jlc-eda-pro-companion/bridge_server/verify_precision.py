"""
Verify coordinate transformation precision between EasyEDA (mil) and KiCad (mm).

Requirement: round-trip error < 0.001mm for any coordinate.
"""

from coord_transform import mil_to_mm, mm_to_mil


def verify_roundtrip():
    test_values = [
        0, 1, 10, 100, 1000, 5000, 10000, 50000, 11811,  # typical PCB sizes
        0.1, 0.5, 2.54, 25.4, 0.001,  # sub-mil precision
    ]

    max_error = 0.0
    max_error_mil = 0.0

    print(f"{'mil':>12} {'-> mm':>14} {'-> mil':>14} {'error_mm':>12} {'error_mil':>12}")
    print("-" * 68)

    for mil in test_values:
        mm = mil_to_mm(mil)
        mil_back = mm_to_mil(mm)
        error_mm = abs(mm - mil_back * 0.0254)
        error_mil = abs(mil - mil_back)

        max_error = max(max_error, error_mm)
        max_error_mil = max(max_error_mil, error_mil)

        status = "PASS" if error_mm < 0.001 else "FAIL"
        print(f"{mil:>12.3f} {mm:>14.6f} {mil_back:>14.3f} {error_mm:>12.6f} {error_mil:>12.3f}  {status}")

    print("-" * 68)
    print(f"Max round-trip error: {max_error:.6f} mm ({max_error_mil:.3f} mil)")

    if max_error < 0.001:
        print("\nRESULT: PASS - All coordinates meet the < 0.001mm precision requirement.")
        return 0
    else:
        print("\nRESULT: FAIL - Some coordinates exceed the 0.001mm precision threshold.")
        return 1


if __name__ == "__main__":
    exit(verify_roundtrip())

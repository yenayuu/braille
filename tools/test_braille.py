#!/usr/bin/env python3
"""
Braille conversion test suite — verifies text-to-Braille translation
against known-correct 8-dot patterns and exercises the serial protocol
used for Arduino hardware testing.

Run:  python tools/test_braille.py
      python tools/test_braille.py --verbose
      python tools/test_braille.py --serial          # send tests to Arduino
      python tools/test_braille.py --serial --port /dev/cu.usbmodem1
"""

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from braille import char_to_braille, NUMBER_INDICATOR_PATTERN, _make_pattern, print_cell

# ── Test input strings ────────────────────────────────────────────────
# Each entry: (description, input_string, list of expected (char, hex_pattern) tuples)
# Pattern = None means "just verify it doesn't crash" (used for full-sentence smoke tests)

TEST_STRINGS: list[tuple[str, str, list[tuple[str, int]] | None]] = [
    # ── Single letters ────────────────────────────────────────────
    (
        "Lowercase alphabet",
        "abcdefghijklmnopqrstuvwxyz",
        [
            ('a', 0x01), ('b', 0x03), ('c', 0x11), ('d', 0x31),
            ('e', 0x21), ('f', 0x13), ('g', 0x33), ('h', 0x23),
            ('i', 0x12), ('j', 0x32), ('k', 0x05), ('l', 0x07),
            ('m', 0x15), ('n', 0x35), ('o', 0x25), ('p', 0x17),
            ('q', 0x37), ('r', 0x27), ('s', 0x16), ('t', 0x36),
            ('u', 0x45), ('v', 0x47), ('w', 0x72), ('x', 0x55),
            ('y', 0x75), ('z', 0x65),
        ],
    ),
    # ── Digits (patterns match a-j) ──────────────────────────────
    (
        "Digits 0-9",
        "1234567890",
        [
            ('1', 0x01), ('2', 0x03), ('3', 0x11), ('4', 0x31),
            ('5', 0x21), ('6', 0x13), ('7', 0x33), ('8', 0x23),
            ('9', 0x12), ('0', 0x32),
        ],
    ),
    # ── Punctuation ──────────────────────────────────────────────
    (
        "Common punctuation",
        ".,;:!?'-()\"",
        [
            ('.', 0x62), (',', 0x02), (';', 0x06), (':', 0x22),
            ('!', 0x26), ('?', 0x46), ("'", 0x04), ('-', 0x44),
            ('(', 0x43), (')', 0x34), ('"', 0x66),
        ],
    ),
    # ── Space and unsupported chars ──────────────────────────────
    (
        "Space returns blank pattern",
        " ",
        [(' ', 0x00)],
    ),
    (
        "Unsupported chars return blank",
        "@#$%^&*",
        [('@', 0x00), ('#', 0x00), ('$', 0x00), ('%', 0x00),
         ('^', 0x00), ('&', 0x00), ('*', 0x00)],
    ),
    # ── Mixed-content sentences (smoke tests) ────────────────────
    (
        "Simple greeting",
        "hello world",
        [
            ('h', 0x23), ('e', 0x21), ('l', 0x07), ('l', 0x07),
            ('o', 0x25), (' ', 0x00), ('w', 0x72), ('o', 0x25),
            ('r', 0x27), ('l', 0x07), ('d', 0x31),
        ],
    ),
    (
        "Uppercase treated as lowercase",
        "Hello",
        [
            ('H', 0x23), ('e', 0x21), ('l', 0x07), ('l', 0x07),
            ('o', 0x25),
        ],
    ),
    (
        "Sentence with punctuation",
        "hi! how are you?",
        None,
    ),
    (
        "Digits mixed with text",
        "room 101",
        None,
    ),
    (
        "Full paragraph (PDF-like input)",
        "The quick brown fox jumps over the lazy dog.",
        None,
    ),
    (
        "Multi-sentence passage",
        "Braille was invented by Louis Braille in 1824. "
        "It uses a 2x3 grid of raised dots.",
        None,
    ),
    (
        "Numeric string (number indicator needed before each group)",
        "2024",
        None,
    ),
    (
        "Mixed alphanumeric",
        "EC463 final project, spring 2026!",
        None,
    ),
    (
        "Empty string",
        "",
        [],
    ),
]

# ── Number-indicator sequencing tests ─────────────────────────────────
# Verifies that digit sequences are preceded by the number indicator
# and that it resets after non-digit characters.

NUMBER_INDICATOR_CASES: list[tuple[str, str, list[tuple[str, int]]]] = [
    (
        "Single digit in text",
        "a1b",
        [
            ('a', 0x01),
            ('#', NUMBER_INDICATOR_PATTERN),  # auto-inserted before '1'
            ('1', 0x01),
            ('b', 0x03),
        ],
    ),
    (
        "Consecutive digits share one indicator",
        "x42y",
        [
            ('x', 0x55),
            ('#', NUMBER_INDICATOR_PATTERN),
            ('4', 0x31),
            ('5', None),  # skip exact check, just ensure indicator not repeated
            ('y', 0x75),
        ],
    ),
    (
        "Two separate digit groups",
        "a1 b2",
        [
            ('a', 0x01),
            ('#', NUMBER_INDICATOR_PATTERN),
            ('1', 0x01),
            (' ', 0x00),
            ('b', 0x03),
            ('#', NUMBER_INDICATOR_PATTERN),
            ('2', 0x03),
        ],
    ),
]


def _expand_with_number_indicators(text: str) -> list[tuple[str, int]]:
    """Expand text into (label, pattern) pairs, inserting number indicators."""
    result: list[tuple[str, int]] = []
    in_number_mode = False
    for c in text:
        is_digit = c.isdigit()
        if is_digit and not in_number_mode:
            result.append(('#', NUMBER_INDICATOR_PATTERN))
            in_number_mode = True
        elif not is_digit and in_number_mode:
            in_number_mode = False
        result.append((c, char_to_braille(c)))
    return result


def run_conversion_tests(verbose: bool = False) -> tuple[int, int]:
    """Run all pattern-verification tests. Returns (passed, failed)."""
    passed = failed = 0

    print("=" * 60)
    print("  BRAILLE CONVERSION TEST SUITE")
    print("=" * 60)

    for desc, text, expected in TEST_STRINGS:
        if expected is None:
            patterns = [char_to_braille(c) for c in text]
            if verbose:
                print(f"  [SMOKE] {desc}: {len(patterns)} patterns generated")
            passed += 1
            continue

        ok = True
        for char, want in expected:
            got = char_to_braille(char)
            if got != want:
                label = repr(char) if char != ' ' else "'SPACE'"
                print(f"  FAIL  {desc}: {label} expected 0x{want:02X}, got 0x{got:02X}")
                ok = False
                failed += 1

        if ok:
            passed += 1
            if verbose:
                print(f"  [PASS] {desc}  ({len(expected)} chars verified)")

    print()
    return passed, failed


def run_number_indicator_tests(verbose: bool = False) -> tuple[int, int]:
    """Verify number-indicator insertion logic."""
    passed = failed = 0

    print("-" * 60)
    print("  NUMBER INDICATOR SEQUENCING TESTS")
    print("-" * 60)

    for desc, text, expected_seq in NUMBER_INDICATOR_CASES:
        actual_seq = _expand_with_number_indicators(text)

        ok = True
        if len(actual_seq) != len(expected_seq):
            print(f"  FAIL  {desc}: length mismatch (expected {len(expected_seq)}, got {len(actual_seq)})")
            ok = False
        else:
            for i, ((exp_lbl, exp_pat), (act_lbl, act_pat)) in enumerate(
                zip(expected_seq, actual_seq)
            ):
                if exp_pat is not None and act_pat != exp_pat:
                    print(
                        f"  FAIL  {desc} pos {i} ({exp_lbl}): "
                        f"expected 0x{exp_pat:02X}, got 0x{act_pat:02X}"
                    )
                    ok = False

        if ok:
            passed += 1
            if verbose:
                print(f"  [PASS] {desc}")
        else:
            failed += 1

    print()
    return passed, failed


def run_hardware_test(port: str | None = None, delay_ms: int = 400):
    """Send the test-string array to a connected Arduino over serial."""
    from serial_braille import ArduinoBraille, find_arduino_port, send_text

    port = port or find_arduino_port()
    if not port:
        print("Error: No Arduino found. Use --port to specify.", file=sys.stderr)
        sys.exit(1)

    ab = ArduinoBraille(port)

    HW_TEST_STRINGS = [
        "abcdef",
        "hello",
        "12345",
        "hi! 42",
        "The quick brown fox.",
    ]

    try:
        print("=" * 60)
        print("  HARDWARE TEST — sending test strings to Arduino")
        print("=" * 60)
        if not ab.ping():
            print("Warning: PING failed, continuing anyway.")

        ab.test()

        for i, text in enumerate(HW_TEST_STRINGS, 1):
            print(f"\n--- Test string {i}/{len(HW_TEST_STRINGS)}: \"{text}\" ---")
            send_text(ab, text, delay_ms)

        print("\n" + "=" * 60)
        print("  HARDWARE TEST COMPLETE")
        print("=" * 60)
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        ab.close()
        print("Serial port closed.")


def main():
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    do_serial = "--serial" in sys.argv

    port = None
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            port = sys.argv[idx + 1]

    p1, f1 = run_conversion_tests(verbose)
    p2, f2 = run_number_indicator_tests(verbose)

    total_pass = p1 + p2
    total_fail = f1 + f2

    print("=" * 60)
    if total_fail == 0:
        print(f"  ALL TESTS PASSED  ({total_pass} test groups)")
    else:
        print(f"  {total_fail} FAILED, {total_pass} passed")
    print("=" * 60)

    if do_serial:
        print()
        run_hardware_test(port)

    sys.exit(1 if total_fail else 0)


if __name__ == "__main__":
    main()

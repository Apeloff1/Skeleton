"""GF-I art-direction acceptance contract tests (synthetic, deterministic, no GPU)."""
from skeleton.game import art_acceptance as aa

W, H = 32, 24


def _box_mask(x0=10, y0=6, x1=22, y1=20):
    return [[x0 <= x < x1 and y0 <= y < y1 for x in range(W)] for y in range(H)]


def _frame(mask, fg, bg):
    return [[fg if m else bg for m in row] for row in mask]


def test_palette_loads_tokens():
    pal = aa.load_palette()
    assert pal["brand"] == (0x8B, 0x5C, 0xF6)
    assert pal["surface"] == (0x0A, 0x0A, 0x0A)


def test_flat_gray_frame_fails_contrast_and_silhouette():
    empty = [[False] * W for _ in range(H)]
    frame = _frame(empty, (128, 128, 128), (128, 128, 128))
    rep = aa.evaluate_frame(frame, empty)
    assert not rep.passed
    joined = " ".join(rep.failures)
    assert "contrast" in joined and "silhouette_fill" in joined and "value_bands" in joined


def test_token_lit_subject_on_dark_bg_passes():
    pal = aa.load_palette()
    mask = _box_mask()
    frame = _frame(mask, pal["brandSecondary"], pal["surface"])
    rep = aa.evaluate_frame(frame, mask)
    assert rep.passed, rep.failures
    assert rep.metrics["contrast_ratio"] >= aa.MIN_CONTRAST_RATIO
    assert "GF-P0-61" in rep.not_claimed


def test_off_palette_fails_conformance():
    pal = aa.load_palette()
    mask = _box_mask(0, 0, W, 12)  # half the frame lime green
    frame = _frame(mask, (0, 255, 0), pal["surface"])
    rep = aa.evaluate_frame(frame, mask)
    assert not rep.passed
    assert any("palette_conformance" in f for f in rep.failures)


def test_deterministic():
    pal = aa.load_palette()
    mask = _box_mask()
    frame = _frame(mask, pal["brand"], pal["surface"])
    assert aa.evaluate_frame(frame, mask).metrics == aa.evaluate_frame(frame, mask).metrics

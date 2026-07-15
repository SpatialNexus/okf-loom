from __future__ import annotations

import io

import pytest

import capture_readme_media as media

Image = pytest.importorskip("PIL.Image")


def _png_frame(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("filename", "frame_count"),
    [("themes.gif", 4), ("graph-lenses.gif", 5)],
)
def test_readme_gifs_play_once_and_retain_final_frame(tmp_path, filename, frame_count):
    colors = [
        (220, 20, 60),
        (12, 115, 115),
        (64, 160, 80),
        (80, 60, 180),
        (245, 170, 30),
    ][:frame_count]
    path = tmp_path / filename

    media._assemble_gif([_png_frame(color) for color in colors], path)

    raw = path.read_bytes()
    assert b"NETSCAPE2.0" not in raw, "infinite-loop application extension present"
    with Image.open(path) as gif:
        assert "loop" not in gif.info, "Pillow decoded an infinite/repeat loop extension"
        assert gif.n_frames == frame_count
        durations = []
        for index in range(gif.n_frames):
            gif.seek(index)
            durations.append(gif.info["duration"])
        assert durations == [media.GIF_FRAME_MS] * (frame_count - 1) + [
            media.GIF_FINAL_FRAME_MS
        ]
        gif.seek(gif.n_frames - 1)
        assert gif.convert("RGB").getpixel((0, 0)) == colors[-1]


def test_gif_manifest_metadata_declares_finite_one_cycle_final_frame():
    metadata = media._gif_playback_metadata(5, "Recent")

    assert metadata == {
        "autoplay": "finite-one-cycle",
        "loop_count": 1,
        "infinite_loop": False,
        "loop_extension": False,
        "frame_count": 5,
        "frame_duration_ms": media.GIF_FRAME_MS,
        "final_frame": "Recent",
        "final_frame_duration_ms": media.GIF_FINAL_FRAME_MS,
        "final_frame_retained": True,
    }

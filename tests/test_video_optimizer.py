import os
import tempfile
from app.services.video_optimizer import (
    get_cached_folder_videos,
    get_playable_video_fast,
    is_video_ready,
    prewarm_background_folder,
)


def test_cached_folder_videos(tmp_path):
    # Empty folder
    assert get_cached_folder_videos(str(tmp_path)) == []

    # Create dummy video files
    f1 = tmp_path / "vid1.mp4"
    f1.write_bytes(b"dummy")
    f2 = tmp_path / "vid2.mkv"
    f2.write_bytes(b"dummy")
    f3 = tmp_path / "song.mp3"
    f3.write_bytes(b"audio")

    vids = get_cached_folder_videos(str(tmp_path))
    assert len(vids) == 2
    assert str(f1) in vids
    assert str(f2) in vids
    assert str(f3) not in vids


def test_playable_video_fast_nonexistent():
    # Non-existent or empty path returns as-is without crashing
    assert get_playable_video_fast("") == ""
    assert get_playable_video_fast("non_existent.mp4") == "non_existent.mp4"


def test_playable_video_fast_caching(tmp_path):
    f = tmp_path / "test.mp4"
    f.write_bytes(b"fake video data")
    path_str = str(f)

    # First call will probe/check
    p1 = get_playable_video_fast(path_str, auto_transcode_async=False)
    assert p1 == path_str

    # Second call hits memory cache
    p2 = get_playable_video_fast(path_str, auto_transcode_async=False)
    assert p2 == p1

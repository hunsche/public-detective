import os

import imageio_ffmpeg
import pytest


@pytest.fixture(scope="session", autouse=True)
def download_ffmpeg():
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_path

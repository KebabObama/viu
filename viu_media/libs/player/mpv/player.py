"""
MPV player integration for Viu.

This module provides the MpvPlayer class, which implements the BasePlayer interface
for the MPV media player.
"""

import logging
import os
import re
import shutil
import subprocess

from ....core.config import MpvConfig
from ....core.exceptions import ViuError
from ....core.patterns import TORRENT_REGEX, YOUTUBE_REGEX
from ....core.utils import detect
from ..base import BasePlayer
from ..params import PlayerParams
from ..types import PlayerResult

logger = logging.getLogger(__name__)

MPV_AV_TIME_PATTERN = re.compile(r"AV: ([0-9:]*) / ([0-9:]*) \(([0-9]*)%\)")


class MpvPlayer(BasePlayer):
    """
    MPV player implementation for Viu.
    """

    def __init__(self, config: MpvConfig):
        self.config = config
        self.executable = shutil.which("mpv")

    # ---------- public API ----------

    def play(self, params: PlayerParams) -> PlayerResult:
        if TORRENT_REGEX.match(params.url) and detect.is_running_in_termux():
            raise ViuError("Unable to play torrents on termux")
        elif params.syncplay and detect.is_running_in_termux():
            raise ViuError("Unable to play with syncplay on termux")
        elif detect.is_running_in_termux():
            return self._play_on_mobile(params)
        else:
            return self._play_on_desktop(params)

    # ---------- mobile ----------

    def _play_on_mobile(self, params: PlayerParams) -> PlayerResult:
        if YOUTUBE_REGEX.match(params.url):
            args = [
                "nohup",
                "am",
                "start",
                "--user",
                "0",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                params.url,
                "-n",
                "com.google.android.youtube/.UrlActivity",
            ]
        else:
            args = [
                "nohup",
                "am",
                "start",
                "--user",
                "0",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                params.url,
                "-n",
                "is.xyz.mpv/.MPVActivity",
            ]

        subprocess.run(args, env=detect.get_clean_env())
        return PlayerResult(params.episode)

    # ---------- desktop ----------

    def _play_on_desktop(self, params: PlayerParams) -> PlayerResult:
        if not self.executable:
            raise ViuError("MPV executable not found in PATH.")

        if TORRENT_REGEX.search(params.url):
            return self._stream_on_desktop_with_webtorrent_cli(params)
        elif params.syncplay:
            return self._stream_on_desktop_with_syncplay(params)
        else:
            return self._stream_on_desktop_with_subprocess(params)

    def _stream_on_desktop_with_subprocess(
        self, params: PlayerParams
    ) -> PlayerResult:
        mpv_args = self._base_mpv_args(params)

        pre_args = self._pre_args()

        proc = subprocess.run(
            pre_args + mpv_args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            env=detect.get_clean_env(),
        )

        stop_time = None
        total_time = None

        if proc.stdout:
            for line in reversed(proc.stdout.split("\n")):
                match = MPV_AV_TIME_PATTERN.search(line.strip())
                if match:
                    stop_time = match.group(1)
                    total_time = match.group(2)
                    break

        return PlayerResult(
            episode=params.episode,
            total_time=total_time,
            stop_time=stop_time,
        )

    def play_with_ipc(
        self, params: PlayerParams, socket_path: str
    ) -> subprocess.Popen:
        mpv_args = [
            self.executable,
            f"--input-ipc-server={socket_path}",
            "--idle=yes",
            "--force-window=yes",
            "--config-dir=" + self._mpv_config_dir(),
            params.url,
        ]

        mpv_args.extend(self._create_mpv_cli_options(params))

        logger.info(f"Starting MPV with IPC socket: {socket_path}")

        return subprocess.Popen(
            self._pre_args() + mpv_args,
            env=detect.get_clean_env(),
        )

    def _stream_on_desktop_with_webtorrent_cli(
        self, params: PlayerParams
    ) -> PlayerResult:
        webtorrent = shutil.which("webtorrent")
        if not webtorrent:
            raise ViuError("Please install webtorrent-cli")

        args = [webtorrent, params.url, "--mpv"]

        if mpv_args := self._create_mpv_cli_options(params):
            args.append("--player-args")
            args.extend(mpv_args)

        subprocess.run(args, env=detect.get_clean_env())
        return PlayerResult(params.episode)

    def _stream_on_desktop_with_syncplay(
        self, params: PlayerParams
    ) -> PlayerResult:
        syncplay = shutil.which("syncplay")
        if not syncplay:
            raise ViuError("Please install syncplay")

        args = [syncplay, params.url]

        if mpv_args := self._base_mpv_args(params):
            args.append("--")
            args.extend(mpv_args)

        subprocess.run(args, env=detect.get_clean_env())
        return PlayerResult(params.episode)

    # ---------- helpers ----------

    def _mpv_config_dir(self) -> str:
        return os.path.expanduser("~/.config/mpv")

    def _base_mpv_args(self, params: PlayerParams) -> list[str]:
        args = [
            self.executable,
            "--config-dir=" + self._mpv_config_dir(),
            params.url,
        ]
        args.extend(self._create_mpv_cli_options(params))
        return args

    def _pre_args(self) -> list[str]:
        return self.config.pre_args.split(",") if self.config.pre_args else []

    def _create_mpv_cli_options(self, params: PlayerParams) -> list[str]:
        mpv_args: list[str] = []

        if params.headers:
            header_str = ",".join(f"{k}:{v}" for k, v in params.headers.items())
            mpv_args.append(f"--http-header-fields={header_str}")

        if params.subtitles:
            for sub in params.subtitles:
                mpv_args.append(f"--sub-file={sub}")

        if params.start_time:
            mpv_args.append(f"--start={params.start_time}")

        if params.title:
            mpv_args.append(f"--title={params.title}")

        if self.config.args:
            mpv_args.extend(self.config.args.split(","))

        return mpv_args


if __name__ == "__main__":
    from ....core.constants import APP_ASCII_ART

    print(APP_ASCII_ART)
    url = input("Enter the url you would like to stream: ")
    mpv = MpvPlayer(MpvConfig())
    result = mpv.play(PlayerParams(episode="", query="", url=url, title=""))
    print(result)

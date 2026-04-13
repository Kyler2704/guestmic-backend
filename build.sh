#!/usr/bin/env bash
set -e

pip install -r requirements.txt

# Download static ffmpeg binary — no root required
echo "Downloading ffmpeg static binary..."
wget -q https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz
tar xf ffmpeg-master-latest-linux64-gpl.tar.xz
mkdir -p bin
mv ffmpeg-master-latest-linux64-gpl/bin/ffmpeg bin/ffmpeg
chmod +x bin/ffmpeg
rm -rf ffmpeg-master-latest-linux64-gpl ffmpeg-master-latest-linux64-gpl.tar.xz
echo "ffmpeg installed at bin/ffmpeg"

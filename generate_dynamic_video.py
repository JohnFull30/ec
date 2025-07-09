import os
import sys
import subprocess
import re

def extract_ticker_and_quarter(input_id):
    match = re.match(r'([a-zA-Z]+)_q(\d)_(\d{4})', input_id)
    if not match:
        print("❌ Invalid format. Use: ticker_q#_yyyy (e.g. tsla_q2_2025)")
        sys.exit(1)
    ticker = match.group(1).upper()
    quarter = f"q{match.group(2)}_{match.group(3)}"
    return ticker, quarter

if len(sys.argv) != 2:
    print("Usage: python3 generate_dynamic_video.py tsla_q2_2025")
    sys.exit(1)

input_id = sys.argv[1].lower()
ticker, quarter = extract_ticker_and_quarter(input_id)

SLIDES_DIR = "assets"
os.makedirs(SLIDES_DIR, exist_ok=True)

summary_dir = os.path.join("summaries", ticker, quarter)
VOICEOVER_PATH = os.path.join(summary_dir, f"voiceover_{ticker}_{quarter}.mp3")
OUTPUT_VIDEO = os.path.join(summary_dir, "video_dynamic.mp4")
DURATION_PER_SLIDE = 5  # seconds

if not os.path.exists(VOICEOVER_PATH):
    print(f"❌ Missing voiceover file: {VOICEOVER_PATH}")
    sys.exit(1)

slide_files = sorted([f for f in os.listdir(SLIDES_DIR) if f.endswith('.png')])
if not slide_files:
    print("❌ No PNG slides found in assets/.")
    sys.exit(1)

ffmpeg_input_list = os.path.join(SLIDES_DIR, "ffmpeg_input.txt")
with open(ffmpeg_input_list, 'w') as f:
    for slide in slide_files:
        f.write(f"file '{slide}'\n")
        f.write(f"duration {DURATION_PER_SLIDE}\n")
    f.write(f"file '{slide_files[-1]}'\n")

temp_video = os.path.join(SLIDES_DIR, "temp_video.mp4")
os.chdir(SLIDES_DIR)
build = subprocess.run([
    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
    "-i", "ffmpeg_input.txt",
    "-vsync", "vfr", "-pix_fmt", "yuv420p",
    "temp_video.mp4"
])
os.chdir("..")

if build.returncode != 0 or not os.path.exists(temp_video):
    print("❌ Failed to create slideshow.")
    sys.exit(1)

subprocess.run([
    "ffmpeg", "-y",
    "-i", os.path.join(SLIDES_DIR, "temp_video.mp4"),
    "-i", VOICEOVER_PATH,
    "-c:v", "copy",
    "-c:a", "aac",
    "-shortest",
    OUTPUT_VIDEO
])

print(f"✅ Final video created at: {OUTPUT_VIDEO}")
try:
    subprocess.run(["open", OUTPUT_VIDEO])
except Exception:
    pass

import os
import sys
import subprocess
import re
import json
import webbrowser
import tempfile
import argparse
from PyPDF2 import PdfReader

WHISPER_CLI = "./whisper.cpp/build/bin/whisper-cli"
WHISPER_MODEL = "./whisper.cpp/models/ggml-small.bin"
script_dir = os.path.dirname(os.path.abspath(__file__))
BACKGROUND_IMAGE = os.path.join(script_dir, "clean_default_background.png")

def check_virtual_env():
    if sys.prefix == sys.base_prefix:
        print("⚠️ Not in a virtual environment. Activate one for safety.")

def get_target_files():
    return sorted(
        [f for f in os.listdir('.') if f.endswith('.mp3') or f.endswith('.pdf')],
        key=os.path.getmtime,
        reverse=True
    )

def confirm_files(files):
    print("\n📄 Files selected for processing:")
    for idx, f in enumerate(files):
        print(f" [{idx}] {f}")
    while True:
        choice = input("\nContinue? (y/n) or type 'd' to deselect files: ").strip().lower()
        if choice == 'y':
            return files
        elif choice == 'n':
            print("❌ Aborted by user.")
            sys.exit(0)
        elif choice == 'd':
            indices = input("Enter indices to remove (comma-separated): ").strip()
            try:
                to_remove = {int(i) for i in indices.split(',') if i.strip().isdigit()}
                files = [f for i, f in enumerate(files) if i not in to_remove]
                print("\n📄 Updated file list:")
                for idx, f in enumerate(files):
                    print(f" [{idx}] {f}")
            except ValueError:
                print("⚠️ Invalid input. Please enter numbers separated by commas.")
        else:
            print("⚠️ Invalid choice. Type 'y', 'n', or 'd'.")

def extract_ticker_and_quarter(filename):
    base = os.path.basename(filename).lower()
    match = re.search(r'([a-z]{1,5})[-_\s]*q[-_]?(\d)[-_\s]?(20\d{2})', base, re.IGNORECASE)
    if match:
        return match.group(1).upper(), f"q{match.group(2)}_{match.group(3)}"
    return base.split()[0].upper(), "unknown"

def normalize_filename(file, ticker, quarter):
    ext = os.path.splitext(file)[1]
    new_name = f"{ticker}_{quarter}{ext}"
    if file != new_name:
        os.rename(file, new_name)
        print(f"📦 Renamed {file} -> {new_name}")
    return new_name

def extract_text_from_pdf(file_path):
    reader = PdfReader(file_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)

def transcribe_audio(audio_file, ticker, quarter, out_dir, dry_run=False):
    print("📝 Transcribing with Whisper.cpp...")
    base_name = f"{ticker}_{quarter}_transcript"
    if dry_run:
        return "(dry run transcript)", os.path.join(out_dir, base_name + ".txt"), os.path.join(out_dir, base_name + ".vtt")
    result = subprocess.run([
        WHISPER_CLI, "-m", WHISPER_MODEL,
        "-f", audio_file,
        "-of", os.path.join(out_dir, base_name),
        "-otxt", "-ovtt"
    ])
    if result.returncode != 0:
        raise RuntimeError("Whisper transcription failed.")
    with open(f"{os.path.join(out_dir, base_name)}.txt", 'r') as f:
        return f.read(), f"{os.path.join(out_dir, base_name)}.txt", f"{os.path.join(out_dir, base_name)}.vtt"

def summarize_text(text):
    import requests
    response = requests.post("http://localhost:11434/api/generate", json={
        "model": "llama3",
        "prompt": f"Summarize this earnings call clearly. Include 10 notable executive quotes separately:\n\n{text}\n\nStructure:\nSummary:\n[Your summary here]\n\nQuotes:\n1. \"...\"\n2. \"...\"",
        "stream": False
    })
    return response.json()['response']

def generate_youtube_script(summary):
    import requests
    response = requests.post("http://localhost:11434/api/generate", json={
        "model": "llama3",
        "prompt": f"Write a YouTube script (~1800–2000 words). Compelling and insightful:\n\n{summary}\n\nStart bold, give context, highlight, end strong CTA.",
        "stream": False
    })
    return response.json()['response']

def generate_voiceover(script_text, output_path, dry_run=False):
    print("🔊 Generating voiceover...")
    if dry_run:
        print(f"[dry-run] Would generate voiceover to {output_path}")
        return
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tf:
        tf.write(script_text.encode())
        tf.flush()
        script_path = tf.name
    aiff_path = output_path.replace(".mp3", ".aiff")
    subprocess.run(["say", "-f", script_path, "-o", aiff_path])
    subprocess.run(["ffmpeg", "-y", "-i", aiff_path, output_path])
    os.remove(script_path)
    os.remove(aiff_path)

def create_video(image_path, audio_path, output_path, dry_run=False):
    print("🎞️ Building video with ffmpeg...")
    if dry_run:
        print(f"[dry-run] Would create video with {audio_path} on {image_path}")
        return
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", image_path, "-i", audio_path,
        "-filter:a", "atempo=0.85", "-c:v", "libx264", "-c:a", "aac", "-shortest",
        "-pix_fmt", "yuv420p", output_path
    ], check=True)

def extract_quotes_with_script(primary_file, fallback_file=None):
    for path in [primary_file, fallback_file]:
        if path and os.path.exists(path):
            subprocess.run(["python3", "extract_quotes.py", path], check=True)
            quotes_file = f"quotes_{os.path.basename(path).replace('.txt', '').replace('.pdf', '').replace('.vtt', '')}.json"
            if os.path.exists(quotes_file):
                with open(quotes_file, 'r') as f:
                    return json.load(f)
    return []

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--skip-to')
    parser.add_argument('--no-confirm', action='store_true')
    args = parser.parse_args()

    check_virtual_env()
    files = get_target_files()

    if args.skip_to:
        if args.skip_to.isdigit():
            files = files[int(args.skip_to):]
        else:
            match_idx = next((i for i, f in enumerate(files) if args.skip_to.lower() in f.lower()), None)
            if match_idx is not None:
                files = files[match_idx:]

    if not args.no_confirm:
        files = confirm_files(files)

    for file in files:
        try:
            ticker, quarter = extract_ticker_and_quarter(file)
            normalized_file = normalize_filename(file, ticker, quarter)
            out_dir = os.path.join("summaries", ticker, quarter)
            os.makedirs(out_dir, exist_ok=True)

            if normalized_file.endswith(".pdf"):
                text = extract_text_from_pdf(normalized_file)
                transcript_file = os.path.join(out_dir, normalized_file)
                vtt_file = None
            elif normalized_file.endswith(".mp3"):
                text, transcript_file, vtt_file = transcribe_audio(normalized_file, ticker, quarter, out_dir, dry_run=args.dry_run)

            full_summary = summarize_text(text)
            quotes = extract_quotes_with_script(vtt_file, transcript_file)
            script = generate_youtube_script(full_summary)

            paths = {k: os.path.join(out_dir, f"{k}_{ticker}_{quarter}.{ext}") for k, ext in {
                "summary": "txt", "script": "txt", "voice": "mp3", "video": "mp4", "quotes": "json"}.items()}

            for key, content in [("summary", full_summary), ("script", script), ("quotes", json.dumps(quotes, indent=2))]:
                if args.dry_run:
                    print(f"[dry-run] Would write {paths[key]}")
                else:
                    with open(paths[key], 'w') as f:
                        f.write(content)

            generate_voiceover(script, paths["voice"], dry_run=args.dry_run)
            create_video(BACKGROUND_IMAGE, paths["voice"], paths["video"], dry_run=args.dry_run)

            if not args.dry_run:
                subprocess.run(["python3", os.path.join(script_dir, "generate_dynamic_video.py"), f"{ticker.lower()}_{quarter}"])

            print(f"✅ Done: {ticker} {quarter}")

        except Exception as e:
            print(f"❌ Error in {file}: {e}")

    webbrowser.open("summaries")

if __name__ == '__main__':
    main()

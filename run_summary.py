import os
import sys
import subprocess
import mimetypes
import re
import json
import webbrowser
import tempfile
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
    while True:
        print("\n📄 Files selected for processing:")
        for idx, f in enumerate(files):
            print(f" [{idx}] {f}")

        choice = input("\nContinue? (y/n) or type 'd' to deselect files: ").strip().lower()
        if choice == 'y':
            return files
        elif choice == 'n':
            print("❌ Aborted by user.")
            sys.exit(0)
        elif choice == 'd':
            to_remove = input("Enter indices to remove (comma-separated): ").strip()
            try:
                indices = set(int(i) for i in to_remove.split(',') if i.strip().isdigit())
                files = [f for idx, f in enumerate(files) if idx not in indices]
            except ValueError:
                print("⚠️ Invalid input. Use numbers like: 0,1,2")
        else:
            print("⚠️ Invalid option. Type 'y' to continue, 'n' to cancel, or 'd' to deselect files.")


def extract_ticker_and_quarter(filename):
    base = os.path.basename(filename).lower()
    match = re.search(r'([a-z]{1,5})[-_\s]*q[-_]?(\d)[-_\s]?(20\d{2})', base, re.IGNORECASE)
    if match:
        return match.group(1).upper(), f"q{match.group(2)}_{match.group(3)}"
    return base.split()[0].upper(), "unknown"


def extract_text_from_pdf(file_path):
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            try:
                text += page.extract_text() or ""
            except Exception:
                continue
        return text
    except Exception as e:
        raise RuntimeError(f"Failed to read PDF: {e}")


def transcribe_audio(audio_file, ticker, quarter):
    print("📝 Transcribing with Whisper.cpp...")
    transcript_file = f"{ticker}_{quarter}_transcript.txt"
    result = subprocess.run([
        WHISPER_CLI, "-m", WHISPER_MODEL,
        "-f", audio_file,
        "-of", transcript_file.replace('.txt', ''),
        "-otxt", "-ovtt"
    ])
    if result.returncode != 0:
        raise RuntimeError("Whisper transcription failed.")
    with open(transcript_file, 'r') as f:
        return f.read(), transcript_file


def summarize_text(text):
    import requests
    response = requests.post("http://localhost:11434/api/generate", json={
        "model": "llama3",
        "prompt": f"""Summarize this earnings call clearly. Include 10 notable executive quotes separately:

{text}

Structure:
Summary:
[Your summary here]

Quotes:
1. "..."
2. "..."
""",
        "stream": False
    })
    return response.json()['response']


def generate_youtube_script(summary):
    import requests
    response = requests.post("http://localhost:11434/api/generate", json={
        "model": "llama3",
        "prompt": f"""Write a YouTube script that's around 12 minutes (~1800–2000 words). 
Make it compelling and insightful using the summary and financial context.

Summary:
{summary}

Start with a bold hook, give context about the company, dive into highlights, and end with a strong CTA.
""",
        "stream": False
    })
    return response.json()['response']


def generate_voiceover(script_text, output_path):
    print("🔊 Generating voiceover with macOS 'say' (offline)...")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tf:
        tf.write(script_text.encode())
        tf.flush()
        script_path = tf.name
    aiff_path = output_path.replace(".mp3", ".aiff")
    subprocess.run(["say", "-f", script_path, "-o", aiff_path])
    subprocess.run(["ffmpeg", "-y", "-i", aiff_path, output_path])
    os.remove(script_path)
    os.remove(aiff_path)


def create_video(image_path, audio_path, output_path):
    print("🎞️ Building video with ffmpeg...")
    abs_image_path = os.path.abspath(image_path)

    if not os.path.isfile(abs_image_path):
        raise FileNotFoundError(f"Background image not found at: {abs_image_path}")

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", abs_image_path,
        "-i", audio_path,
        "-filter:a", "atempo=0.85",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-pix_fmt", "yuv420p",
        output_path
    ]

    print(f"🧪 Running FFmpeg command:\n{' '.join(cmd)}")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode != 0:
        print("❌ FFmpeg error:")
        print(result.stderr.decode())
        raise RuntimeError("FFmpeg failed to generate video.")


def extract_quotes_with_script(primary_file, fallback_file=None):
    for path in [primary_file, fallback_file]:
        if not path or not os.path.exists(path):
            continue
        try:
            subprocess.run(["python3", "extract_quotes.py", path], check=True)
            base = os.path.basename(path).replace(".txt", "").replace(".pdf", "").replace(".vtt", "")
            quotes_file = f"quotes_{base}.json"
            if os.path.exists(quotes_file):
                with open(quotes_file, 'r') as f:
                    quotes = json.load(f)
                if quotes:
                    return quotes
                else:
                    print(f"⚠️ Quote file exists but is empty: {quotes_file}")
        except Exception as e:
            print(f"⚠️ Failed to extract quotes from {path}: {e}")
    return []


def main():
    check_virtual_env()
    files = sys.argv[1:] if len(sys.argv) > 1 else get_target_files()
    files = confirm_files(files)
    for file in files:
        try:
            print(f"\n📂 Processing: {file}")
            ticker, quarter = extract_ticker_and_quarter(file)
            if file.endswith(".pdf"):
                text = extract_text_from_pdf(file)
                transcript_file = file
                vtt_file = None
            elif file.endswith(".mp3"):
                text, transcript_file = transcribe_audio(file, ticker, quarter)
                vtt_file = transcript_file.replace(".txt", ".vtt")
            else:
                continue

            full_summary = summarize_text(text)
            match = re.search(r'Summary:\s*(.*?)\s*Quotes:', full_summary, re.DOTALL)
            clean_summary = match.group(1).strip() if match else full_summary

            # Use VTT if available, fallback to transcript or PDF
            quotes = extract_quotes_with_script(vtt_file, transcript_file)

            script = generate_youtube_script(clean_summary)
            out_dir = os.path.join("summaries", ticker)
            os.makedirs(out_dir, exist_ok=True)

            paths = {
                "summary": os.path.join(out_dir, f"summary_{ticker}_{quarter}.txt"),
                "script": os.path.join(out_dir, f"youtube_script_{ticker}_{quarter}.txt"),
                "voice": os.path.join(out_dir, f"voiceover_{ticker}_{quarter}.mp3"),
                "video": os.path.join(out_dir, f"video_{ticker}_{quarter}.mp4"),
                "quotes": os.path.join(out_dir, f"quotes_{ticker}_{quarter}.json")
            }

            with open(paths["summary"], 'w') as f: f.write(clean_summary)
            with open(paths["script"], 'w') as f: f.write(script)
            with open(paths["quotes"], 'w') as f: json.dump(quotes, f, indent=2)
            generate_voiceover(script, paths["voice"])
            create_video(BACKGROUND_IMAGE, paths["voice"], paths["video"])

            try:
                subprocess.run([
                    "python3",
                    os.path.join(script_dir, "generate_dynamic_video.py"),
                    f"{ticker.lower()}_{quarter}"
                ])
            except Exception as e:
                print(f"⚠️ Failed to generate dynamic video: {e}")

            print(f"✅ Done: {ticker} {quarter}")
        except Exception as e:
            print(f"❌ Error in {file}: {e}")
    webbrowser.open("summaries")


if __name__ == '__main__':
    main()

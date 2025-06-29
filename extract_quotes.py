import re
import sys
import json
from PyPDF2 import PdfReader

RELEVANT_KEYWORDS = [
    "revenue", "guidance", "growth", "outlook", "AI", "artificial intelligence",
    "margin", "EPS", "earnings", "demand", "forecast", "segment", "data center",
    "automotive", "products", "shareholder", "capital", "gross", "net", "customer",
    "record", "strong", "accelerated", "decline", "increase", "surge", "conversion", "monetization"
]

ACTION_VERBS = [
    "delivered", "grew", "expanded", "drove", "achieved", "reported", "generated",
    "improved", "declined", "accelerated", "forecast", "expect", "see", "guiding", "surpassed"
]

IGNORE_PATTERNS = [
    r"press \*1", r"conference call", r"replay", r"mute", r"telephone keypad",
    r"welcome", r"ladies and gentlemen", r"operator", r"question and answer",
    r"Q&A", r"forward-looking", r"cautionary statement", r"SEC", r"regulation", r"safe harbor"
]

EXECUTIVES = ["Mark Zuckerberg", "Susan Li"]

MIN_WORDS = 10
MAX_WORDS = 50
MAX_QUOTES = 10


def is_relevant(text):
    text = text.lower()
    return any(k in text for k in RELEVANT_KEYWORDS) and any(v in text for v in ACTION_VERBS)


def extract_from_pdf(path):
    reader = PdfReader(path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_quotes_from_pdf(path):
    text = extract_from_pdf(path)
    lines = text.splitlines()

    quotes = []
    collecting = False
    speaker = ""
    buffer = []

    for line in lines:
        line = line.strip()

        if any(exec_name in line for exec_name in EXECUTIVES):
            if buffer and speaker:
                combined = " ".join(buffer)
                quotes += extract_relevant_quotes(combined, speaker)
                buffer = []
            speaker = next(name for name in EXECUTIVES if name in line)
            collecting = True
            continue

        if collecting:
            if line == "" and buffer:
                combined = " ".join(buffer)
                quotes += extract_relevant_quotes(combined, speaker)
                buffer = []
                if len(quotes) >= MAX_QUOTES:
                    break
            else:
                buffer.append(line)

    if buffer and speaker and len(quotes) < MAX_QUOTES:
        combined = " ".join(buffer)
        quotes += extract_relevant_quotes(combined, speaker)

    return quotes[:MAX_QUOTES]


def extract_quotes_from_vtt(path):
    with open(path, 'r') as f:
        lines = f.readlines()

    quotes = []
    current_quote = ""
    current_time = ""

    for line in lines:
        line = line.strip()
        if "-->" in line:
            current_time = line
            current_quote = ""
        elif not line or line.lower().startswith("webvtt"):
            continue
        else:
            current_quote += " " + line
            word_count = len(current_quote.split())
            if MIN_WORDS <= word_count <= MAX_WORDS:
                if any(re.search(p, current_quote, re.IGNORECASE) for p in IGNORE_PATTERNS):
                    current_quote = ""
                    continue
                if is_relevant(current_quote):
                    quotes.append({
                        "quote": current_quote.strip(),
                        "speaker": "Likely Executive",
                        "timestamp": current_time
                    })
                    current_quote = ""
                    if len(quotes) >= MAX_QUOTES:
                        break
    return quotes


def extract_relevant_quotes(text_block, speaker="Likely Executive"):
    quotes = []
    sentences = re.split(r"(?<=[.!?])\s+", text_block.strip())
    for sent in sentences:
        words = sent.strip().split()
        if MIN_WORDS <= len(words) <= MAX_WORDS and is_relevant(sent):
            quotes.append({
                "quote": sent.strip(),
                "speaker": speaker,
                "timestamp": "N/A"
            })
            if len(quotes) >= MAX_QUOTES:
                break
    return quotes


def extract_quotes_from_txt(path):
    with open(path, 'r') as f:
        text = f.read()
    return extract_relevant_quotes(text)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 extract_quotes.py path/to/transcript.[pdf|vtt|txt]")
        sys.exit(1)

    path = sys.argv[1].strip().lower()

    if path.endswith(".pdf"):
        quotes = extract_quotes_from_pdf(path)
    elif path.endswith(".vtt"):
        quotes = extract_quotes_from_vtt(path)
    elif path.endswith(".txt"):
        quotes = extract_quotes_from_txt(path)
    else:
        print("❌ Unsupported file type. Use .pdf, .vtt, or .txt")
        sys.exit(1)

    if not quotes:
        print("⚠️ No strong executive quotes found.")
        sys.exit(0)

    output_path = "quotes_" + path.split("/")[-1].replace(".pdf", "").replace(".vtt", "").replace(".txt", "") + ".json"
    with open(output_path, "w") as f:
        json.dump(quotes, f, indent=2)

    print(f"✅ Extracted {len(quotes)} quotes and saved to {output_path}")

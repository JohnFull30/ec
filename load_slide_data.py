import json

# Load the JSON file
with open("summaries/NVDA/nvda_q1_2025_slide_data.json", "r") as f:
    data = json.load(f)

# Display core fields
print("📌 Ticker:", data["ticker"])
print("📆 Quarter:", data["quarter"], data["year"])
print("🏢 Company:", data["company_name"])
print("📈 Revenue:", data["highlights"]["revenue"])
print("💬 First Quote:", data["executive_quotes"][0])

# Show thumbnail options
print("\n🎯 Thumbnail Text Options:")
for i, option in enumerate(data["thumbnail_text_options"], start=1):
    print(f"  {i}. {option}")

# Show title slide options
print("\n🎬 Title Slide Options:")
for i, title in enumerate(data["title_slide_text_options"], start=1):
    print(f"  {i}. {title['title']} — {title['subtitle']}")
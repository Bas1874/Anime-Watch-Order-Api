# scrape_wiki.py
import requests
import json
import sys

REDDIT_WIKI_URL = "https://www.reddit.com/r/anime/wiki/watch_order.json"
# The output path will be provided as a command-line argument
OUTPUT_FILEPATH = sys.argv[1]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def scrape_and_save():
    print(f"Fetching data from {REDDIT_WIKI_URL}...")
    try:
        response = requests.get(REDDIT_WIKI_URL, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        html_content = data.get("data", {}).get("content_html", "")

        if not html_content:
            print("Error: Could not find 'content_html'.")
            return

        output_data = {"html": html_content}

        with open(OUTPUT_FILEPATH, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=4)
        
        print(f"Successfully saved wiki data to {OUTPUT_FILEPATH}")

    except Exception as e:
        print(f"An error occurred: {e}")
        # Exit with a non-zero status code to fail the GitHub Action if something goes wrong
        sys.exit(1)

if __name__ == "__main__":
    scrape_and_save()

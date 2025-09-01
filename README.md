
# Reddit r/anime Watch Order Scraper & API

> This repository automatically scrapes the ultimate guide to anime watch orders from the [r/anime wiki](https://www.reddit.com/r/anime/wiki/watch_order) and transforms it into a clean, structured, and machine-readable JSON API.

## Project Overview

The `/r/anime` community maintains one of the most comprehensive and well-regarded watch order guides for complex anime series. However, this data exists as a manually-edited HTML wiki page, which makes it difficult to use in applications, trackers, or other automated tools.

This project solves that problem by:

1.  **Automatically scraping** the wiki page once a day using a GitHub Action.
2.  **Parsing** the complex HTML structure into a logical, easy-to-use format.
3.  **Enriching** the data by fetching detailed metadata (cover images, genres, scores, etc.) for each anime from the [AniList API](https://anilist.gitbook.io/anilist-apiv2-docs).
4.  **Committing** the updated data back to this repository, providing a reliable, free, and self-updating JSON API for anyone to use.

## How It Works

The entire process is automated via GitHub Actions:

1.  **Scheduled Trigger:** A workflow runs automatically every day at 6:00 AM UTC. It can also be triggered manually.
2.  **Authentication:** The Python script securely authenticates with the Reddit API using credentials stored in GitHub Secrets.
3.  **Scraping:** It fetches the raw HTML content of the `/r/anime/wiki/watch_order` page.
4.  **Parsing:** Using `BeautifulSoup`, the script intelligently parses the HTML, identifying each series, its alternative titles, and its various named watch orders (e.g., "Airing Order," "Novel Order").
5.  **Data Enrichment:** All unique MyAnimeList IDs found are collected and used in a single batch query to the AniList API to fetch rich metadata.
6.  **File Generation:** The script generates two JSON files in the `/data` directory.
7.  **Commit:** The GitHub Action automatically commits the updated files back to this repository, ensuring the data is always fresh.

## The Output Files

The generated data is available in the `/data` directory of this repository.

### Raw Data (`/data/watch_order.json`)

This file contains the raw, unescaped HTML content of the wiki page as it was at the time of the last scrape. It serves primarily as an archive and for debugging purposes.

### Structured API (`/data/watch_order_api.json`)

This is the primary output of the project. It is a structured JSON file containing the parsed and enriched data, ready for use in any application.

## API Data Structure

The `watch_order_api.json` file has a clear and predictable structure.

```json
{
  "metadata": {
    "version": "2.6",
    "last_updated_utc": "YYYY-MM-DDTHH:MM:SS.ffffff+00:00",
    "source_url": "https://www.reddit.com/r/anime/wiki/watch_order"
  },
  "data": [
    // Array of series entries
  ]
}
```

### Series Entry Object

Each element in the `data` array represents a single anime franchise:

*   `title`: (String) The primary title of the series (e.g., "Monogatari").
*   `alternative_titles`: (Array of Strings) Alternative names for the series (e.g., "Bakemonogatari").
*   `prologue`: (String | null) Introductory text that appears before the first watch order.
*   `entry_notes`: (String | null) General notes about the series as a whole (often from a "Note:" section).
*   `watch_orders`: (Array of Objects) A list containing one or more named watch orders.

### Watch Order Object

Each element in the `watch_orders` array represents a specific way to watch the series:

*   `name`: (String) The name of this specific order (e.g., "Airing Order", "Novel Release Order", "Main Story").
*   `description`: (String | null) The full text description and instructions for this watch order.
*   `steps`: (Array of Objects) An ordered list of the anime to watch.

### Step Object

Each element in the `steps` array represents a single anime title:

*   `step_title`: (String) The full text of the step as it appears on the wiki (e.g., "Kizumonogatari I: Tekketsu-hen").
*   `is_optional`: (Boolean) True if the step is marked as optional.
*   `media`: (Object) A rich object containing detailed metadata fetched from AniList (see `Anilist api.txt` in this repository for the full schema).

#### Example: `Monogatari` Entry

```json
{
  "title": "Monogatari",
  "alternative_titles": ["Bakemonogatari"],
  "prologue": "For the sake of convenience, this watch order guide will only be covering the most common watch orders...",
  "entry_notes": null,
  "watch_orders": [
    {
      "name": "Airing Order",
      "description": "This visual guide is good if you're more fond of infographics.\n\nBakemonogatari -> Nisemonogatari -> ...",
      "steps": [
        {
          "step_title": "Bakemonogatari",
          "is_optional": false,
          "media": {
            "id": 5081,
            "idMal": 5081,
            "title": { "romaji": "Bakemonogatari", ... },
            "format": "TV",
            "episodes": 15,
            "averageScore": 82,
            ...
          }
        },
        {
          "step_title": "Nisemonogatari",
          "is_optional": false,
          "media": { ... }
        }
      ]
    },
    {
      "name": "Novel Release Order",
      "description": "Infographic by u/BlakexEkalb helping explain the order.\n\nBakemonogatari -> Kizumonogatari I: Tekketsu-hen -> ...",
      "steps": [ ... ]
    }
  ]
}
```

## Setting Up and Running Locally

If you wish to fork this repository and run the scraper yourself, follow these steps:

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/your-username/Scraping-Watch-Order.git
    cd Scraping-Watch-Order
    ```

2.  **Install Dependencies:**
    Create a `requirements.txt` file with the following content:
    ```
    requests
    beautifulsoup4
    lxml
    ```
    Then run:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Set Up Secrets:** You will need to create your own Reddit Application to get API credentials.
    *   Go to `Preferences > apps` on Reddit and create a new "script" type app.
    *   In your forked GitHub repository, go to `Settings > Secrets and variables > Actions`.
    *   Create the following four repository secrets:
        *   `REDDIT_CLIENT_ID`: The client ID from your Reddit app.
        *   `REDDIT_CLIENT_SECRET`: The client secret from your Reddit app.
        *   `REDDIT_USERNAME`: Your Reddit username.
        *   `REDDIT_PASSWORD`: Your Reddit password.

4.  **Run the Script Manually:**
    ```bash
    python scrape_wiki.py ./data
    ```
    The output files will be generated in the `data` directory.

## Acknowledgements

*   This project would not be possible without the incredible work of the moderators and community contributors to the **/r/anime wiki**. All watch order data is sourced directly from their page.
*   Anime metadata is provided by the free **[AniList GraphQL API](https://anilist.gitbook.io/anilist-apiv2-docs)**.

## License

This project is licensed under the **MIT License**. See the `LICENSE` file for details.

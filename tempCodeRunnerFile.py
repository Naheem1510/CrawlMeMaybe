import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

# Setup headers
headers = {
    "User-Agent": "Mozilla/5.0"
}

# Base URLs
base_url = "https://www.myjob.mu"
search_url = "https://www.myjob.mu/ShowResults.aspx?Keywords=&Location=&Cat=0"  # All categories

# Store all jobs here
all_jobs = []
page = 1

while True:
    print(f"🔎 Scraping page {page}...")
    url = f"{search_url}&Page={page}"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"❌ Failed to fetch page {page}. Status code: {response.status_code}")
        break

    soup = BeautifulSoup(response.content, "html.parser")
    print(soup.prettify()[:2000])
    # ✅ Correct job listing container
    job_cards = soup.find_all("div", class_="media")
    print(f"📄 Jobs found on page {page}: {len(job_cards)}")

    if not job_cards:
        print("✅ No more job listings. Scraping complete.")
        break

    for card in job_cards:
        title_tag = card.find("a", href=True)
        company_tag = card.find("div", class_="col-md-5 col-sm-12 col-xs-12")
        location_tag = card.find("span", class_="fa fa-map-marker")

        if title_tag and title_tag["href"].startswith("/Jobs/"):
            title = title_tag.text.strip()
            link = base_url + title_tag["href"]

            # Fallback for company name
            company = "Not Specified"
            if company_tag and company_tag.find("span"):
                company = company_tag.find("span").text.strip()

            # Fallback for location
            location = "Not Specified"
            if location_tag and location_tag.next_sibling:
                location = location_tag.next_sibling.strip()

            all_jobs.append({
                "title": title,
                "company": company,
                "location": location,
            })

    page += 1
    time.sleep(1)  # Be polite to the server

# Save to CSV
df = pd.DataFrame(all_jobs)
df.to_csv("jobs.csv", index=False, encoding="utf-8-sig")
print(f"✅ Done! {len(df)} jobs saved to 'jobs.csv'")

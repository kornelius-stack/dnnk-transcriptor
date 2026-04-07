#!/usr/bin/env python3
"""
DNNK Webinar Auto-Transskription
Overvåger DNNK's vidensbank og transskriberer nye webinarer
Kun videoer uploadet efter CUTOFF_DATE transskriberes
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import time
import subprocess
from datetime import datetime, date
from pathlib import Path

# Konfiguration
TRANSKRIPTOR_API_KEY = os.environ.get('TRANSKRIPTOR_API_KEY')
TRANSCRIPTIONS_FOLDER = Path("transcriptions")
PROCESSED_VIDEOS_FILE = "processed_videos.json"

# Kun videoer uploadet efter denne dato transskriberes
CUTOFF_DATE = date(2026, 1, 1)

CATEGORIES = {
    "Tech_Talks":           "https://www.dnnk.dk/tech-talks/",
    "Godmorgen_med_DNNK":   "https://www.dnnk.dk/god-morgen-med-dnnk/",
    "Konferencer":          "https://www.dnnk.dk/optagelser-fra-konferencer-og-temadage/",
    "Jura":                 "https://www.dnnk.dk/jura-i-klimatilpasning/",
    "DNNK_Masterclass":     "https://www.dnnk.dk/dnnk-masterclass/",
    "Fremtidsvaerksted":    "https://www.dnnk.dk/fremtid/",
    "Arrangementer":        "https://www.dnnk.dk/arrangementer/",
    "Vidensbank":           "https://www.dnnk.dk/category/vidensbank/",
    "Studieture":           "https://www.dnnk.dk/online-studietur/",
    "VIP":                  "https://www.dnnk.dk/dnnk-vip/",
    "Oevrige":              "https://www.dnnk.dk/dnnk-arrangementer/"
}

def load_processed_videos():
    if os.path.exists(PROCESSED_VIDEOS_FILE):
        with open(PROCESSED_VIDEOS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_processed_video(video_id):
    processed = load_processed_videos()
    if video_id not in processed:
        processed.append(video_id)
        with open(PROCESSED_VIDEOS_FILE, 'w') as f:
            json.dump(processed, f, indent=2)

def extract_youtube_id(url):
    if 'youtu.be/' in url:
        return url.split('youtu.be/')[1].split('?')[0]
    elif 'youtube.com/watch?v=' in url:
        return url.split('v=')[1].split('&')[0]
    elif 'youtube.com/embed/' in url:
        return url.split('embed/')[1].split('?')[0]
    return None

def get_video_upload_date(video_id):
    """Hent uploaddato via yt-dlp"""
    try:
        result = subprocess.run(
            ["yt-dlp", "--get-filename", "-o", "%(upload_date)s",
             f"https://youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, timeout=30
        )
        date_str = result.stdout.strip()
        if date_str and len(date_str) == 8:
            return date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
    except Exception as e:
        print(f"      ⚠️ Kunne ikke hente uploaddato: {e}")
    return None

def scrape_category_for_videos(category_url):
    try:
        response = requests.get(category_url, timeout=30,
            headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(response.content, 'html.parser')
        youtube_urls = []
        for iframe in soup.find_all('iframe'):
            src = iframe.get('src', '')
            if 'youtube.com' in src or 'youtu.be' in src:
                video_id = extract_youtube_id(src)
                if video_id:
                    youtube_urls.append(video_id)
        for link in soup.find_all('a', href=True):
            href = link['href']
            if 'youtube.com' in href or 'youtu.be' in href:
                video_id = extract_youtube_id(href)
                if video_id:
                    youtube_urls.append(video_id)
        return list(set(youtube_urls))
    except Exception as e:
        print(f"❌ Fejl ved scraping af {category_url}: {e}")
        return []

def transcribe_with_transkriptor(video_url):
    if not TRANSKRIPTOR_API_KEY:
        print("❌ TRANSKRIPTOR_API_KEY mangler!")
        return None

    headers = {
        "Authorization": f"Bearer {TRANSKRIPTOR_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    start_url = "https://api.tor.app/developer/transcription/url"
    payload = {"url": video_url, "language": "da-DK"}

    try:
        response = requests.post(start_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        order_id = data.get('order_id')

        if not order_id:
            print(f"❌ Intet order_id i svar: {data}")
            return None

        print(f"      ⏳ Transskription startet – order_id: {order_id}")

        status_url = f"https://api.tor.app/developer/transcription/{order_id}"
        for attempt in range(60):
            time.sleep(10)
            status_response = requests.get(status_url, headers=headers, timeout=30)
            status_data = status_response.json()
            status = status_data.get('status', '').lower()

            if status == 'completed':
                content_url = f"https://api.tor.app/developer/files/{order_id}/content"
                content_response = requests.get(content_url, headers=headers, timeout=30)
                content_data = content_response.json()
                return content_data.get('content') or content_data.get('text') or str(content_data)
            elif status in ('error', 'failed'):
                print(f"❌ Fejl: {status_data.get('error', 'Ukendt')}")
                return None

            print(f"      ⏳ Venter... status: {status} ({attempt + 1}/60)")

        print("❌ Timeout")
        return None

    except Exception as e:
        print(f"❌ Fejl ved transskription: {e}")
        return None

def save_transcription(video_id, transcription, category):
    TRANSCRIPTIONS_FOLDER.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = TRANSCRIPTIONS_FOLDER / f"{category}_{video_id}_{timestamp}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(f"=== DNNK Webinar Transskription ===\n")
        f.write(f"Kategori: {category}\n")
        f.write(f"Video ID: {video_id}\n")
        f.write(f"URL: https://youtube.com/watch?v={video_id}\n")
        f.write(f"Transskriberet: {datetime.now().isoformat()}\n")
        f.write(f"\n{'='*50}\n\n")
        f.write(transcription)
    print(f"✅ Transskription gemt: {filename}")
    return filename

def main():
    print(f"\n{'='*60}")
    print(f"🔍 Starter tjek for nye webinarer - {datetime.now()}")
    print(f"📅 Cutoff dato: {CUTOFF_DATE} (kun videoer efter denne dato)")
    print(f"{'='*60}\n")

    processed_videos = load_processed_videos()
    new_videos_found = 0

    for category_name, category_url in CATEGORIES.items():
        print(f"\n📂 Tjekker kategori: {category_name}")
        video_ids = scrape_category_for_videos(category_url)
        print(f"   Fandt {len(video_ids)} videoer i alt")

        for video_id in video_ids:
            if video_id in processed_videos:
                continue

            # Tjek uploaddato
            upload_date = get_video_upload_date(video_id)

            if upload_date is None:
                print(f"   ⚠️ Springer over {video_id} – kunne ikke verificere dato")
                save_processed_video(video_id)
                continue

            if upload_date < CUTOFF_DATE:
                print(f"   ⏭️ Springer over {video_id} – uploadet {upload_date} (for gammel)")
                save_processed_video(video_id)
                continue

            print(f"\n   🆕 Ny video fundet: {video_id} (uploadet {upload_date})")
            print(f"      URL: https://youtube.com/watch?v={video_id}")
            print(f"      🎤 Starter transskription...")

            transcription = transcribe_with_transkriptor(
                f"https://youtube.com/watch?v={video_id}"
            )

            if transcription:
                save_transcription(video_id, transcription, category_name)
                save_processed_video(video_id)
                new_videos_found += 1
                print(f"      ✅ Transskription komplet!")
            else:
                print(f"      ❌ Transskription fejlede")

            time.sleep(2)

    print(f"\n{'='*60}")
    print(f"✅ Tjek komplet - {new_videos_found} nye videoer transskriberet")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
DNNK Webinar Auto-Transskription
Overvåger DNNK's vidensbank og transskriberer nye webinarer
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import time
from datetime import datetime
from pathlib import Path

# Konfiguration
TRANSKRIPTOR_API_KEY = os.environ.get('TRANSKRIPTOR_API_KEY')
TRANSCRIPTIONS_FOLDER = Path("transcriptions")
PROCESSED_VIDEOS_FILE = "processed_videos.json"

CATEGORIES = {
    "Tech_Talks": "https://www.dnnk.dk/tech-talks/",
    "Godmorgen_med_DNNK": "https://www.dnnk.dk/god-morgen-med-dnnk/",
    "Konferencer": "https://www.dnnk.dk/Optagelser fra konferencer og temadage",
    "Jura": "https://www.dnnk.dk/jura-i-klimatilpasning/",
    "DNNK_Masterclass": "https://www.dnnk.dk/dnnk-masterclass/",
    "Fremtidsvaerksted": "https://www.dnnk.dk/fremtid/",
    "Oevrige": "https://www.dnnk.dk/dnnk-arrangementer/"
}

def load_processed_videos():
    """Indlæs liste over allerede behandlede videoer"""
    if os.path.exists(PROCESSED_VIDEOS_FILE):
        with open(PROCESSED_VIDEOS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_processed_video(video_id):
    """Gem video ID som behandlet"""
    processed = load_processed_videos()
    if video_id not in processed:
        processed.append(video_id)
        with open(PROCESSED_VIDEOS_FILE, 'w') as f:
            json.dump(processed, f, indent=2)

def extract_youtube_id(url):
    """Udtræk YouTube video ID fra URL"""
    if 'youtu.be/' in url:
        return url.split('youtu.be/')[1].split('?')[0]
    elif 'youtube.com/watch?v=' in url:
        return url.split('v=')[1].split('&')[0]
    elif 'youtube.com/embed/' in url:
        return url.split('embed/')[1].split('?')[0]
    return None

def scrape_category_for_videos(category_url):
    """Scrape en kategori-side for YouTube videoer"""
    try:
        response = requests.get(category_url, timeout=30)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        youtube_urls = []
        
        # Find iframes (embedded videos)
        iframes = soup.find_all('iframe')
        for iframe in iframes:
            src = iframe.get('src', '')
            if 'youtube.com' in src or 'youtu.be' in src:
                video_id = extract_youtube_id(src)
                if video_id:
                    youtube_urls.append(video_id)
        
        # Find links til YouTube
        links = soup.find_all('a', href=True)
        for link in links:
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
    """Send YouTube video til Transkriptor API for transskription"""
    if not TRANSKRIPTOR_API_KEY:
        print("❌ TRANSKRIPTOR_API_KEY mangler!")
        return None
    
    endpoint = "https://api.transkriptor.com/v1/transcribe"
    
    headers = {
        "Authorization": f"Bearer {TRANSKRIPTOR_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "url": video_url,
        "language": "da",
        "output_format": "txt"
    }
    
    try:
        # Start transskription
        response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Vent på transskriptionen er klar
        job_id = data.get('job_id')
        max_attempts = 60
        
        for attempt in range(max_attempts):
            time.sleep(10)
            
            status_response = requests.get(
                f"{endpoint}/{job_id}",
                headers=headers,
                timeout=30
            )
            status_data = status_response.json()
            
            if status_data['status'] == 'completed':
                return status_data.get('transcription')
            elif status_data['status'] == 'failed':
                print(f"❌ Transskription fejlede: {status_data.get('error')}")
                return None
            
            print(f"   ⏳ Venter... ({attempt + 1}/{max_attempts})")
        
        print("❌ Timeout: Transskription tog for lang tid")
        return None
            
    except Exception as e:
        print(f"❌ Fejl ved transskription: {e}")
        return None

def save_transcription(video_id, transcription, category):
    """Gem transskription som fil"""
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
    """Hovedfunktion - tjek for nye webinarer og transskriber dem"""
    print(f"\n{'='*60}")
    print(f"🔍 Starter tjek for nye webinarer - {datetime.now()}")
    print(f"{'='*60}\n")
    
    processed_videos = load_processed_videos()
    new_videos_found = 0
    
    for category_name, category_url in CATEGORIES.items():
        print(f"\n📂 Tjekker kategori: {category_name}")
        
        # Find alle YouTube videoer på siden
        video_ids = scrape_category_for_videos(category_url)
        print(f"   Fandt {len(video_ids)} videoer i alt")
        
        new_in_category = 0
        for video_id in video_ids:
            if video_id in processed_videos:
                continue
            
            print(f"\n   🆕 Ny video fundet: {video_id}")
            print(f"      URL: https://youtube.com/watch?v={video_id}")
            
            # Transskriber med Transkriptor
            video_url = f"https://youtube.com/watch?v={video_id}"
            print(f"      🎤 Starter transskription...")
            
            transcription = transcribe_with_transkriptor(video_url)
            
            if transcription:
                # Gem transskription
                save_transcription(video_id, transcription, category_name)
                
                # Marker som behandlet
                save_processed_video(video_id)
                new_videos_found += 1
                new_in_category += 1
                
                print(f"      ✅ Transskription komplet!")
            else:
                print(f"      ❌ Transskription fejlede")
            
            # Vent lidt mellem hver video
            time.sleep(2)
        
        if new_in_category == 0:
            print(f"   ✓ Ingen nye videoer i denne kategori")
    
    print(f"\n{'='*60}")
    print(f"✅ Tjek komplet - {new_videos_found} nye videoer transskriberet")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()

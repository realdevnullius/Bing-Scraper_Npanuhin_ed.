# ==============================================================================
# BING WALLPAPER ARCHIVE PIPELINE (SINGLE-THREADED ENGINE)
# ==============================================================================
# THE WHY:
#   Maintains a sequential, single-threaded pipeline execution model for maximum
#   portability, minimal dependency overhead, and simple procedural tracing.
#
# THE HOW:
#   Iterates through the dataset one item at a time, checking disk state,
#   fetching images via standard requests.Session, and updating terminal output.
# ==============================================================================

import os
import time
import json
import sys
import re
import requests
import piexif
from PIL import Image

# Enable Virtual Terminal Processing on Windows consoles for ANSI control
if sys.platform == "win32":
    os.system('')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# PIPELINE CONFIGURATION
FLATTEN_OUTPUT = False

JSON_URL = "https://bing.npanuhin.me/all.json"
LOCAL_JSON_PATH = os.path.join(SCRIPT_DIR, "all.json.latest")
DOWNLOAD_DIR = os.path.join(SCRIPT_DIR, "_OUT")

REGIONS = {
    'us': 'US-en', 'uk': 'GB-en', 'de': 'DE-de', 'fr': 'FR-fr',
    'ja': 'JP-ja', 'au': 'AU-en', 'cn': 'CN-zh', 'ca': 'CA-en',
    'in': 'IN-en', 'br': 'BR-pt', 'row': 'ROW-en'
}

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}


class PipelineMonitor:
    """
    Thread-safe monitor tracking byte-throughput, ETA, and 
    flicker-free console redraws with strictly aligned ASCII borders.
    """
    def __init__(self, total_tasks):
        self.total_tasks = total_tasks
        self.processed = 0
        self.skipped = 0
        self.uhd_downloads = 0
        self.hd_downloads = 0
        self.failed = 0
        self.total_bytes = 0
        self.start_time = time.time()
        self.recent_transfers = []  # List of (timestamp, bytes)
        self.rendered_lines = 0

    def record_result(self, status_type, bytes_count=0):
        now = time.time()
        self.processed += 1
        if status_type == "SKIPPED":
            self.skipped += 1
        elif status_type == "UHD":
            self.uhd_downloads += 1
            self.total_bytes += bytes_count
            self.recent_transfers.append((now, bytes_count))
        elif status_type == "HD":
            self.hd_downloads += 1
            self.total_bytes += bytes_count
            self.recent_transfers.append((now, bytes_count))
        elif status_type == "FAILED":
            self.failed += 1

        # 10-second rolling speed window calculation
        cutoff = now - 10.0
        self.recent_transfers = [t for t in self.recent_transfers if t[0] >= cutoff]

        self.render_dashboard()

    def render_dashboard(self):
        elapsed = time.time() - self.start_time
        downloaded_count = self.uhd_downloads + self.hd_downloads

        percentage = (self.processed / self.total_tasks * 100) if self.total_tasks > 0 else 100.0
        bar_length = 20
        filled_len = int(bar_length * self.processed // self.total_tasks) if self.total_tasks > 0 else bar_length
        bar = "=" * filled_len + (">" if filled_len < bar_length else "")
        bar = bar.ljust(bar_length)

        items_remaining = self.total_tasks - self.processed
        rate = self.processed / elapsed if elapsed > 0 else 0
        eta_seconds = int(items_remaining / rate) if rate > 0 else 0
        eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(int(elapsed)))

        window_time = min(elapsed, 10.0)
        recent_bytes = sum(b for t, b in self.recent_transfers)
        recent_count = len(self.recent_transfers)
        speed_mbps = (recent_bytes / (1024 * 1024)) / window_time if window_time > 0 else 0.0
        speed_imgs = recent_count / window_time if window_time > 0 else 0.0

        total_mb = self.total_bytes / (1024 * 1024)
        avg_mb = (total_mb / downloaded_count) if downloaded_count > 0 else 0.0

        # Dynamic ASCII labels formatted to exactly 64 characters to fit perfectly in a 68-character outer box
        lbl_unique   = f"Total Unique Items Processed : {self.processed:,}"
        lbl_skipped  = f"Already Up-to-Date (Skipped) : {self.skipped:,}"
        lbl_download = f"New Wallpapers Downloaded    : {downloaded_count:,}"
        lbl_uhd      = f"  +-- New UHD (4K) Quality   : {self.uhd_downloads:,}"
        lbl_hd       = f"  +-- New HD Quality         : {self.hd_downloads:,}"
        lbl_failed   = f"Failed / Unavailable Assets  : {self.failed:,}"
        lbl_payload  = f"Total Payload Downloaded     : {total_mb:.2f} MB"
        lbl_avg_size = f"Average Image Payload Size   : {avg_mb:.2f} MB"
        lbl_speed    = f"Current Network Speed        : {speed_mbps:.2f} MB/s ({speed_imgs:.0f} img/s)"
        lbl_elapsed  = f"Total Pipeline Execution Time: {elapsed_str}"

        lines = [
            f"[*] PROGRESS: [{bar}] {percentage:5.1f}% | {self.processed:,}/{self.total_tasks:,} items | ETA: {eta_str}",
            "+------------------------------------------------------------------+",
            "| REAL-TIME PIPELINE EXECUTION MONITOR                             |",
            "+------------------------------------------------------------------+",
            f"| {lbl_unique:<64} |",
            f"| {lbl_skipped:<64} |",
            f"| {lbl_download:<64} |",
            f"| {lbl_uhd:<64} |",
            f"| {lbl_hd:<64} |",
            f"| {lbl_failed:<64} |",
            f"| {lbl_payload:<64} |",
            f"| {lbl_avg_size:<64} |",
            f"| {lbl_speed:<64} |",
            f"| {lbl_elapsed:<64} |",
            "+------------------------------------------------------------------+"
        ]

        if self.rendered_lines > 0:
            sys.stdout.write(f"\033[{self.rendered_lines}F")

        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        self.rendered_lines = len(lines)


def print_ascii_banner():
    banner = """
================================================================================
 ____                    ____
|  _ \ | _ __   __ _    / ___|  ___ _ __ __ _ _ __   ___ _ __
| |_) | | '_ \ / _` |  \___ \ / __| '__/ _` | '_ \ / _ \ '__|
|  _ <| | | | | (_| |   ___) | (__| | | (_| | |_) |  __/ |
|____/|_|_| |_|\__, |  |____/ \___|_|  \__,_| .__/ \___|_|
               |___/                        |_|
               (Single-Threaded Engine)
================================================================================"""
    print(banner)


def sync_central_database(session):
    CACHE_TTL_SECONDS = 5 * 3600
    print("[*] Initialising remote database synchronization routine...")

    if os.path.exists(LOCAL_JSON_PATH):
        file_age = time.time() - os.path.getmtime(LOCAL_JSON_PATH)
        if file_age < CACHE_TTL_SECONDS:
            hours_old = file_age / 3600
            print(f"[ ] Cache hit! 'all.json.latest' is {hours_old:.2f} hours old (< 5 hours). Skipping download.")
            return True

    print("[*] Cache expired or missing. Refreshing from endpoint...")
    print(f"[*] Target Endpoint: {JSON_URL}")

    api_headers = {
        "User-Agent": DEFAULT_HEADERS["User-Agent"],
        "Accept": "application/json",
        "Connection": "keep-alive"
    }

    try:
        response = session.get(JSON_URL, headers=api_headers, timeout=60)
        if response.status_code == 200:
            parsed_json = response.json()
            with open(LOCAL_JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump(parsed_json, f, indent=4, ensure_ascii=False)

            final_size = os.path.getsize(LOCAL_JSON_PATH)
            print(f"[ ] Sync complete! all.json.latest refreshed successfully ({final_size / (1024*1024):.2f} MB).")
            return True
        else:
            print(f"[!] HTTP Status Code: {response.status_code}")
            return False
    except Exception as e:
        print(f"[!] Critical network failure during database ingestion: {e}")
        if os.path.exists(LOCAL_JSON_PATH):
            print("[!] Falling back to existing local 'all.json.latest' file.")
            return True
        return False


def verify_and_inject_metadata(file_path, title, description, copyright_text):
    """Validates image integrity with Pillow and writes EXIF headers with piexif."""
    try:
        if os.path.getsize(file_path) == 0:
            return False

        with Image.open(file_path) as img:
            img.verify()

        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}, "thumbnail": None}

        if title:
            exif_dict["0th"][0x9c9b] = title.encode('utf-16le')
            exif_dict["0th"][0x010e] = title.encode('utf-8')

        if description:
            exif_dict["0th"][0x9c9c] = description.encode('utf-16le')

        if copyright_text:
            exif_dict["0th"][0x8298] = copyright_text.encode('utf-8')

        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, file_path)
        return True
    except Exception:
        if os.path.exists(file_path):
            os.remove(file_path)
        return False


def clean_title(title_str):
    if not title_str:
        return "BingImage"

    stop_words = {
        'the', 'in', 'on', 'at', 'of', 'and', 'a', 'an', 'to', 'for', 'with', 'off',
        'from', 'by', 'as', 'between', 'among', 'into', 'over', 'through', 'about',
        'under', 'above', 'during', 'without', 'against', 'including', 'across'
    }

    clean = re.sub(r'[\x00-\x1f\\/:*?"<>|,\. !?’’“” ]|，|。|！|＿|：', ' ', title_str)
    words = clean.split()
    filtered_words = [w.capitalize() if w.isascii() else w for w in words if w.lower() not in stop_words]

    if not filtered_words:
        return "BingImage"

    raw_cleaned = " ".join(filtered_words)
    return raw_cleaned[:60].rstrip(' ') if len(raw_cleaned) > 60 else raw_cleaned


def load_local_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        if not content.endswith('}'):
            content += '}' if content.endswith(']') else ']}'
        try:
            return json.loads(content)
        except Exception:
            return None


def extract_ms_code(url, default_quality="HD"):
    if not url:
        return default_quality

    raw = url
    if "id=OHR." in raw:
        raw = raw.split("id=OHR.")[-1]
    elif "/OHR." in raw:
        raw = raw.split("/OHR.")[-1]
    elif "OHR." in raw:
        raw = raw.split("OHR.")[-1]

    raw = raw.split("&")[0].split("?")[0]
    raw = re.sub(r'\.(jpg|jpeg|png)$', '', raw, flags=re.IGNORECASE)

    quality_tag = "UHD" if "uhd" in url.lower() else "HD"

    m = re.search(r'([A-Za-z]{2,4}-?[A-Za-z]{2,4}?\d{5,12})', raw, re.IGNORECASE)
    if m:
        return f"{m.group(1)}_{quality_tag}"

    m = re.search(r'([A-Za-z]{2,4}-[A-Za-z]{2,4}|ROW)', raw, re.IGNORECASE)
    if m:
        return f"{m.group(1)}_{quality_tag}"

    return quality_tag


def fetch_and_write(session, url, target_path, title, description, copyright_text):
    """Downloads payload into a temporary binary file before verifying."""
    tmp_path = f"{target_path}.tmp"
    try:
        response = session.get(url, headers=DEFAULT_HEADERS, timeout=20, stream=True)
        if response.status_code == 200:
            with open(tmp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=65536):
                    f.write(chunk)

            success = verify_and_inject_metadata(tmp_path, title, description, copyright_text)

            if success:
                os.replace(tmp_path, target_path)
                return True, os.path.getsize(target_path)
    except Exception:
        pass
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return False, 0


def download_single_wallpaper(task, session):
    """Managed download unit handling resolution upgrading and fallbacks."""
    date_str, img_name, img_url, title, description, copyright_text = task

    digits_only = re.sub(r'\D', '', str(date_str)) if date_str else ""

    if len(digits_only) >= 6:
        year_str, month_str = digits_only[:4], digits_only[4:6]
        date_prefix = digits_only[:8] if len(digits_only) >= 8 else digits_only
    elif len(digits_only) >= 4:
        year_str, month_str, date_prefix = digits_only[:4], None, digits_only[:4]
    else:
        year_str, month_str, date_prefix = "0000", None, "0000"

    if FLATTEN_OUTPUT:
        target_folder = DOWNLOAD_DIR
    else:
        if year_str == "0000":
            target_folder = os.path.join(DOWNLOAD_DIR, "0000")
        elif month_str:
            target_folder = os.path.join(DOWNLOAD_DIR, year_str, month_str)
        else:
            target_folder = os.path.join(DOWNLOAD_DIR, year_str)

    os.makedirs(target_folder, exist_ok=True)

    # Resolution URL target generation
    if "1920x1080" in img_url:
        target_url = img_url.replace("1920x1080", "UHD")
    elif "1366x768" in img_url:
        target_url = img_url.replace("1366x768", "UHD")
    elif "_UHD.jpg" in img_url:
        target_url = img_url
    else:
        target_url = img_url + "&rf=LaDigue_UHD.jpg"

    if target_url.startswith("/"):
        target_url = "https://bing.com" + target_url
    elif "bing.com" in target_url and not target_url.startswith("http"):
        target_url = "https://" + target_url

    fallback_url = "https://bing.com" + img_url if img_url.startswith("/") else img_url
    if "bing.com" in fallback_url and not fallback_url.startswith("http"):
        fallback_url = "https://" + fallback_url

    uhd_code = extract_ms_code(target_url, default_quality="UHD")
    uhd_file_path = os.path.join(target_folder, f"{date_prefix}_{img_name} ({uhd_code}).jpg")

    hd_code = extract_ms_code(fallback_url, default_quality="HD")
    hd_file_path = os.path.join(target_folder, f"{date_prefix}_{img_name} ({hd_code}).jpg")

    legacy_file_path = os.path.join(target_folder, f"{date_prefix}_{img_name}.jpg")

    # Fast existence check
    if (os.path.exists(uhd_file_path) and os.path.getsize(uhd_file_path) > 0) or \
       (os.path.exists(hd_file_path) and os.path.getsize(hd_file_path) > 0) or \
       (os.path.exists(legacy_file_path) and os.path.getsize(legacy_file_path) > 0):
        return ("SKIPPED", 0)

    # Attempt 1: 4K UHD
    ok, bytes_count = fetch_and_write(session, target_url, uhd_file_path, title, description, copyright_text)
    if ok:
        return ("UHD", bytes_count)

    # Attempt 2: 1080p HD Fallback
    ok, bytes_count = fetch_and_write(session, fallback_url, hd_file_path, title, description, copyright_text)
    if ok:
        return ("HD", bytes_count)

    return ("FAILED", 0)


def main():
    print_ascii_banner()
    print("[*] Initialising Bing Wallpaper Synchroniser (Single-Threaded Engine)\n")

    session = requests.Session()
    sync_central_database(session)
    print("-" * 60)

    print(f"[*] Reading local JSON database: {LOCAL_JSON_PATH}")
    if not os.path.exists(LOCAL_JSON_PATH):
        print("[!] CRITICAL ERROR: all.json.latest is missing!")
        return

    db = load_local_json(LOCAL_JSON_PATH)
    if not db:
        print("[!] CRITICAL ERROR: Could not parse all.json.latest!")
        return

    total_entries = sum(len(entries) for entries in db.values() if isinstance(entries, list))
    print(f"[+] Successfully loaded {total_entries} entries from database schema.")

    unique_wallpapers = {}

    for short_name, json_key in REGIONS.items():
        actual_key = next((k for k in db.keys() if k.lower() == json_key.lower()), None)
        if not actual_key:
            continue

        for entry in db[actual_key]:
            date_str = entry.get('date')
            bing_url = entry.get('bing_url')
            storage_url = entry.get('url')
            title = entry.get('title')
            caption = entry.get('caption')
            description = entry.get('description')
            copyright_text = entry.get('copyright')

            img_url = bing_url if bing_url else storage_url
            if not img_url:
                continue

            try:
                if "id=OHR." in img_url:
                    raw_part = img_url.split("id=OHR.")[-1]
                    base_key = re.split(r'_[A-Za-z]{2}-[A-Za-z]{2}|_[A-Za-z]{3,4}\d', raw_part)[0].lower()
                else:
                    base_key = img_url.split("/")[-1].split("_")[0].replace(".jpg", "").lower()
            except Exception:
                base_key = date_str.replace("-", "") if date_str else "0000"

            if not base_key or len(base_key) < 3 or base_key in ["bingimage", "wallpaper", "image"]:
                base_key = f"date_{date_str.replace('-', '')}" if date_str else "date_0000"

            if base_key:
                base_key = re.sub(r'(\d{2})y$', r'20\1', base_key)
                if 'lanterfestival' in base_key:
                    base_key = base_key.replace('lanterfestival', 'lanternfestival')

            img_name = None
            if title and title.strip():
                img_name = clean_title(title)
            if not img_name and caption and caption.strip() and caption.lower() != "info":
                img_name = clean_title(caption)
            if not img_name and entry.get('name'):
                img_name = entry.get('name')

            if not img_name or img_name.lower() in ["bingimage", "wallpaper", "image"]:
                if base_key and not base_key.startswith("date_"):
                    working_name = base_key
                    bing_keywords = [
                        'day', 'season', 'festival', 'summer', 'spring', 'autumn', 'winter',
                        'labor', 'work', 'may', 'sky', 'tree', 'tower', 'bridge', 'beach',
                        'bay', 'lake', 'river', 'park', 'shiba', 'zakura', 'showa', 'era',
                        'lunar', 'new', 'year', 'eve', 'of', 'lantern'
                    ]
                    for kw in bing_keywords:
                        working_name = re.sub(
                            f'(?<=[A-Za-z])({kw})(?=[A-Za-z])|(?<=[A-Za-z])({kw})$|^({kw})(?=[A-Za-z])',
                            r' \1\2\3 ', working_name, flags=re.IGNORECASE
                        )

                    working_name = working_name if any(c.isupper() for c in working_name) else working_name.capitalize()
                    working_name = re.sub(r'(?<!^)(?=[A-Z])', ' ', working_name)
                    working_name = re.sub(r'\b25\b', '2025', str(working_name))
                    working_name = re.sub(r'\b26\b', '2026', str(working_name))
                    working_name = re.sub(r'(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])', ' ', working_name)
                    img_name = clean_title(working_name)

            fallback_suffix = date_str.replace('-', '') if date_str else "0000"
            if not img_name or img_name.lower() in ["bingimage", "wallpaper", "image"] or len(img_name) < 3:
                img_name = f"Wallpaper_{fallback_suffix}"

            if base_key not in unique_wallpapers:
                unique_wallpapers[base_key] = (date_str, img_name, img_url, title, description, copyright_text)
            else:
                existing_task = unique_wallpapers[base_key]
                existing_name = existing_task[1]
                is_existing_generic = existing_name.lower().startswith("wallpaper_") or existing_name.lower().startswith("bingimage_")
                is_new_better = not img_name.lower().startswith("wallpaper_") and not img_name.lower().startswith("bingimage_")

                if (is_existing_generic and is_new_better) or (short_name in ['us', 'uk'] and is_new_better):
                    unique_wallpapers[base_key] = (date_str, img_name, img_url, title, description, copyright_text)

    download_queue = list(unique_wallpapers.values())
    download_queue.sort(key=lambda x: x[0] if x[0] else "", reverse=True)

    total_tasks = len(download_queue)
    print(f"[+] Cross-date deduplication complete: {total_tasks} unique download tasks queued.\n")

    monitor = PipelineMonitor(total_tasks)

    for task in download_queue:
        status_type, bytes_count = download_single_wallpaper(task, session)
        monitor.record_result(status_type, bytes_count)

    print(f"\n\n[ ] Outstanding! Archiving process complete\nin:\n{DOWNLOAD_DIR}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[!] Operation cancelled by user. Exiting gracefully...")
        sys.exit(0)
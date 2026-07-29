# ==============================================================================
# BING WALLPAPER ARCHIVE PIPELINE (SINGLE-THREADED + REALTIME MONITOR)
# ==============================================================================
# SENIOR DEV (WHY):
#   This module serves as an idempotent, cross-region ingest engine for Bing's
#   global image archive. It resolves local pathing, manages cache sync TTLs,
#   deduplicates multi-market assets in RAM, enforces maximum available payload 
#   resolution (4K UHD over 1080p HD), verifies payload binary health, and writes 
#   UTF-16LE Byte Order Mark (BOM) encoded EXIF/IPTC tags into the final JPEGs.
#   It incorporates an in-memory thread-safe visual dashboard for real-time telemetry.
#
# JUNIOR DEV (HOW):
#   We import standard Python libraries along with extra utilities ('threading', 
#   'requests', 'piexif', 'Pillow/PIL') to handle image downloads, file metadata, 
#   terminal ANSI sequences, and a live updating progress dashboard.
# ==============================================================================

import os
import time
import json
import sys
import re
import requests
import piexif
import threading
from PIL import Image

# SENIOR DEV (WHY):
#   Enables Virtual Terminal Processing mode on Windows 10/11 consoles to properly 
#   interpret VT100/ANSI cursor control escape codes (`\033[F`) for dynamic line rewriting.
# JUNIOR DEV (HOW):
#   Calling `os.system('')` tricks Windows command prompt into enabling colored/styled terminal output.
if sys.platform == "win32":
    os.system('')

# SENIOR DEV (WHY):
#   Anchor all file path calculations dynamically to the script's actual file system
#   location rather than current working directory (CWD). This prevents broken paths
#   when called via scheduled tasks, batch files, or relative shell invocation.
# JUNIOR DEV (HOW):
#   __file__ gets the current script file, abspath cleans it up, and dirname gives
#   us the folder path where this script actually sits on the hard drive.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ARCHITECTURAL PATH ROUTING STRATEGY:
# False -> Persists assets inside structured hierarchical subdirectories (e.g., _OUT\2026\07\image.jpg)
# True  -> Flattens the dependency graph and writes assets directly into root (e.g., _OUT\image.jpg)
FLATTEN_OUTPUT = False

# SENIOR DEV (WHY):
#   The npanuhin/bing-wallpaper index aggregates daily endpoint telemetry across 11 regions.
#   Targeting 'all.json' gives us a unified, normalized database manifest instead of issuing 
#   hundreds of fragmented API calls to Microsoft Bing directly.
# JUNIOR DEV (HOW):
#   These variables store our target online database link, where we cache the file 
#   locally ('all.json.latest'), and the main target folder ('_OUT') where images are saved.
JSON_URL = "https://bing.npanuhin.me/all.json"

LOCAL_JSON_PATH = os.path.join(SCRIPT_DIR, "all.json.latest")
DOWNLOAD_DIR = os.path.join(SCRIPT_DIR, "_OUT")

# SENIOR DEV (WHY):
#   Bing serves different daily wallpapers or localized title variants per market. 
#   Mapping these keys standardizes cross-region scanning across Microsoft's regional hubs.
# JUNIOR DEV (HOW):
#   A dictionary connecting simple region names (like 'us', 'de') to their full
#   Microsoft country-language locale keys (like 'US-en', 'DE-de').
REGIONS = {
    'us': 'US-en', 'uk': 'GB-en', 'de': 'DE-de', 'fr': 'FR-fr',
    'ja': 'JP-ja', 'au': 'AU-en', 'cn': 'CN-zh', 'ca': 'CA-en',
    'in': 'IN-en', 'br': 'BR-pt', 'row': 'ROW-en'
}

# SENIOR DEV (WHY):
#   Ensures destination workspace exists before any network socket open calls, avoiding I/O race conditions.
# JUNIOR DEV (HOW):
#   Creates the '_OUT' folder if it doesn't exist yet; 'exist_ok=True' prevents errors if it's already there.
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# SENIOR DEV (WHY):
#   Bypasses aggressive CDN edge rate-limiting/blocking targeting generic Python HTTP clients.
# JUNIOR DEV (HOW):
#   A dictionary containing a modern Chrome browser string to make our network requests look like real user traffic.
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
}


class PipelineMonitor:
    """
    SENIOR DEV (WHY):
      Aggregates real-time execution statistics, byte throughput metrics, ETA projections,
      and dynamic UI framing. Employs ANSI cursor control sequence rewrites (`\033[{lines}F`) 
      to produce a zero-flicker terminal dashboard without full console screen clears.

    JUNIOR DEV (HOW):
      1. Keeps track of total processed items, skipped items, UHD downloads, HD downloads, and bytes.
      2. Computes execution speed (MB/s and images/sec) using a rolling 10-second window.
      3. Draws a clean ASCII progress bar and execution table on screen, updating it line-by-line.
    """
    def __init__(self, total_tasks):
        self.lock = threading.Lock()
        self.total_tasks = total_tasks
        self.processed = 0
        self.skipped = 0
        self.uhd_downloads = 0
        self.hd_downloads = 0
        self.failed = 0
        self.total_bytes = 0
        self.start_time = time.time()
        self.recent_transfers = []  # List of (timestamp, bytes_downloaded)
        self.rendered_lines = 0

    def record_result(self, status_type, bytes_count=0):
        with self.lock:
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

            # Keep rolling window of last 10 seconds for transfer speed calculation
            cutoff = now - 10.0
            self.recent_transfers = [t for t in self.recent_transfers if t[0] >= cutoff]

            self.render_dashboard()

    def render_dashboard(self):
        elapsed = time.time() - self.start_time
        downloaded_count = self.uhd_downloads + self.hd_downloads
        
        # Progress Bar calculation
        percentage = (self.processed / self.total_tasks * 100) if self.total_tasks > 0 else 100.0
        bar_length = 20
        filled_len = int(bar_length * self.processed // self.total_tasks) if self.total_tasks > 0 else bar_length
        bar = "=" * filled_len + (">" if filled_len < bar_length else "")
        bar = bar.ljust(bar_length)

        # ETA calculation
        items_remaining = self.total_tasks - self.processed
        rate = self.processed / elapsed if elapsed > 0 else 0
        eta_seconds = int(items_remaining / rate) if rate > 0 else 0
        eta_str = time.strftime("%H:%M:%S", time.gmtime(eta_seconds))
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(int(elapsed)))

        # Network speed calculation (rolling 10s window)
        window_time = min(elapsed, 10.0)
        recent_bytes = sum(b for t, b in self.recent_transfers)
        recent_count = len(self.recent_transfers)
        speed_mbps = (recent_bytes / (1024 * 1024)) / window_time if window_time > 0 else 0.0
        speed_imgs = recent_count / window_time if window_time > 0 else 0.0

        # Payload Metrics
        total_mb = self.total_bytes / (1024 * 1024)
        avg_mb = (total_mb / downloaded_count) if downloaded_count > 0 else 0.0

        lines = [
            f"[*] PROGRESS: [{bar}] {percentage:5.1f}% | {self.processed:,}/{self.total_tasks:,} items | ETA: {eta_str}",
            "+------------------------------------------------------------------+",
            "| REAL-TIME PIPELINE EXECUTION MONITOR                             |",
            "+------------------------------------------------------------------+",
            f"| Total Unique Items Processed : {self.processed:<35,}|",
            f"| Already Up-to-Date (Skipped) : {self.skipped:<35,}|",
            f"| New Wallpapers Downloaded    : {downloaded_count:<35,}|",
            f"|   ├── New UHD (4K) Quality   : {self.uhd_downloads:<35,}|",
            f"|   └── New HD Quality         : {self.hd_downloads:<35,}|",
            f"| Failed / Unavailable Assets  : {self.failed:<35,}|",
            f"| Total Payload Downloaded     : {total_mb:<32.2f} MB |",
            f"| Average Image Payload Size   : {avg_mb:<32.2f} MB |",
            f"| Current Network Speed        : {speed_mbps:<5.2f} MB/s ({speed_imgs:<2.0f} img/s)".ljust(67) + "|",
            f"| Total Pipeline Execution Time: {elapsed_str:<35}|",
            "+------------------------------------------------------------------+"
        ]

        # Rewind cursor to overwrite previous dashboard frame
        if self.rendered_lines > 0:
            sys.stdout.write(f"\033[{self.rendered_lines}F")

        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        self.rendered_lines = len(lines)


def print_ascii_banner():
    """
    SENIOR DEV (WHY):
      Renders standardized ASCII branding banner for console visual clarity.
    JUNIOR DEV (HOW):
      Prints the large multi-line 'Bing Backgrounds' text block on script start.
    """
    banner = """
================================================================================
 ____                   ____
|  _ \ | _ __   __ _   / ___|  ___ _ __ __ _ _ __   ___ _ __
| |_) | | '_ \ / _` |  \___ \ / __| '__/ _` | '_ \ / _ \ '__|
|  _ <| | | | | (_| |   ___) | (__| | | (_| | |_) |  __/ |
|____/|_|_| |_|\__, |  |____/ \___|_|  \__,_| .__/ \___|_|
               |___/                        |_|
               (Npanuhin Edition - multi-threaded version)
================================================================================"""
    print(banner)


def sync_central_database():
    """
    SENIOR DEV (WHY):
      Manages remote manifest ingestion with a strict 5-hour Time-To-Live (TTL) cache.
      Prevents redundant egress bandwidth usage and CDN socket strain on frequent script execution.
      Includes graceful fallback to stale local database during network outages.

    JUNIOR DEV (HOW):
      1. Checks if 'all.json.latest' exists locally.
      2. Measures its file age; if younger than 5 hours (18,000 seconds), skips network download.
      3. If missing or expired, downloads the remote JSON and writes it cleanly formatted to disk.
      4. If network fails, catches the error and reuses local JSON if available.
    """
    CACHE_TTL_SECONDS = 5 * 3600  # 5 hours

    print(f"[*] Initialising remote database synchronization routine...")

    # Check if local cache exists and is younger than 5 hours
    if os.path.exists(LOCAL_JSON_PATH):
        file_age = time.time() - os.path.getmtime(LOCAL_JSON_PATH)
        if file_age < CACHE_TTL_SECONDS:
            hours_old = file_age / 3600
            print(f"[ ] Cache hit! 'all.json.latest' is {hours_old:.2f} hours old (< 5 hours). Skipping download. ⚡")
            return True

    print(f"[*] Cache expired or missing. Refreshing from endpoint...")
    print(f"[*] Target Endpoint: {JSON_URL}")

    api_headers = {
        "User-Agent": headers["User-Agent"],
        "Accept": "application/json",
        "Connection": "keep-alive"
    }

    try:
        response = requests.get(JSON_URL, headers=api_headers, timeout=60)
        if response.status_code == 200:
            parsed_json = response.json()
            with open(LOCAL_JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump(parsed_json, f, indent=4, ensure_ascii=False)

            final_size = os.path.getsize(LOCAL_JSON_PATH)
            print(f"[ ] Sync complete! all.json.latest refreshed successfully 🎉 ({final_size / (1024*1024):.2f} MB).")
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


def inject_metadata_iptc(file_path, title, description, copyright_text):
    """
    SENIOR DEV (WHY):
      Injects image metadata directly into JPEG APP1 binary headers using EXIF/IPTC specs.
      Applies UTF-16LE Byte Order Mark (BOM) encoding to Windows XP specific tags (0x9c9b, 0x9c9c)
      and UTF-8 to standard tags (0x010e, 0x8298). This guarantees full native compatibility 
      with Windows Explorer properties, legacy DAM systems, and desktop wallpaper tools.

    JUNIOR DEV (HOW):
      1. Builds a Python dictionary structured for EXIF tags.
      2. Converts title, description, and copyright strings into byte data with correct encodings.
      3. Uses 'piexif.dump()' to generate binary EXIF byte arrays.
      4. Writes these bytes directly into the downloaded JPEG file header.
    """
    try:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "Interop": {}, "1st": {}, "thumbnail": None}

        if title:
            exif_dict["0th"][0x9c9b] = title.encode('utf-16le')  # Windows XP Title
            exif_dict["0th"][0x010e] = title.encode('utf-8')     # Standard Image Description

        if description:
            exif_dict["0th"][0x9c9c] = description.encode('utf-16le')  # Windows XP Comment/Subject

        if copyright_text:
            exif_dict["0th"][0x8298] = copyright_text.encode('utf-8')   # Standard Copyright Tag

        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, file_path)
        return True
    except Exception as e:
        print(f" [Warning] Shell metadata injection vector failed: {e}")
        return False


def clean_title(title_str):
    """
    SENIOR DEV (WHY):
      Sanitizes descriptive text for cross-platform OS filename safety. Strips non-printable
      ASCII control codes and Windows illegal path characters (\ / : * ? " < > |). 
      Filters non-informational English stop-words to optimize character economy while preserving 
      full international CJK / Non-Latin UTF-8 script readability.

    JUNIOR DEV (HOW):
      1. Returns 'BingImage' if text is empty.
      2. Uses regular expressions (re.sub) to replace bad filename characters with spaces.
      3. Splits words, removes common filler words (like 'the', 'in', 'on'), and capitalizes ASCII words.
      4. Truncates final string length cleanly at max 60 characters.
    """
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
    """
    SENIOR DEV (WHY):
      Handles fault-tolerant JSON payload reading. Mitigates potential issues with truncated
      or improperly terminated local JSON files by dynamically appending missing structural 
      closing brackets before throwing parsing failures.

    JUNIOR DEV (HOW):
      1. Opens file using UTF-8 text encoding.
      2. Tries reading with standard 'json.loads()'.
      3. If JSON syntax is broken at EOF, attempts to append missing closing '}' or ']}' and retries.
    """
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
    """
    Extracts Microsoft Bing market codes and asset IDs.
    Normalizes resolution tags to either 'UHD' or 'HD', stripping
    dimension metrics (e.g. 1920x1080) from final target names.

    SENIOR DEV (WHY):
      Parses Microsoft's unique asset key from Bing CDN query strings (e.g., OHR.GrandCanyon_EN-US12345).
      Appending normalized market tags (EN-US_UHD) directly to filenames ensures strict identity tracking
      and prevents collisions between localized renditions of identical images.

    JUNIOR DEV (HOW):
      1. Strips out URL query params, keeping just the image key.
      2. Determines if URL string requests 'uhd' or standard 'hd'.
      3. Uses RegEx to match Market Codes + Asset IDs (like 'EN-US0450019921') or base region keys ('ROW').
      4. Combines market ID with quality tag (e.g., 'EN-US0450019921_UHD').
    """
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

    # Determine Quality Tag (UHD vs HD)
    if "uhd" in url.lower():
        quality_tag = "UHD"
    else:
        quality_tag = "HD"

    # 1. Full Market Code + ID (e.g., EN-US0450019921 or ZH-CN12345)
    m = re.search(r'([A-Za-z]{2,4}-?[A-Za-z]{2,4}?\d{5,12})', raw, re.IGNORECASE)
    if m:
        return f"{m.group(1)}_{quality_tag}"

    # 2. Market Code alone without numeric ID (e.g., EN-US, DE-DE, ROW)
    m = re.search(r'([A-Za-z]{2,4}-[A-Za-z]{2,4}|ROW)', raw, re.IGNORECASE)
    if m:
        return f"{m.group(1)}_{quality_tag}"

    # 3. Fallback -> Returns 'UHD' or 'HD'
    return quality_tag


def download_single_wallpaper(task):
    """
    SENIOR DEV (WHY):
      Core asset ingest unit. Performs URL manipulation to upgrade standard 1080p stream parameters
      to 4K Ultra HD endpoints (`_UHD.jpg`). Validates binary stream payload integrity using 
      Pillow's `Image.verify()` prior to writing EXIF metadata, cleaning up partial/corrupted byte
      streams on failure before trying standard HD fallback routes.
      Returns a tuple `(STATUS_TYPE, FILE_SIZE_BYTES)` consumed directly by the PipelineMonitor dashboard.

    JUNIOR DEV (HOW):
      1. Unpacks task metadata (date, titles, URLs).
      2. Calculates target directory structure (`_OUT\YYYY\MM\` or flat `_OUT\`).
      3. Constructs 4K UHD URL target and HD Fallback URL target.
      4. Checks if target file already exists on disk (if found, returns ("SKIPPED", 0)).
      5. Downloads 4K UHD image in binary chunks; verifies image health using Pillow (`Image.verify()`).
      6. Injects metadata tags into image header, returning ("UHD", byte_size).
      7. If 4K download fails, attempts fallback download of standard 1080p image, returning ("HD", byte_size).
      8. Cleans up broken or 0-byte temporary files if network/disk errors occur and returns ("FAILED", 0).
    """
    date_str, img_name, img_url, title, description, copyright_text = task

    # --- ACCURATE YYYY\MM PATH ROUTING ENGINE ---
    digits_only = re.sub(r'\D', '', str(date_str)) if date_str else ""

    if len(digits_only) >= 6:
        year_str = digits_only[:4]
        month_str = digits_only[4:6]
        date_prefix = digits_only[:8] if len(digits_only) >= 8 else digits_only
    elif len(digits_only) >= 4:
        year_str = digits_only[:4]
        month_str = None
        date_prefix = year_str
    else:
        year_str = "0000"
        month_str = None
        date_prefix = "0000"

    if FLATTEN_OUTPUT:
        target_folder = DOWNLOAD_DIR
        log_path_display = ""
    else:
        if year_str == "0000":
            target_folder = os.path.join(DOWNLOAD_DIR, "0000")
            log_path_display = "0000\\"
        elif month_str:
            target_folder = os.path.join(DOWNLOAD_DIR, year_str, month_str)
            log_path_display = f"{year_str}\\{month_str}\\"
        else:
            target_folder = os.path.join(DOWNLOAD_DIR, year_str)
            log_path_display = f"{year_str}\\"

    os.makedirs(target_folder, exist_ok=True)

    # Resolve UHD target URL
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

    # Resolve HD Fallback URL
    fallback_url = "https://bing.com" + img_url if img_url.startswith("/") else img_url
    if "bing.com" in fallback_url and not fallback_url.startswith("http"):
        fallback_url = "https://" + fallback_url

    # Compute clean target filenames with UHD/HD indicators
    uhd_code = extract_ms_code(target_url, default_quality="UHD")
    uhd_filename = f"{date_prefix}_{img_name} ({uhd_code}).jpg"
    uhd_file_path = os.path.join(target_folder, uhd_filename)

    hd_code = extract_ms_code(fallback_url, default_quality="HD")
    hd_filename = f"{date_prefix}_{img_name} ({hd_code}).jpg"
    hd_file_path = os.path.join(target_folder, hd_filename)

    # Legacy file format check to prevent duplicates
    legacy_filename = f"{date_prefix}_{img_name}.jpg"
    legacy_file_path = os.path.join(target_folder, legacy_filename)

    # Skip download if target file already exists in any valid naming scheme
    if (os.path.exists(uhd_file_path) and os.path.getsize(uhd_file_path) > 0) or \
       (os.path.exists(hd_file_path) and os.path.getsize(hd_file_path) > 0) or \
       (os.path.exists(legacy_file_path) and os.path.getsize(legacy_file_path) > 0):
        return ("SKIPPED", 0)

    time.sleep(0.1)

    try:
        # Attempt 1: 4K UHD Download
        img_res = requests.get(target_url, headers=headers, timeout=15, stream=True)
        if img_res.status_code == 200:
            with open(uhd_file_path, 'wb') as f:
                for chunk in img_res.iter_content(chunk_size=65536):
                    f.write(chunk)

            try:
                file_size = os.path.getsize(uhd_file_path)
                if file_size > 0:
                    with Image.open(uhd_file_path) as img:
                        img.verify()

                    inject_metadata_iptc(uhd_file_path, title, description, copyright_text)
                    return ("UHD", file_size)
            except Exception:
                if os.path.exists(uhd_file_path):
                    os.remove(uhd_file_path)

        # Attempt 2: 1080p HD Fallback Download
        fb_res = requests.get(fallback_url, headers=headers, timeout=15, stream=True)
        if fb_res.status_code == 200:
            with open(hd_file_path, 'wb') as f:
                for chunk in fb_res.iter_content(chunk_size=65536):
                    f.write(chunk)

            try:
                file_size = os.path.getsize(hd_file_path)
                if file_size > 0:
                    with Image.open(hd_file_path) as img:
                        img.verify()

                    inject_metadata_iptc(hd_file_path, title, description, copyright_text)
                    return ("HD", file_size)
            except Exception:
                if os.path.exists(hd_file_path):
                    os.remove(hd_file_path)

    except Exception:
        if os.path.exists(uhd_file_path):
            os.remove(uhd_file_path)
        if os.path.exists(hd_file_path):
            os.remove(hd_file_path)

    return ("FAILED", 0)


def main():
    """
    SENIOR DEV (WHY):
      Main orchestrator loop. Displays ASCII banner, syncs central DB manifest, loads JSON into memory,
      and performs cross-region deduplication using extracted base keys in RAM.
      Prioritizes descriptive English titles (US/UK regions) over generic fallbacks.
      Instantiates PipelineMonitor to render live terminal execution progress statistics frame-by-frame 
      during sequential single-threaded asset processing.

    JUNIOR DEV (HOW):
      1. Displays ASCII header banner.
      2. Calls `sync_central_database()` to update JSON if needed.
      3. Reads local JSON database and counts total raw schema entries.
      4. Iterates over all 11 regional keys in JSON ('US-en', 'GB-en', etc.).
      5. Builds unique wallpaper entries dictionary `unique_wallpapers`.
      6. Deduplicates: replaces generic image names if a better localized title is found.
      7. Sorts task queue chronologically by date in descending order (newest first).
      8. Initializes `PipelineMonitor(total_tasks)` and sequentially calls `download_single_wallpaper(task)` 
         updating the monitor after every single image item.
      9. Catches Ctrl+C (KeyboardInterrupt) to stop execution cleanly.
    """
    print_ascii_banner()
    print("[*] Initialising Bing Wallpaper Synchroniser (Schema Engine)\n")

    sync_central_database()
    print("-" * 60)

    print(f"[*] Reading local JSON database: {LOCAL_JSON_PATH}")
    if not os.path.exists(LOCAL_JSON_PATH):
        print(f"[!] CRITICAL ERROR: all.json.latest is missing!")
        return

    db = load_local_json(LOCAL_JSON_PATH)
    if not db:
        print(f"[!] CRITICAL ERROR: Could not parse all.json.latest!")
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

            base_key = None
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

            if not img_name or img_name.lower() in ["bingimage", "wallpaper", "image"] or img_name.startswith("date_"):
                if title and title.strip():
                    img_name = clean_title(title)
                elif caption and caption.strip() and caption.lower() != "info":
                    img_name = clean_title(caption)

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
    print(f"[+] Cross-date Latin-preferred deduplication complete: {total_tasks} unique download tasks queued.\n")

    monitor = PipelineMonitor(total_tasks)

    try:
        for task in download_queue:
            status_type, bytes_count = download_single_wallpaper(task)
            monitor.record_result(status_type, bytes_count)
    except KeyboardInterrupt:
        print("\n[!] Operation cancelled by user. Exiting gracefully...")
        sys.exit(0)

    print(f"\n\n[ ] Outstanding! Archiving process complete 🎉\nin:\n{DOWNLOAD_DIR}")


if __name__ == "__main__":
    main()
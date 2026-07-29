# 🖼️ Bing Scraper, Npanuhin Edition. A Bing Wallpapers Archive Pipeline

A robust, cross-region deduplicating downloader pipeline for the global **Bing Image of the Day** archive. Available in both **Single-Threaded (Sequential)** and **Multi-Threaded (Concurrent)** editions.

This pipeline syncs manifests across 11 worldwide regional endpoints, performs in-memory deduplication, enforces Ultra HD (4K) image quality, verifies binary payload integrity, and hard-injects Windows Shell-compatible EXIF/IPTC metadata into every asset.

---

## 📸 Key Features

* **🌍 Worldwide Cross-Region Deduplication:** Evaluates regional Bing markets (`US`, `UK`, `DE`, `FR`, `JA`, `AU`, `CN`, `CA`, `IN`, `BR`, `ROW`) in RAM to ensure duplicate global images are downloaded exactly once.
* **⚡ Dual Execution Engines:**
  * **Multi-Threaded Engine:** Uses `ThreadPoolExecutor` TCP multiplexing for speed (5x–15x throughput gains).
  * **Single-Threaded Engine:** Strict sequential ingestion for connection stability on low-bandwidth networks or strict firewalls.
* **⏱️ Smart 5-Hour Manifest Caching:** Checks local modification time of `all.json.latest` before fetching. Bypasses redundant network bandwidth if the cached manifest is younger than 5 hours.
* **🎯 Unicode & CJK Script Preservation:** Prevents descriptive international filenames (Chinese, Japanese, Korean, German, etc.) from being overwritten with generic fallback strings.
* **✨ Automatic 4K Ultra HD Upgrading:** Dynamically rewrites standard high-definition asset URLs to target Ultra HD (`_UHD.jpg`) streams on Bing's CDNs.
* **🏷️ Windows Explorer Metadata Injection:** Directly writes native `EXIF/IPTC` metadata tags using UTF-16LE Byte Order Mark (BOM) encoding. Windows Explorer reads image titles, descriptions, and copyrights natively in File Explorer properties.
* **🔄 Flexible Directory Architecture:** Supports both structured `_OUT\YYYY\MM\filename.jpg` output and flat `_OUT\filename.jpg` storage via a simple global toggle.
* **🖼️ Background Switcher Ready:** Optimized for seamless integration with desktop wallpaper rotation software, such as *John's Background Switcher*.

---

## 🏎️ Pipeline Comparison: Single-Threaded vs. Multi-Threaded

| Feature / Dimension | Single-Threaded Edition | Multi-Threaded Edition |
| --- | --- | --- |
| **Execution Vector** | Sequential (1 asset at a time) | Concurrent (`ThreadPoolExecutor`) |
| **Speed / Throughput** | Standard Network Throughput | ~max. 6x Speedup |
| **Default Concurrency** | `1 worker` | `6 workers` (Hard Limit: Max 6) |
| **Manifest Caching** | Skip download if file < 5 hrs old | Skip download if file < 5 hrs old |
| **Graceful Shutdown** | Signal intercept + zero-byte cleanup | Signal intercept + `executor.shutdown()` |
| **Best Used For** | Metered links, strict VPNs/proxies | Bulk archiving, high-speed initial runs |

---

## 🏁 Quick Start (For Beginners)

### 1. Requirements

* Windows 10 or Windows 11
* Python 3.8 or higher installed on your system

### 2. Setup & Execution

1. Download or clone this repository to any folder on your computer.
2. Double-click **`run.cmd`** to start downloading.

> **What `run.cmd` does automatically:**
> * Checks your Python installation.
> * Installs missing Python libraries (`requests`, `piexif`, `Pillow`).
> * Smart-checks the local Bing manifest database (`all.json.latest`); refreshes it only if older than 5 hours.
> * Downloads and metadata-enriches all available wallpapers into the `_OUT` directory.

---

## 💻 Manual / Advanced Usage (For Power Users)

If you prefer running the script manually from PowerShell or Command Prompt:

```powershell
# 1. Install required dependencies
pip install requests piexif Pillow

# 2. Run the Multi-Threaded Edition (Fastest)
python '.\2. grab_everything_multithreaded_with_deduplication_and_automatic-npanuhin.me-all.json_download.py'

# 3. OR Run the Single-Threaded Edition (Sequential / Safe Mode)
python '.\1. grab_everything_singlethreaded_with_deduplication_and_automatic-npanuhin.me-all.json_download.py'
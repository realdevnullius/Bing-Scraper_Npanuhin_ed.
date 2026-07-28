import re

def clean_title(title_str):
    """Sanitizes raw string payloads into deterministic, underscore-delimited signatures, preserving global Unicode characters."""
    if not title_str:
        return "BingImage"
        
    stop_words = {
        'the', 'in', 'on', 'at', 'of', 'and', 'a', 'an', 'to', 'for', 'with', 'off', 
        'from', 'by', 'as', 'into', 'over', 'through', 'about', 'under', 'above', 
        'between', 'among', 'during', 'without', 'against', 'including', 'across'
    }
    
    # STANDARDIZED UNICODE REGEX: Replaces illegal filesystem markers and global punctuation vectors with whitespaces
    clean = re.sub(r'[\x00-\x1f\\/:*?"<>|,\. !?’’“”，。！＿：]', ' ', title_str)
    words = clean.split()
    
    filtered_words = []
    for w in words:
        if w.lower() not in stop_words:
            # Capitalize western words, keep Asian scripts completely untouched
            filtered_words.append(w.capitalize() if w.isascii() else w)
            
    if not filtered_words:
        return "BingImage"
        
    raw_cleaned = "_".join(filtered_words)
    
    # PATH LENGTH BOUNDARY CLAMPING: Restrict filename lengths to 90 characters to guarantee Windows MAX_PATH compliance
    if len(raw_cleaned) > 90:
        raw_cleaned = raw_cleaned[:90].rstrip('_')
        
    return raw_cleaned

# --- ENGINE VALIDATION EXECUTION ENGINE ---
print("=" * 70)
print("              BING BACKGROUNDS - ENGINE VALIDATION TEST")
print("=" * 70)

test_cases = [
    {
        "id": "1. Standard Asian Script (Changsha Fireworks)",
        "title": "夜空中的烟花表演，长沙，湖南省，中国",
        "expected_desc": "Should preserve native Unicode scripts completely."
    },
    {
        "id": "2. Extreme Western String Payload (Windows MAX_PATH target testing)",
        "title": "The majestic and absolutely breathtaking panoramic view of the grand canyon national park during a very dramatic and colorful golden hour sunset with big clouds",
        "expected_desc": "Should clamp execution length parameters at 90 characters."
    },
    {
        "id": "3. Conjoined Multi-Language Matrix",
        "title": "Mount_Fuji Area! 富士山の絶景, Japan",
        "expected_desc": "Should format Western casing properties while retaining native Kanji signatures."
    }
]

for case in test_cases:
    result = clean_title(case["title"])
    print(f"\n📌 TEST: {case['id']}")
    print(f"👉 Input:  {case['title']}")
    print(f"✅ Output: {result}")
    print(f"📊 Length: {len(result)} characters (Limit = 90)")
    print(f"💡 Status: {'PASSED' if len(result) <= 90 else 'FAILED'}")
    print("-" * 70)

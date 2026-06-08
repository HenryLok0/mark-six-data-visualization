import json
import os
from playwright.sync_api import sync_playwright

ALL_JSON_PATH = "data/all.json"
STATS_JSON_PATH = "data/stats.json"
HKJC_RESULTS_URL = "https://bet.hkjc.com/ch/marksix/results"
RESULTS_TABLE_SELECTOR = ".maraksx-results-table .table-row"
NAVIGATION_TIMEOUT_MS = 90000

def fetch_hkjc_results():
    data = []
    print("Launching Microsoft Edge virtual browser...")
    with sync_playwright() as p:
        # headless=False can be used in development to see the screen and check for ads blocking it. Setted to True for speed here.
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()
        
        print("Opening HKJC Mark Six results page...")
        # Use domcontentloaded instead of networkidle; HKJC keeps background requests
        # alive and networkidle often never settles on CI runners.
        page.goto(
            HKJC_RESULTS_URL,
            wait_until="domcontentloaded",
            timeout=NAVIGATION_TIMEOUT_MS,
        )

        print("Waiting for results table to render...")
        page.wait_for_selector(RESULTS_TABLE_SELECTOR, timeout=NAVIGATION_TIMEOUT_MS)
        
        print("Extracting latest draw records directly from the web DOM...")
        
        # This is key: getting the lottery results table from the screen via JS
        extracted_data = page.evaluate('''() => {
            const results = [];
            
            // Find the sections containing the results (HKJC's current structure uses .table-row)
            const rows = document.querySelectorAll('.maraksx-results-table .table-row');
            
            rows.forEach(row => {
                const idEl = row.querySelector('.cell-id a');
                const dateEl = row.querySelector('.cell-date');
                const ballImages = row.querySelectorAll('.cell-ball-list img');
                
                if(idEl && dateEl && ballImages.length >= 7) {
                    let drawId = idEl.innerText.trim().replace(' EAS', ''); // e.g. 26/045
                    let drawDate = dateEl.innerText.trim(); // e.g. 25/04/2026
                    
                    // Find the alt attribute in all <img> tags, this is the winning number
                    const numbers = Array.from(ballImages).map(img => img.getAttribute('alt'));
                    
                    // Convert date format to YYYY-MM-DD
                    if (drawDate.includes("/")) {
                        const parts = drawDate.split("/");
                        if(parts.length === 3) {
                            drawDate = `${parts[2]}-${parts[1]}-${parts[0]}`;
                        }
                    }

                    // Take the first 6 regular numbers, the 7th is the special number
                    results.push({
                        id: drawId,
                        date: drawDate,
                        no: numbers.slice(0, 6),
                        sno: numbers[6]
                    });
                }
            });
            return results;
        }''')
        
        if extracted_data:
            data.extend(extracted_data)
        
        browser.close()
    return data

def update_data(new_draws):
    if not new_draws:
        return
        
    all_data = []
    if os.path.exists(ALL_JSON_PATH):
        try:
            with open(ALL_JSON_PATH, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except json.JSONDecodeError:
            all_data = []
            
    existing_ids = {item["id"] for item in all_data if item.get("id")}
    added_count = 0
    
    for draw in new_draws:
        # Check against the full drawing ID formatting in existing data 
        # (old data format: id: "26/045", sometimes id may differ, we check date and id)
        if draw["id"] and draw["id"] not in existing_ids:
            all_data.append(draw)
            added_count += 1
            
    if added_count == 0:
        print("Screen captured successfully, but no 'new' data to update.")
        return
        
    all_data.sort(key=lambda x: x.get("date",""), reverse=True)
    
    with open(ALL_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print(f"✅ Successfully saved {added_count} new draw records to {ALL_JSON_PATH}")

    # ===== Calculate stats =====
    stats_without_sno = {}
    stats_with_sno = {}
    stats_sno_only = {}
    
    for item in all_data:
        if "no" not in item or "sno" not in item:
            continue
        for num in item["no"]:
            num_str = str(int(num))
            stats_without_sno[num_str] = stats_without_sno.get(num_str, 0) + 1
            stats_with_sno[num_str] = stats_with_sno.get(num_str, 0) + 1
            
        sno_str = str(int(item["sno"]))
        stats_with_sno[sno_str] = stats_with_sno.get(sno_str, 0) + 1
        stats_sno_only[sno_str] = stats_sno_only.get(sno_str, 0) + 1
        
    stats_data = {
        "total": len(all_data),
        "stats_without_sno": stats_without_sno,
        "stats_with_sno": stats_with_sno,
        "stats_sno_only": stats_sno_only
    }
    
    with open(STATS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(stats_data, f, ensure_ascii=False, indent=2)
    print(f"✅ Successfully updated statistics in {STATS_JSON_PATH}")

if __name__ == "__main__":
    results = fetch_hkjc_results()
    if results:
        update_data(results)
    else:
        print("No data extracted from screen, the website layout might have changed.")
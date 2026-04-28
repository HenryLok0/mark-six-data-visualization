import json
import os
import time
from playwright.sync_api import sync_playwright

ALL_JSON_PATH = "data/all.json"
STATS_JSON_PATH = "data/stats.json"

def fetch_hkjc_results():
    data = []
    print("正在啟動微軟 Edge 虛擬瀏覽器...")
    with sync_playwright() as p:
        # headless=False 可以在開發時看到畫面，確認它是否被廣告擋住。這邊為了速度先設為 True
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()
        
        print("正在開啟香港賽馬會六合彩頁面...")
        page.goto("https://bet.hkjc.com/ch/marksix/results", wait_until="networkidle", timeout=60000)
        
        print("等待網頁 Javascript 渲染完成...")
        time.sleep(5)
        
        print("直接從網頁 DOM 提取最新開獎紀錄...")
        
        # 這裡是關鍵：透過 JS 把畫面上的開獎結果表格扒下來
        extracted_data = page.evaluate('''() => {
            const results = [];
            
            // 找出包含結果的區塊 (賽馬會目前的結構使用 .table-row)
            const rows = document.querySelectorAll('.maraksx-results-table .table-row');
            
            rows.forEach(row => {
                const idEl = row.querySelector('.cell-id a');
                const dateEl = row.querySelector('.cell-date');
                const ballImages = row.querySelectorAll('.cell-ball-list img');
                
                if(idEl && dateEl && ballImages.length >= 7) {
                    let drawId = idEl.innerText.trim().replace(' EAS', ''); // e.g. 26/045
                    let drawDate = dateEl.innerText.trim(); // e.g. 25/04/2026
                    
                    // 找出所有 <img> 標籤裡面的 alt 屬性，這就是開獎數字
                    const numbers = Array.from(ballImages).map(img => img.getAttribute('alt'));
                    
                    // 轉換日期格式變成 YYYY-MM-DD
                    if (drawDate.includes("/")) {
                        const parts = drawDate.split("/");
                        if(parts.length === 3) {
                            drawDate = `${parts[2]}-${parts[1]}-${parts[0]}`;
                        }
                    }

                    // 取前 6 個常規號，第 7 個是特別號
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
        print("成功擷取畫面，但是沒有任何「新」資料需要更新。")
        return
        
    all_data.sort(key=lambda x: x.get("date",""), reverse=True)
    
    with open(ALL_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)
    print(f"✅ 成功將 {added_count} 筆新開獎紀錄存入 {ALL_JSON_PATH}")

    # ===== 計算 stats =====
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
    print(f"✅ 成功更新統計資料 {STATS_JSON_PATH}")

if __name__ == "__main__":
    results = fetch_hkjc_results()
    if results:
        update_data(results)
    else:
        print("未擷取到畫面資料，可能是網頁改版找不到表格與球標籤(.ball)。")
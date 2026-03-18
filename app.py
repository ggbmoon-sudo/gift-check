import streamlit as st
import pandas as pd
import requests
import base64
import uuid
import json
from io import BytesIO
from PIL import Image

# =========================================
# ⚙️ 系統設定與 API
# =========================================
# ⚠️ 請替換為你真實的 Google Apps Script 網址
GAS_URL = "https://script.google.com/macros/s/AKfycbw9zjR7-DOHCzBhHbDM9QhG22nWpozbU2ENjUayX8Y-AdLVXhddIKm-ea8sI3ToLLXs/exec"

st.set_page_config(page_title="禮品盤點 Pro", page_icon="📦", layout="wide")

# =========================================
# 🛡️ 安全數字轉換器
# =========================================
def safe_float(v):
    try:
        v = float(v)
        return 0.0 if pd.isna(v) else v
    except:
        return 0.0

def safe_int(v):
    try:
        v = float(v)
        return 0 if pd.isna(v) else int(v)
    except:
        return 0

# =========================================
# 🔄 雲端同步與輔助引擎
# =========================================
def load_data():
    try:
        res = requests.get(GAS_URL)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list):
                return data
    except Exception as e:
        st.error(f"下載資料失敗: {e}")
    return []

def auto_save():
    try:
        payload = {"action": "save_data", "data": st.session_state.inventory}
        headers = {'Content-Type': 'application/json'}
        res = requests.post(GAS_URL, json=payload, headers=headers)
        if res.status_code == 200 and res.json().get("status") == "success":
            st.toast("☁️ 雲端已自動同步！", icon="✅")
        else:
            st.error("❌ 雲端同步失敗，請檢查網路。")
    except Exception as e:
        st.error(f"自動同步發生錯誤: {e}")

def generate_short_code():
    chars = '23456789ABCDFGHJKLMNPQRSTUVWXYZ'
    import random
    while True:
        code = ''.join(random.choice(chars) for _ in range(4))
        if not any(item.get('shortCode') == code for item in st.session_state.inventory):
            return code

def process_image_to_b64(uploaded_file, max_width=300):
    if uploaded_file is None:
        return ""
    img = Image.open(uploaded_file)
    if img.width > max_width:
        ratio = max_width / float(img.width)
        height = int((float(img.height) * float(ratio)))
        img = img.resize((max_width, height), Image.Resampling.LANCZOS)
    buffered = BytesIO()
    img.save(buffered, format="JPEG", quality=60)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def upload_image_to_drive(base64_img, filename):
    payload = {"action": "upload_image", "base64Data": base64_img, "fileName": filename}
    headers = {'Content-Type': 'application/json'}
    try:
        res = requests.post(GAS_URL, json=payload, headers=headers)
        if res.status_code == 200 and res.json().get("status") == "success":
            return res.json().get("imageUrl")
    except:
        pass
    return ""

def call_gemini_api(prompt, base64_img, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": base64_img}}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    res = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
    if res.status_code == 200:
        return json.loads(res.json()['candidates'][0]['content']['parts'][0]['text'])
    else:
        raise Exception(f"AI 呼叫失敗: {res.text}")

# 初始載入
if 'inventory' not in st.session_state:
    with st.spinner("🔄 正在連線至雲端資料庫..."):
        st.session_state.inventory = load_data()

# =========================================
# 🛡️ 左側邊欄：系統維護與 AI 金鑰
# =========================================
with st.sidebar:
    st.header("✨ AI 視覺引擎設定")
    # 讓使用者在側邊欄輸入 API Key，保護隱私
    gemini_key = st.text_input("輸入 Gemini API Key", type="password", help="用於啟動照片辨識功能")
    if gemini_key:
        st.success("✅ AI 引擎已解鎖")
    else:
        st.warning("請輸入 API Key 以啟用 AI 功能")
        
    st.divider()
    st.header("🛠️ 系統還原")
    uploaded_file = st.file_uploader("上傳盤點報告 (CSV)", type="csv")
    if uploaded_file and st.button("🚨 確認還原 (將覆蓋現有資料)", type="primary"):
        try:
            df_backup = pd.read_csv(uploaded_file, skiprows=2)
            restored_data = []
            for _, row in df_backup.iterrows():
                raw_sku = str(row.get('SKU', 'N/A'))
                clean_sku = raw_sku[2:-1] if raw_sku.startswith('="') and raw_sku.endswith('"') else raw_sku
                restored_data.append({
                    "shortCode": str(row.get('四碼代號', generate_short_code())),
                    "area": str(row.get('區域', '未指定')),
                    "category": str(row.get('分類', '未分類')),
                    "sku": clean_sku,
                    "name": str(row.get('產品名稱', '未知產品')),
                    "unit": str(row.get('單位', '件')),
                    "price": safe_float(row.get('單價', 0)),
                    "bookQty": 0,
                    "actualQty": safe_int(row.get('實盤數量', 0)),
                    "image": "", 
                    "isPrinted": False
                })
            st.session_state.inventory = restored_data
            auto_save() 
            st.success(f"✅ 成功還原 {len(restored_data)} 筆資料！")
        except Exception as e:
            st.error(f"還原失敗: {e}")

# =========================================
# 🖥️ 頂部儀表板
# =========================================
st.title("🏢 禮品盤點系統 Pro v5.0")
total_items = len(st.session_state.inventory)
total_value = sum(safe_float(item.get('price', 0)) * safe_int(item.get('actualQty', 0)) for item in st.session_state.inventory)

col1, col2, col3 = st.columns(3)
col1.metric("📦 庫存品項總數", total_items)
col2.metric("💰 資產總值", f"${total_value:,.2f}")
if col3.button("🔄 強制重新載入雲端資料"):
    st.session_state.inventory = load_data()
    st.rerun()

st.divider()

# 主要分頁
tab1, tab2, tab3, tab4, tab5 = st.tabs(["🔍 快速盤點", "➕ 新增建檔", "📊 庫存總表", "🖨️ 列印封條", "✨ AI 助手"])

# ... (Tab 1 到 Tab 4 與上次提供的程式碼相同，為了節省版面，請保留你原本的 tab1 ~ tab4，或參考上一則對話) ...
# ⚠️ 這裡我直接放 Tab 5 (AI 助手) 和 Tab 3 的更新，你可以把它貼到檔案最下面

with tab5:
    st.subheader("🤖 拍照並讓 AI 自動處理")
    if not gemini_key:
        st.info("👈 請先在左側選單輸入您的 Gemini API Key。")
    else:
        ai_photo = st.camera_input("📸 拍下產品或包裝")
        
        if ai_photo:
            ai_b64 = process_image_to_b64(ai_photo, max_width=600)
            
            col_ai1, col_ai2 = st.columns(2)
            # --- AI 功能 1：找舊貨 +1 ---
            if col_ai1.button("🔍 找舊貨 +1", use_container_width=True):
                with st.spinner("AI 正在比對庫存特徵..."):
                    inv_summary = [f"SKU: {i.get('sku')} | 名稱: {i.get('name')}" for i in st.session_state.inventory]
                    prompt = f"""你是一個專業香港盤點助手。從下方清單找出照片中最符合的產品。
                    【庫存清單】\n{json.dumps(inv_summary)}
                    以嚴格 JSON 回覆：{{"sku": "最匹配SKU或 NEW", "name": "產品名稱", "confidence": "數字0-100", "reason": "簡單說明"}}"""
                    
                    try:
                        ai_result = call_gemini_api(prompt, ai_b64, gemini_key)
                        st.json(ai_result)
                        if ai_result.get("sku") != "NEW" and float(ai_result.get("confidence", 0)) > 50:
                            # 找出對應商品並 +1
                            for item in st.session_state.inventory:
                                if item.get("sku") == ai_result.get("sku"):
                                    item["actualQty"] = safe_int(item.get("actualQty", 0)) + 1
                                    item["isPrinted"] = False
                                    auto_save()
                                    st.success(f"🎉 辨識成功！【{item['name']}】數量已自動 +1！")
                                    break
                        else:
                            st.warning("🤖 找不到相似度高的舊貨，請使用「智能建檔」。")
                    except Exception as e:
                        st.error(e)

            # --- AI 功能 2：智能建檔 ---
            if col_ai2.button("📝 智能建檔 (自動加入總表)", type="primary", use_container_width=True):
                with st.spinner("AI 正在解析包裝資訊與市場行情..."):
                    prompt = """你是一個香港建檔助手。請觀察照片並自動填表。
                    估算單價(HKD)。以嚴格 JSON 回覆：
                    {"name": "詳細名稱", "category": "最接近類別", "unit": "件/箱/樽/套", "sku": "條碼數字或空", "price": 數字或0}
                    類別限選：HAMPER類(cheap餅), HAMPER類(朱古力,餅乾), BB野, 籃, ESG, 酒, 果汁, 永生花, 其他。"""
                    try:
                        ai_result = call_gemini_api(prompt, ai_b64, gemini_key)
                        
                        # 上傳圖片到 Google Drive
                        img_url = upload_image_to_drive(ai_b64, f"AI_Auto_{uuid.uuid4().hex[:6]}.jpg")
                        
                        # 建立新資料
                        new_item = {
                            "shortCode": generate_short_code(),
                            "area": "未指定",
                            "category": ai_result.get("category", "其他"),
                            "sku": ai_result.get("sku", "N/A"),
                            "name": ai_result.get("name", "AI 辨識商品"),
                            "unit": ai_result.get("unit", "件"),
                            "price": safe_float(ai_result.get("price", 0)),
                            "bookQty": 0,
                            "actualQty": 0, # 新建檔預設數量 0，等待盤點
                            "image": img_url,
                            "isPrinted": False
                        }
                        st.session_state.inventory.append(new_item)
                        auto_save()
                        st.success(f"✅ AI 建檔完成！已新增：{new_item['name']}。請至「庫存總表」查看！")
                        st.json(ai_result)
                    except Exception as e:
                        st.error(e)
                        
# ⚠️ 請確保 Tab 1 ~ Tab 4 的程式碼也有貼上！

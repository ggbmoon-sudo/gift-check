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
# 🔑 讀取 Streamlit 隱藏金鑰 (Secrets)
# =========================================
# 系統會自動去 Streamlit Cloud 的 Secrets 設定裡尋找金鑰
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = "" # 如果找不到，就預設為空

# =========================================
# 🛡️ 安全轉換與防呆器
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
# 🔄 雲端同步引擎
# =========================================
def load_data():
    try:
        res = requests.get(GAS_URL)
        if res.status_code == 200:
            try:
                data = res.json()
                if isinstance(data, list):
                    return data
            except ValueError:
                # 如果 Google 回傳的是登入網頁(HTML)，就會觸發這個錯誤
                st.error("❌ 無法讀取雲端資料！請確保 Google Apps Script 的「誰可以存取」已設為「所有人 (Anyone)」。")
                return []
    except Exception as e:
        st.error(f"下載資料連線失敗: {e}")
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

# 初始載入資料
if 'inventory' not in st.session_state:
    with st.spinner("🔄 正在連線至雲端資料庫..."):
        st.session_state.inventory = load_data()

# =========================================
# 🛡️ 左側邊欄：系統維護
# =========================================
with st.sidebar:
    st.header("✨ AI 視覺引擎")
    if API_KEY:
        st.success("✅ 金鑰已從系統背景安全載入")
    else:
        st.error("⚠️ 尚未設定 GEMINI_API_KEY。請至 Streamlit Cloud 的 Secrets 中設定。")
        
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
            st.rerun()
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

# -----------------------------------------
# 分頁 1：快速盤點
# -----------------------------------------
with tab1:
    st.subheader("🔍 搜尋與快速調整")
    search_query = st.text_input("輸入名稱、SKU 或四碼代號搜尋...", "")
    
    if search_query:
        filtered_indices = [
            i for i, item in enumerate(st.session_state.inventory)
            if search_query.lower() in str(item.values()).lower()
        ]
        if not filtered_indices:
            st.warning("找不到符合的商品。")
        for idx in filtered_indices:
            item = st.session_state.inventory[idx]
            with st.container(border=True):
                c1, c2, c3 = st.columns([1, 3, 2])
                with c1:
                    if item.get('image'):
                        st.image(item['image'], width=80)
                    else:
                        st.info("無圖片")
                with c2:
                    st.markdown(f"**{item.get('name')}**")
                    st.caption(f"代碼: `{item.get('shortCode')}` | 區域: {item.get('area')} | SKU: {item.get('sku')}")
                    st.markdown(f"單價: **${item.get('price')}** / {item.get('unit')}")
                with c3:
                    st.metric("實盤數量", item.get('actualQty', 0))
                    bc1, bc2 = st.columns(2)
                    if bc1.button("➖ 減 1", key=f"minus_{idx}", use_container_width=True):
                        if int(item.get('actualQty', 0)) > 0:
                            st.session_state.inventory[idx]['actualQty'] = int(item.get('actualQty', 0)) - 1
                            st.session_state.inventory[idx]['isPrinted'] = False
                            auto_save()
                            st.rerun()
                    if bc2.button("➕ 加 1", key=f"plus_{idx}", type="primary", use_container_width=True):
                        st.session_state.inventory[idx]['actualQty'] = int(item.get('actualQty', 0)) + 1
                        st.session_state.inventory[idx]['isPrinted'] = False
                        auto_save()
                        st.rerun()

# -----------------------------------------
# 分頁 2：新增建檔
# -----------------------------------------
with tab2:
    st.subheader("➕ 新增商品")
    photo = st.camera_input("📸 拍攝產品照片 (可選)")
    b64_image = process_image_to_b64(photo) if photo else ""
    
    with st.form("add_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_sku = st.text_input("SKU 編號", placeholder="掃描槍輸入或留空")
            new_area = st.text_input("區域", placeholder="例: A-01")
            new_name = st.text_input("產品名稱 (必填)*")
        with col2:
            new_cat = st.selectbox("分類", ["HAMPER類(cheap餅)", "HAMPER類(朱古力,餅乾)", "BB野", "籃", "ESG", "酒", "果汁", "永生花", "其他"])
            new_unit = st.selectbox("單位", ["件", "箱", "樽", "套", "其他"])
            new_price = st.number_input("單價 ($) 💡非必填", value=0.0, step=1.0)
            new_qty = st.number_input("初始實盤數量", min_value=0, value=0, step=1)
            
        submit_add = st.form_submit_button("💾 儲存並全自動上傳", type="primary")
        
        if submit_add:
            if not new_name:
                st.error("⚠️ 產品名稱為必填項目！")
            else:
                img_url = ""
                if b64_image:
                    with st.spinner("上傳照片中..."):
                        img_url = upload_image_to_drive(b64_image, f"Item_{uuid.uuid4().hex[:6]}.jpg")
                
                new_item = {
                    "shortCode": generate_short_code(),
                    "area": new_area,
                    "category": new_cat,
                    "sku": new_sku or "N/A",
                    "name": new_name,
                    "unit": new_unit,
                    "price": float(new_price),
                    "bookQty": 0,
                    "actualQty": int(new_qty),
                    "image": img_url,
                    "isPrinted": False
                }
                st.session_state.inventory.append(new_item)
                auto_save()
                st.success(f"✅ {new_name} 新增成功！")

# -----------------------------------------
# 分頁 3：庫存總表 (動態防護更新)
# -----------------------------------------
with tab3:
    st.subheader("📋 庫存總表 (可直接點擊表格修改)")
    if st.session_state.inventory:
        df = pd.DataFrame(st.session_state.inventory)
        
        # 🌟 強制補齊缺漏欄位 (防呆：避免舊版 CSV 導致報錯)
        display_cols = ['shortCode', 'area', 'name', 'sku', 'category', 'price', 'actualQty', 'unit', 'isPrinted']
        for col in display_cols:
            if col not in df.columns:
                df[col] = False if col == 'isPrinted' else (0 if col in ['price', 'actualQty'] else "")
                
        edited_df = st.data_editor(
            df[display_cols],
            column_config={
                "shortCode": st.column_config.TextColumn("四碼", disabled=True),
                "area": "區域",
                "name": "產品名稱",
                "sku": "SKU",
                "category": "分類",
                "price": st.column_config.NumberColumn("單價", format="$ %.2f"),
                "actualQty": st.column_config.NumberColumn("數量", min_value=0, step=1),
                "isPrinted": st.column_config.CheckboxColumn("已印封條")
            },
            hide_index=True,
            use_container_width=True,
            num_rows="dynamic"
        )
        
        if not df[display_cols].equals(edited_df):
            updated_inventory = []
            for i, row in edited_df.iterrows():
                original_item = st.session_state.inventory[i] if i < len(st.session_state.inventory) else {}
                merged_item = {**original_item, **row.to_dict()}
                updated_inventory.append(merged_item)
                
            st.session_state.inventory = updated_inventory
            auto_save()
            st.success("✅ 修改已自動同步至雲端！")
            
        csv = edited_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(label="📊 匯出 Excel (CSV) 報表", data=csv, file_name='盤點總表.csv', mime='text/csv')
    else:
        st.info("目前無資料。")

# -----------------------------------------
# 分頁 4：列印封條
# -----------------------------------------
with tab4:
    st.subheader("🖨️ 封條列印中心")
    unprinted_items = [item for item in st.session_state.inventory if not item.get('isPrinted')]
    st.metric("尚有未印封條數量", len(unprinted_items))
    
    if unprinted_items:
        if st.button("🖨️ 產生批次列印畫面 (80mm)", type="primary"):
            html_content = """
            <html><head><style>
                @media print { body { margin: 0; padding: 0; } }
                .seal { page-break-after: always; width: 300px; padding: 10px; font-family: sans-serif; border-bottom: 1px dashed #ccc; margin-bottom: 20px;}
                .header { text-align: center; font-weight: bold; border-bottom: 2px solid black; padding-bottom: 5px; margin-bottom: 10px;}
                .code { font-size: 32px; font-weight: 900; text-align: center; letter-spacing: 5px; border: 2px solid black; padding: 5px; margin: 10px 0;}
                .qty { font-size: 28px; font-weight: bold; text-align: center; margin: 10px 0;}
                .warn { font-size: 12px; text-align: center; border-top: 1px dashed black; padding-top: 5px;}
            </style></head><body onload="window.print()">
            """
            for item in unprinted_items:
                html_content += f"""
                <div class='seal'>
                    <div class='header'>✅ INVENTORY COMPLETED</div>
                    <div style='display:flex; justify-content:space-between; font-size:12px;'>
                        <span>區域: {item.get('area', 'N/A')}</span><span>2026年3月</span>
                    </div>
                    <div class='code'>{item.get('shortCode')}</div>
                    <div style='text-align:center; font-weight:bold;'>{item.get('name')}</div>
                    <div class='qty'>{item.get('actualQty')} <span style='font-size:14px;'>{item.get('unit')}</span></div>
                    <div class='warn'>⚠️ 封條損毀即屬無效</div>
                </div>
                """
            html_content += "</body></html>"
            st.components.v1.html(html_content, height=600, scrolling=True)
            for item in st.session_state.inventory:
                if not item.get('isPrinted'):
                    item['isPrinted'] = True
            auto_save()
            st.success("✅ 列印指令已送出，資料狀態已更新！")
    else:
        st.success("🎉 所有封條都已經列印完畢。")

# -----------------------------------------
# 分頁 5：AI 助手
# -----------------------------------------
with tab5:
    st.subheader("🤖 拍照並讓 AI 自動處理")
    if not API_KEY:
        st.info("👈 您的系統尚未設定 Gemini API Key，請至後台 Secrets 設定。")
    else:
        ai_photo = st.camera_input("📸 拍下產品或包裝")
        if ai_photo:
            ai_b64 = process_image_to_b64(ai_photo, max_width=600)
            col_ai1, col_ai2 = st.columns(2)
            
            if col_ai1.button("🔍 找舊貨 +1", use_container_width=True):
                with st.spinner("AI 正在比對庫存特徵..."):
                    inv_summary = [f"SKU: {i.get('sku')} | 名稱: {i.get('name')}" for i in st.session_state.inventory]
                    prompt = f"""你是一個專業香港盤點助手。從下方清單找出照片中最符合的產品。
                    【庫存清單】\n{json.dumps(inv_summary)}
                    以嚴格 JSON 回覆：{{"sku": "最匹配SKU或 NEW", "name": "產品名稱", "confidence": "數字0-100", "reason": "簡單說明"}}"""
                    try:
                        ai_result = call_gemini_api(prompt, ai_b64, API_KEY)
                        st.json(ai_result)
                        if ai_result.get("sku") != "NEW" and float(ai_result.get("confidence", 0)) > 50:
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

            if col_ai2.button("📝 智能建檔", type="primary", use_container_width=True):
                with st.spinner("AI 正在解析包裝資訊與市場行情..."):
                    prompt = """你是一個香港建檔助手。請觀察照片並自動填表。
                    估算單價(HKD)。以嚴格 JSON 回覆：
                    {"name": "詳細名稱", "category": "最接近類別", "unit": "件/箱/樽/套", "sku": "條碼數字或空", "price": 數字或0}
                    類別限選：HAMPER類(cheap餅), HAMPER類(朱古力,餅乾), BB野, 籃, ESG, 酒, 果汁, 永生花, 其他。"""
                    try:
                        ai_result = call_gemini_api(prompt, ai_b64, API_KEY)
                        img_url = upload_image_to_drive(ai_b64, f"AI_Auto_{uuid.uuid4().hex[:6]}.jpg")
                        new_item = {
                            "shortCode": generate_short_code(),
                            "area": "未指定",
                            "category": ai_result.get("category", "其他"),
                            "sku": ai_result.get("sku", "N/A"),
                            "name": ai_result.get("name", "AI 辨識商品"),
                            "unit": ai_result.get("unit", "件"),
                            "price": safe_float(ai_result.get("price", 0)),
                            "bookQty": 0,
                            "actualQty": 0,
                            "image": img_url,
                            "isPrinted": False
                        }
                        st.session_state.inventory.append(new_item)
                        auto_save()
                        st.success(f"✅ AI 建檔完成！已新增：{new_item['name']}。請至「庫存總表」查看！")
                        st.json(ai_result)
                    except Exception as e:
                        st.error(e)

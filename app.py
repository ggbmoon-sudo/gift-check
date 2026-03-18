import streamlit as st
import pandas as pd
import requests
import base64
import uuid
import json
from io import BytesIO
from PIL import Image

# 嘗試載入條碼辨識庫
try:
    from pyzbar.pyzbar import decode
except ImportError:
    decode = None

# =========================================
# ⚙️ 系統設定與 API
# =========================================
GAS_URL = "https://script.google.com/macros/s/AKfycbw9zjR7-DOHCzBhHbDM9QhG22nWpozbU2ENjUayX8Y-AdLVXhddIKm-ea8sI3ToLLXs/exec"

st.set_page_config(page_title="禮品盤點 Pro", page_icon="📦", layout="wide", initial_sidebar_state="collapsed")

# =========================================
# 🎨 頂級 UI/UX CSS 注入 (專為 iPhone 16 Pro 與電腦版優化)
# =========================================
st.markdown("""
<style>
    /* 引入蘋果風格字體 */
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Noto Sans TC", sans-serif;
    }
    
    /* 隱藏預設的 Streamlit 頂部和底部標記，營造 App 感 */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* 美化數據看板 (Metrics) */
    div[data-testid="stMetricValue"] {
        color: #007AFF; /* iOS 經典藍 */
        font-weight: 800;
        font-size: 2.2rem;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 1rem;
        color: #8E8E93;
        font-weight: 600;
    }
    
    /* 按鈕圓角與陰影優化 */
    .stButton>button {
        border-radius: 14px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    .stButton>button:active {
        transform: scale(0.97);
    }
    
    /* 主要按鈕使用 iOS 綠色或藍色漸層 */
    button[kind="primary"] {
        background: linear-gradient(135deg, #007AFF, #0056b3);
        border: none;
    }
    
    /* 卡片與擴展區塊美化 */
    div[data-testid="stExpander"] {
        background-color: #FFFFFF;
        border-radius: 16px;
        border: 1px solid #E5E5EA;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    
    /* 標籤頁 (Tabs) 現代化 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px 10px 0 0;
        padding: 10px 16px;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #F2F2F7;
        color: #1C1C1E;
    }
</style>
""", unsafe_allow_html=True)

# =========================================
# 🔑 讀取隱藏金鑰
# =========================================
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
except:
    API_KEY = ""

# =========================================
# 🛡️ 輔助與同步引擎
# =========================================
def safe_float(v):
    try: return 0.0 if pd.isna(float(v)) else float(v)
    except: return 0.0

def safe_int(v):
    try: return 0 if pd.isna(float(v)) else int(float(v))
    except: return 0

def load_data():
    try:
        res = requests.get(GAS_URL)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list): return data
    except Exception as e:
        st.error("連線異常，無法讀取資料庫。")
    return []

def auto_save():
    try:
        payload = {"action": "save_data", "data": st.session_state.inventory}
        res = requests.post(GAS_URL, json=payload, headers={'Content-Type': 'application/json'})
        if res.status_code == 200:
            st.toast("☁️ 雲端已自動同步", icon="✅")
    except:
        st.toast("⚠️ 自動同步失敗，將於下次操作重試", icon="⚠️")

def generate_short_code():
    import random
    chars = '23456789ABCDFGHJKLMNPQRSTUVWXYZ'
    while True:
        code = ''.join(random.choice(chars) for _ in range(4))
        if not any(item.get('shortCode') == code for item in st.session_state.inventory):
            return code

def process_image_to_b64(uploaded_file, max_width=300):
    if not uploaded_file: return ""
    img = Image.open(uploaded_file)
    if img.width > max_width:
        ratio = max_width / float(img.width)
        img = img.resize((max_width, int(float(img.height) * ratio)), Image.Resampling.LANCZOS)
    buffered = BytesIO()
    img.save(buffered, format="JPEG", quality=60)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def upload_image_to_drive(base64_img, filename):
    if not base64_img: return ""
    payload = {"action": "upload_image", "base64Data": base64_img, "fileName": filename}
    try:
        res = requests.post(GAS_URL, json=payload, headers={'Content-Type': 'application/json'})
        if res.status_code == 200: return res.json().get("imageUrl", "")
    except: pass
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
        raise Exception(f"AI 回應錯誤: {res.text}")

# 初始化狀態
if 'inventory' not in st.session_state:
    st.session_state.inventory = load_data()
if 'scanned_sku' not in st.session_state:
    st.session_state.scanned_sku = ""
if 'pending_ai_item' not in st.session_state:
    st.session_state.pending_ai_item = None

# =========================================
# 🛡️ 左側邊欄：進階設定 (將不常用的放到底部)
# =========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/679/679821.png", width=60)
    st.header("系統設定")
    if API_KEY:
        st.success("✨ AI 視覺引擎：已啟用")
    else:
        st.error("⚠️ AI 引擎：未設定金鑰")
    
    st.divider()
    
    # 放置於側邊欄最下方的系統維護區
    st.markdown("<br>"*5, unsafe_allow_html=True) # 用空白推到底部
    st.caption("進階選項")
    with st.expander("🛠️ 系統還原 (上傳 CSV)"):
        uploaded_file = st.file_uploader("上傳盤點報告", type="csv")
        if uploaded_file and st.button("🚨 強制覆蓋還原", type="primary"):
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
                st.success("✅ 還原成功！")
                st.rerun()
            except Exception as e:
                st.error("還原失敗！")

# =========================================
# 🖥️ 頂部儀表板 (Dashboard)
# =========================================
st.markdown("## 🏢 禮品盤點系統 Pro")

col1, col2, col3 = st.columns([1, 1, 1.5])
total_items = len(st.session_state.inventory)
total_value = sum(safe_float(item.get('price', 0)) * safe_int(item.get('actualQty', 0)) for item in st.session_state.inventory)

with col1: st.metric("📦 庫存品項", total_items)
with col2: st.metric("💰 資產總值", f"${total_value:,.0f}")
with col3:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 重新載入雲端資料", use_container_width=True):
        st.session_state.inventory = load_data()
        st.rerun()

st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)

# 主要分頁
tab_ai, tab_add, tab_scan, tab_table, tab_print = st.tabs([
    "✨ AI 智能建檔", "➕ 手動/掃碼", "🔍 快速盤點", "📊 庫存總表", "🖨️ 封條"
])

# -----------------------------------------
# 分頁 1：✨ AI 智能建檔 (人類審批流)
# -----------------------------------------
with tab_ai:
    st.markdown("### 🤖 拍下包裝，AI 幫你建檔")
    if not API_KEY:
        st.info("請先設定 Gemini API Key")
    else:
        ai_photo = st.camera_input("📸 拍攝產品照片以交給 AI", key="ai_cam")
        
        # 按鈕區
        if ai_photo:
            ai_b64 = process_image_to_b64(ai_photo, max_width=600)
            
            c1, c2 = st.columns(2)
            if c1.button("🔍 找舊貨 +1", use_container_width=True):
                with st.spinner("AI 正在比對庫存特徵..."):
                    inv_summary = [f"SKU: {i.get('sku')} | 名稱: {i.get('name')}" for i in st.session_state.inventory]
                    prompt = f"""香港盤點助手。從清單找最符合產品。
                    清單：{json.dumps(inv_summary)}
                    回覆 JSON：{{"sku": "最匹配SKU或 NEW", "name": "產品名稱", "confidence": "數字0-100", "reason": "簡單說明"}}"""
                    try:
                        ai_result = call_gemini_api(prompt, ai_b64, API_KEY)
                        if ai_result.get("sku") != "NEW" and float(ai_result.get("confidence", 0)) > 50:
                            for item in st.session_state.inventory:
                                if item.get("sku") == ai_result.get("sku"):
                                    item["actualQty"] = safe_int(item.get("actualQty", 0)) + 1
                                    item["isPrinted"] = False
                                    auto_save()
                                    st.success(f"🎉 辨識成功！【{item['name']}】數量已 +1！")
                                    break
                        else:
                            st.warning("🤖 找不到相似舊貨，請使用右側「智能建檔」。")
                    except Exception as e: st.error("AI 辨識失敗")
            
            if c2.button("📝 智能建檔 (擷取資料)", type="primary", use_container_width=True):
                with st.spinner("AI 正在解析包裝資訊..."):
                    prompt = """香港建檔助手。觀察照片自動填表。
                    估算單價(HKD)。嚴格 JSON 回覆：
                    {"name": "詳細名稱", "category": "最接近類別", "unit": "件/箱/樽/套", "sku": "條碼數字或空", "price": 數字或0}
                    類別限選：HAMPER類(cheap餅), HAMPER類(朱古力,餅乾), BB野, 籃, ESG, 酒, 果汁, 永生花, 其他。"""
                    try:
                        st.session_state.pending_ai_item = call_gemini_api(prompt, ai_b64, API_KEY)
                        st.session_state.pending_ai_img = ai_b64 # 暫存圖片，等審批過再上傳
                        st.rerun() # 重新渲染進入審批畫面
                    except Exception as e: st.error("AI 發生錯誤")

        # 🛑 人類審批區域 (當有 pending 狀態時顯示)
        if st.session_state.pending_ai_item:
            st.markdown("---")
            st.markdown("### ✍️ 人工審批：請確認 AI 擷取的資料")
            st.info("💡 檢查無誤後，點擊下方「批准並加入總表」才會正式存入雲端。")
            
            p_data = st.session_state.pending_ai_item
            with st.form("ai_approval_form"):
                col_a, col_b = st.columns(2)
                with col_a:
                    app_name = st.text_input("產品名稱", value=p_data.get("name", ""))
                    app_sku = st.text_input("SKU 編號", value=p_data.get("sku", ""))
                    app_area = st.text_input("區域", value="未指定")
                with col_b:
                    cat_options = ["HAMPER類(cheap餅)", "HAMPER類(朱古力,餅乾)", "BB野", "籃", "ESG", "酒", "果汁", "永生花", "其他"]
                    default_cat = p_data.get("category", "其他")
                    app_cat = st.selectbox("分類", cat_options, index=cat_options.index(default_cat) if default_cat in cat_options else 8)
                    app_unit = st.selectbox("單位", ["件", "箱", "樽", "套", "其他"])
                    app_price = st.number_input("AI 估算單價 ($)", value=safe_float(p_data.get("price", 0.0)))
                    app_qty = st.number_input("實盤數量", min_value=0, value=1)
                
                c_btn1, c_btn2 = st.columns(2)
                submit_approve = c_btn1.form_submit_button("✅ 批准並加入總表", type="primary")
                submit_reject = c_btn2.form_submit_button("❌ 捨棄此筆資料")
                
                if submit_approve:
                    with st.spinner("正在上傳圖片至圖床並儲存..."):
                        img_url = upload_image_to_drive(st.session_state.pending_ai_img, f"AI_{uuid.uuid4().hex[:6]}.jpg")
                        new_item = {
                            "shortCode": generate_short_code(),
                            "area": app_area, "category": app_cat, "sku": app_sku or "N/A",
                            "name": app_name, "unit": app_unit, "price": app_price,
                            "bookQty": 0, "actualQty": app_qty, "image": img_url, "isPrinted": False
                        }
                        st.session_state.inventory.append(new_item)
                        auto_save()
                        st.session_state.pending_ai_item = None # 清除暫存
                        st.success("✅ 審批通過，已成功寫入資料庫！")
                        st.rerun()
                
                if submit_reject:
                    st.session_state.pending_ai_item = None
                    st.warning("🗑️ 已捨棄 AI 建議資料。")
                    st.rerun()

# -----------------------------------------
# 分頁 2：➕ 手動 / 掃碼建檔 (SKU 掃描回歸)
# -----------------------------------------
with tab_add:
    st.markdown("### ➕ 新增產品")
    
    # 📷 SKU 相機掃描區塊 (放在 Expander 裡保持 UI 整潔)
    with st.expander("📷 開啟相機掃描 SKU 條碼 (iPhone 16 Pro 適用)", expanded=False):
        st.caption("💡 拍攝商品條碼，系統會自動解析並填入下方的 SKU 欄位。")
        sku_photo = st.camera_input("拍攝條碼", key="sku_only_cam")
        if sku_photo and decode:
            img = Image.open(sku_photo)
            barcodes = decode(img)
            if barcodes:
                st.session_state.scanned_sku = barcodes[0].data.decode('utf-8')
                st.success(f"🎯 成功掃描 SKU：{st.session_state.scanned_sku}")
            else:
                st.error("⚠️ 無法辨識條碼，請靠近一點或確保對焦清晰。")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    with st.form("manual_add_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            # SKU 預設帶入剛剛掃描到的結果
            new_sku = st.text_input("SKU 編號", value=st.session_state.scanned_sku, placeholder="可手寫或使用上方掃描")
            new_area = st.text_input("區域", placeholder="例: A-01")
            new_name = st.text_input("產品名稱 (必填)*")
        with col2:
            new_cat = st.selectbox("分類", ["HAMPER類(cheap餅)", "HAMPER類(朱古力,餅乾)", "BB野", "籃", "ESG", "酒", "果汁", "永生花", "其他"])
            new_unit = st.selectbox("單位", ["件", "箱", "樽", "套", "其他"])
            new_price = st.number_input("單價 ($) 💡非必填", value=0.0, step=1.0)
            new_qty = st.number_input("初始實盤數量", min_value=0, value=0, step=1)
            
        submit_add = st.form_submit_button("💾 儲存並上傳雲端", type="primary")
        
        if submit_add:
            if not new_name:
                st.error("⚠️ 產品名稱不可空白！")
            else:
                new_item = {
                    "shortCode": generate_short_code(),
                    "area": new_area, "category": new_cat, "sku": new_sku or "N/A",
                    "name": new_name, "unit": new_unit, "price": float(new_price),
                    "bookQty": 0, "actualQty": int(new_qty), "image": "", "isPrinted": False
                }
                st.session_state.inventory.append(new_item)
                st.session_state.scanned_sku = "" # 存檔後清空掃描暫存
                auto_save()
                st.success(f"✅ {new_name} 新增成功！")

# -----------------------------------------
# 分頁 3：🔍 快速盤點 (+/- 操作)
# -----------------------------------------
with tab_scan:
    search_query = st.text_input("🔍 搜尋名稱、SKU 或短碼...", placeholder="輸入關鍵字...")
    
    if search_query:
        filtered_indices = [i for i, item in enumerate(st.session_state.inventory) if search_query.lower() in str(item.values()).lower()]
        for idx in filtered_indices:
            item = st.session_state.inventory[idx]
            with st.container(border=True):
                c1, c2, c3 = st.columns([1, 3, 2])
                with c1:
                    if item.get('image'): st.image(item['image'], width=70)
                    else: st.info("無圖片")
                with c2:
                    st.markdown(f"**{item.get('name')}**")
                    st.caption(f"`{item.get('shortCode')}` | SKU: {item.get('sku')}")
                with c3:
                    bc1, bc2 = st.columns(2)
                    if bc1.button("➖", key=f"m_{idx}", use_container_width=True):
                        if int(item.get('actualQty', 0)) > 0:
                            st.session_state.inventory[idx]['actualQty'] -= 1
                            st.session_state.inventory[idx]['isPrinted'] = False
                            auto_save()
                            st.rerun()
                    if bc2.button("➕", key=f"p_{idx}", type="primary", use_container_width=True):
                        st.session_state.inventory[idx]['actualQty'] += 1
                        st.session_state.inventory[idx]['isPrinted'] = False
                        auto_save()
                        st.rerun()
                    st.markdown(f"<div style='text-align:center; font-weight:bold; font-size:1.2rem;'>{item.get('actualQty',0)} {item.get('unit')}</div>", unsafe_allow_html=True)

# -----------------------------------------
# 分頁 4：📊 庫存總表 (動態修改)
# -----------------------------------------
with tab_table:
    st.markdown("### 📋 庫存總表 (可直接編輯)")
    if st.session_state.inventory:
        df = pd.DataFrame(st.session_state.inventory)
        display_cols = ['shortCode', 'area', 'name', 'sku', 'category', 'price', 'actualQty', 'unit', 'isPrinted']
        for col in display_cols:
            if col not in df.columns: df[col] = False if col == 'isPrinted' else (0 if col in ['price', 'actualQty'] else "")
                
        edited_df = st.data_editor(
            df[display_cols],
            column_config={
                "shortCode": st.column_config.TextColumn("四碼", disabled=True),
                "area": "區域", "name": "產品名稱", "sku": "SKU", "category": "分類",
                "price": st.column_config.NumberColumn("單價", format="$ %.2f"),
                "actualQty": st.column_config.NumberColumn("數量", min_value=0, step=1),
                "isPrinted": st.column_config.CheckboxColumn("已印封條")
            },
            hide_index=True, use_container_width=True, num_rows="dynamic"
        )
        
        if not df[display_cols].equals(edited_df):
            updated_inv = []
            for i, row in edited_df.iterrows():
                original_item = st.session_state.inventory[i] if i < len(st.session_state.inventory) else {}
                updated_inv.append({**original_item, **row.to_dict()})
            st.session_state.inventory = updated_inv
            auto_save()
            st.success("✅ 編輯已自動同步！")
            
        csv = edited_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📊 匯出 Excel (CSV)", data=csv, file_name='盤點總表.csv', mime='text/csv')
    else:
        st.info("尚無資料")

# -----------------------------------------
# 分頁 5：🖨️ 封條列印
# -----------------------------------------
with tab_print:
    unprinted = [item for item in st.session_state.inventory if not item.get('isPrinted')]
    st.metric("待列印封條數量", len(unprinted))
    
    if unprinted:
        if st.button("🖨️ 產生 80mm 批次列印畫面", type="primary"):
            html = """<html><head><style>
                @media print { body { margin: 0; padding: 0; } }
                .seal { page-break-after: always; width: 300px; padding: 10px; font-family: sans-serif; border-bottom: 1px dashed #ccc; margin-bottom: 20px;}
                .header { text-align: center; font-weight: bold; border-bottom: 2px solid black; padding-bottom: 5px; margin-bottom: 10px;}
                .code { font-size: 32px; font-weight: 900; text-align: center; letter-spacing: 5px; border: 2px solid black; padding: 5px; margin: 10px 0;}
                .qty { font-size: 28px; font-weight: bold; text-align: center; margin: 10px 0;}
                .warn { font-size: 12px; text-align: center; border-top: 1px dashed black; padding-top: 5px;}
            </style></head><body onload="window.print()">"""
            for item in unprinted:
                html += f"""<div class='seal'><div class='header'>✅ INVENTORY COMPLETED</div>
                    <div style='display:flex; justify-content:space-between; font-size:12px;'><span>區域: {item.get('area', 'N/A')}</span><span>2026年3月</span></div>
                    <div class='code'>{item.get('shortCode')}</div><div style='text-align:center; font-weight:bold;'>{item.get('name')}</div>
                    <div class='qty'>{item.get('actualQty')} <span style='font-size:14px;'>{item.get('unit')}</span></div>
                    <div class='warn'>⚠️ 封條損毀即屬無效</div></div>"""
            html += "</body></html>"
            st.components.v1.html(html, height=600, scrolling=True)
            for item in st.session_state.inventory:
                if not item.get('isPrinted'): item['isPrinted'] = True
            auto_save()
    else:
        st.success("🎉 所有封條已列印！")

import streamlit as st
import pandas as pd
import requests
import base64
import uuid

# ⚠️ 貼上你剛剛發布的新版 Google Apps Script 網址
GAS_URL = "https://script.google.com/macros/s/AKfycbw9zjR7-DOHCzBhHbDM9QhG22nWpozbU2ENjUayX8Y-AdLVXhddIKm-ea8sI3ToLLXs/exec"

st.set_page_config(page_title="禮品盤點 Pro", page_icon="📦", layout="wide")

# 初始化 Session State (記憶體快取)
if "inventory" not in st.session_state:
    st.session_state.inventory = []

# =========================================
# 🔄 雲端通訊函數
# =========================================
def fetch_data():
    with st.spinner("從雲端載入資料中..."):
        try:
            response = requests.get(GAS_URL)
            if response.status_code == 200 and response.text:
                st.session_state.inventory = response.json()
                st.success("✅ 下載成功！")
            else:
                st.warning("雲端無資料。")
        except Exception as e:
            st.error(f"❌ 下載失敗：{e}")

def save_data(data_list):
    with st.spinner("同步至雲端中..."):
        try:
            payload = {"action": "save_data", "data": data_list}
            headers = {'Content-Type': 'application/json'}
            response = requests.post(GAS_URL, json=payload, headers=headers)
            if response.status_code == 200:
                st.success("✅ 同步成功！")
            else:
                st.error("❌ 同步失敗。")
        except Exception as e:
            st.error(f"❌ 同步失敗：{e}")

def upload_image_to_drive(image_bytes, filename):
    base64_img = base64.b64encode(image_bytes).decode('utf-8')
    payload = {
        "action": "upload_image",
        "base64Data": base64_img,
        "fileName": filename
    }
    headers = {'Content-Type': 'application/json'}
    response = requests.post(GAS_URL, json=payload, headers=headers)
    if response.status_code == 200:
        result = response.json()
        if result.get("status") == "success":
            return result.get("imageUrl")
    return None

# =========================================
# 🖥️ 介面設計 (Dashboard)
# =========================================
st.title("🏢 禮品盤點系統 Pro (Cloud URL 架構)")

# 頂端儀表板
col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="目前庫存總數", value=len(st.session_state.inventory) if 'inventory' in st.session_state else 0)
with col2:
    if st.button("⬇️ 從雲端下載最新資料"):
        fetch_data()
with col3:
    if st.button("⬆️ 保存變更至雲端"):
        save_data(st.session_state.inventory)

st.divider()

# =========================================
# 🗂️ 兩個主要頁面切換
# =========================================
tab1, tab2 = st.tabs(["📝 盤點與建檔 (手機端)", "📊 庫存總表 (電腦端)"])

# 📱 頁籤 1：適合拿著 iPhone 邊走邊拍的介面
with tab1:
    st.subheader("➕ 快速建檔")
    
    # 手機拍照專用元件
    picture = st.camera_input("📸 拍一張產品照 (選填)")

    with st.form("add_item_form"):
        col1, col2 = st.columns(2)
        with col1:
            sku = st.text_input("SKU 編號 (可直接用掃碼槍掃入)", placeholder="掃描或手寫...")
            area = st.text_input("區域", placeholder="例如: A-01")
            name = st.text_input("產品名稱 (必填)")
        with col2:
            category = st.selectbox("分類", ["HAMPER類(cheap餅)", "HAMPER類(朱古力,餅乾)", "BB野", "籃", "ESG", "酒", "果汁", "永生花", "其他"])
            unit = st.selectbox("單位", ["件", "箱", "樽", "套"])
            price = st.number_input("單價 ($)", value=0.0)
            actual_qty = st.number_input("實盤數量", min_value=0, value=0)

        submitted = st.form_submit_button("加入清單")
        
        if submitted:
            if not name:
                st.error("產品名稱不可空白！")
            else:
                image_url = ""
                # 如果有拍照，立刻上傳 Google Drive，只拿回 URL！
                if picture:
                    with st.spinner("⏳ 正在將照片上傳至 Google Drive 圖床..."):
                        img_bytes = picture.getvalue()
                        unique_filename = f"{uuid.uuid4().hex[:8]}.jpg"
                        uploaded_url = upload_image_to_drive(img_bytes, unique_filename)
                        if uploaded_url:
                            image_url = uploaded_url
                            st.success("✅ 圖床連結產生成功！")
                        else:
                            st.warning("⚠️ 照片上傳失敗，但資料仍會建立。")

                # 生成隨機 4 碼
                short_code = uuid.uuid4().hex[:4].upper()
                
                # 建立新資料
                new_item = {
                    "shortCode": short_code,
                    "area": area,
                    "category": category,
                    "sku": sku,
                    "name": name,
                    "unit": unit,
                    "price": price,
                    "bookQty": 0,
                    "actualQty": actual_qty,
                    "image": image_url # 🌟 現在存的是 Cloud URL，不佔手機容量！
                }
                
                st.session_state.inventory.append(new_item)
                save_data(st.session_state.inventory) # 建檔後自動同步
                st.success(f"🎉 {name} 已成功加入雲端資料庫！")

# 💻 頁籤 2：適合坐在辦公室改資料的老闆介面
with tab2:
    st.subheader("📋 所有庫存一覽 (可直接點擊表格修改)")
    
    if st.session_state.inventory:
        df = pd.DataFrame(st.session_state.inventory)
        
        # 展現 Streamlit 的魔力：直接把 DataFrame 變成可以編輯的表格！
        edited_df = st.data_editor(
            df,
            column_config={
                "image": st.column_config.ImageColumn(
                    "產品照片", help="Google Drive 圖床連結"
                ),
                "actualQty": st.column_config.NumberColumn(
                    "實盤數量", min_value=0, step=1
                ),
                "price": st.column_config.NumberColumn(
                    "單價", format="$%.2f"
                )
            },
            hide_index=True,
            num_rows="dynamic"
        )
        
        # 如果老闆在表格裡改了數量或價錢，按一下儲存就會同步到雲端
        if st.button("💾 儲存修改過的表格至雲端"):
            st.session_state.inventory = edited_df.to_dict('records')
            save_data(st.session_state.inventory)
            st.success("✅ 雲端表格已更新！")
    else:
        st.info("目前沒有資料，請先下載或新增。")

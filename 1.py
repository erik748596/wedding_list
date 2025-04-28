# wedding_giftbook_app.py
import streamlit as st
import pandas as pd
import os
from pyngrok import ngrok, conf
import threading
import time
from datetime import datetime

# 移動裝置優化設定
st.set_page_config(
    page_title="婚禮禮金簿",
    page_icon="🎉",
    layout="centered",  # 使用centered而非wide，減少JS依賴
    initial_sidebar_state="collapsed",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "婚禮禮金簿登記系統 v1.0"
    }
)

# 超級簡化版CSS，只保留最基本元素，避免模組導入問題
st.markdown("""
<style>
/* 極簡風格，減少外部依賴 */
.stButton button {width: 100%;}
footer {visibility: hidden;}
#MainMenu {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# 使用固定的Ngrok隧道名稱
TUNNEL_NAME = "wedding-gift-book"

# 獲取或創建固定隧道
def get_or_create_tunnel():
    try:
        # 設置Ngrok認證令牌
        conf.get_default().auth_token = "2vvP504csSSepBnoYt82qZDiAoj_aGuA31J5H65ojaR9qW91"
        
        # 檢查是否已存在相同名稱的隧道
        tunnels = ngrok.get_tunnels()
        for tunnel in tunnels:
            if TUNNEL_NAME in tunnel.name:
                return tunnel.public_url
        
        # 如果沒有找到，創建新的隧道並指定名稱
        tunnel = ngrok.connect(addr="8501", proto="http", name=TUNNEL_NAME)
        return tunnel.public_url
    except Exception as e:
        print(f"隧道創建錯誤: {e}")
        return None

# 自動重連Ngrok的函數 (保持相同URL)
def reconnect_ngrok():
    while True:
        try:
            time.sleep(180)  # 每3分鐘檢查一次
            print(f"檢查隧道狀態...")
            
            # 獲取現有隧道
            tunnels = ngrok.get_tunnels()
            tunnel_exists = False
            
            for tunnel in tunnels:
                if TUNNEL_NAME in tunnel.name:
                    tunnel_exists = True
                    print(f"隧道仍然活躍: {tunnel.public_url}")
                    break
            
            # 如果沒有找到指定名稱的隧道，重新創建
            if not tunnel_exists:
                print("隧道已斷開，重新連接...")
                new_url = get_or_create_tunnel()
                if new_url:
                    st.session_state.public_url = new_url
                    st.session_state.last_reconnect = datetime.now().strftime("%H:%M:%S")
                    print(f"重新連接成功: {new_url}")
        except Exception as e:
            print(f"重連檢查出錯: {e}")

# 密碼驗證函數
def verify_password(password):
    # 設定密碼
    correct_password = "nfuyyds"
    return password == correct_password

# 初始化或獲取公開URL
if 'public_url' not in st.session_state:
    public_url = get_or_create_tunnel()
    if public_url:
        st.session_state.public_url = public_url
        st.session_state.last_reconnect = datetime.now().strftime("%H:%M:%S")
        
        # 啟動重新連接線程
        if 'reconnect_thread_started' not in st.session_state:
            reconnect_thread = threading.Thread(target=reconnect_ngrok, daemon=True)
            reconnect_thread.start()
            st.session_state.reconnect_thread_started = True
else:
    public_url = st.session_state.public_url

# 顯示頂部標題
st.title("🎉 婚禮禮金簿")

# 讀取對照表
@st.cache_data
def load_reference():
    try:
        file_path = "1.xlsx"
        df = pd.read_excel(file_path, sheet_name="(對照表)")
        
        # 確保有"全名"列
        if "全名" not in df.columns:
            st.error("Excel檔案中沒有'全名'列，請檢查Excel檔案結構")
            return pd.DataFrame({"全名": []})
            
        df = df.dropna(subset=["全名"]).reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"讀取Excel時發生錯誤: {e}")
        return pd.DataFrame({"全名": []})

df_ref = load_reference()

# 初始化 session_state
if "records" not in st.session_state:
    st.session_state.records = []

# 初始化驗證狀態
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

# 初始化金額和金額選擇狀態
if "amount" not in st.session_state:
    st.session_state.amount = 0

# 快捷金額選擇函數
def set_amount(amount):
    st.session_state.amount = amount
    st.session_state.amount_selected = True

# 保存資料到CSV
def save_to_csv():
    if st.session_state.records:
        df_records = pd.DataFrame(st.session_state.records)
        df_records.to_csv("婚禮禮金簿紀錄.csv", index=False, encoding="utf-8-sig")

# 讀取已有資料
def load_from_csv():
    try:
        if os.path.exists("婚禮禮金簿紀錄.csv"):
            df = pd.read_csv("婚禮禮金簿紀錄.csv", encoding="utf-8-sig")
            st.session_state.records = df.to_dict('records')
    except Exception as e:
        st.error(f"讀取記錄檔案時發生錯誤: {e}")

# 嘗試載入已有資料
load_from_csv()

# 顯示連接資訊
if public_url:
    with st.expander("📱 連接資訊 (點擊展開)"):
        st.write("請分享以下連結給工作人員:")
        st.code(public_url)
        
        # 生成QR碼
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={public_url}"
        st.image(qr_url, caption="掃描此QR碼連接")
        
        st.info("注意: 系統會自動維護連線，連結將保持不變")
        
        # 顯示上次檢查時間
        if 'last_reconnect' in st.session_state:
            st.write(f"上次連線檢查時間: {st.session_state.last_reconnect}")

# 極簡化頁籤，完全避免JavaScript
tab = st.selectbox("請選擇功能:", 
                   ["📝 新增紀錄", "📊 查看統計", "⚙️ 設定"])

if tab == "📝 新增紀錄":
    # 1️⃣ 使用者輸入關鍵字搜尋
    keyword = st.text_input("🔍 輸入關鍵字搜尋賓客", placeholder="請輸入姓名...")

    # 自動模糊搜尋人名
    if keyword and "全名" in df_ref.columns:
        matched_names = df_ref[df_ref["全名"].str.contains(keyword, na=False)]
        name_options = matched_names["全名"].tolist()
    else:
        matched_names = pd.DataFrame()
        name_options = []

    # 2️⃣ 下拉選單選擇最終人名
    selected_name = st.selectbox("選擇賓客全名", [""] + name_options) if name_options else st.selectbox("選擇賓客全名", [""])

    if selected_name and not df_ref.empty:
        row = df_ref[df_ref["全名"] == selected_name].iloc[0]
        st.success(f"✅ 已選擇：{selected_name}")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**桌名：** {row.get('桌名', '無')}")
        with col2:
            st.write(f"**喜餅名單：** {'有' if pd.notna(row.get('喜餅名單', pd.NA)) else '無'}")

        # 3️⃣ 輸入金額
        amount = st.number_input("💰 禮金金額", min_value=0, max_value=100000, step=100, value=st.session_state.amount, key="gift_amount")
        
        # 新增快捷金額按鈕
        st.write("快捷金額選擇:")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        # 使用回調而非重新加載頁面
        if "amount_selected" not in st.session_state:
            st.session_state.amount_selected = False
            
        with col1:
            if st.button("1800"):
                st.session_state.amount = 1800
                st.session_state.amount_selected = True
        with col2:
            if st.button("2000"):
                st.session_state.amount = 2000
                st.session_state.amount_selected = True
        with col3:
            if st.button("3600"):
                st.session_state.amount = 3600
                st.session_state.amount_selected = True
        with col4:
            if st.button("6600"):
                st.session_state.amount = 6600
                st.session_state.amount_selected = True
        with col5:
            if st.button("8800"):
                st.session_state.amount = 8800
                st.session_state.amount_selected = True
        
        # 如果金額被選擇，更新顯示
        if st.session_state.amount_selected:
            st.write(f"已選擇金額: {st.session_state.amount}")
            st.session_state.amount_selected = False

        # 4️⃣ 確認按鈕：加入紀錄
        if st.button("➕ 新增紀錄", type="primary"):
            # 新增時間戳記
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 使用當前的amount值
            current_amount = amount
            
            st.session_state.records.append({
                "時間": now,
                "全名": selected_name,
                "桌名": row.get("桌名", '無'),
                "是否給喜餅": "是" if pd.notna(row.get('喜餅名單', pd.NA)) else "否",
                "禮金": current_amount
            })
            # 自動保存到CSV
            save_to_csv()
            st.success("🎉 已成功新增紀錄！")
            # 清空金額，準備下一筆
            st.session_state.amount = 0

elif tab == "📊 查看統計":
    # 密碼驗證
    if not st.session_state.authenticated:
        password = st.text_input("請輸入密碼", type="password")
        if st.button("驗證"):
            if verify_password(password):
                st.session_state.authenticated = True
                st.success("驗證成功！")
            else:
                st.error("密碼錯誤，請重試。")
    
    # 如果已驗證，顯示統計資訊
    if st.session_state.authenticated:
        if st.session_state.records:
            # 建立紀錄DataFrame
            df_records = pd.DataFrame(st.session_state.records)
            
            # 顯示統計資訊
            col1, col2, col3 = st.columns(3)
            with col1:
                total_amount = df_records["禮金"].sum()
                st.metric("總禮金金額", f"${total_amount:,}")
            with col2:
                total_guests = len(df_records)
                st.metric("賓客總數", f"{total_guests}人")
            with col3:
                avg_amount = int(total_amount / total_guests) if total_guests > 0 else 0
                st.metric("平均禮金", f"${avg_amount:,}")
            
            # 顯示紀錄表格
            st.subheader("📋 登記紀錄")
            st.dataframe(df_records, use_container_width=True)
            
            # 匯出按鈕
            csv = df_records.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                label="📥 下載 CSV",
                data=csv,
                file_name="婚禮禮金簿紀錄.csv",
                mime="text/csv"
            )
            
            # 登出按鈕
            if st.button("登出"):
                st.session_state.authenticated = False
        else:
            st.info("尚未有任何紀錄")
            
            # 登出按鈕
            if st.button("登出"):
                st.session_state.authenticated = False

elif tab == "⚙️ 設定":
    st.subheader("連接資訊")
    if public_url:
        st.write("👇 請分享以下連結給工作人員")
        st.code(public_url)
        
        # 生成QR碼
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={public_url}"
        st.image(qr_url, caption="掃描此QR碼連接")
        
        # 顯示系統狀態
        st.info(f"連線自動檢查間隔: 3分鐘")
        if 'last_reconnect' in st.session_state:
            st.success(f"上次連線檢查時間: {st.session_state.last_reconnect}")
    else:
        st.error("無法獲取公開連結")
        st.info("請使用區域網路連接: http://192.168.66.16:8501")
    
    # 手動重新檢查連接
    if st.button("🔄 檢查連線狀態"):
        try:
            tunnels = ngrok.get_tunnels()
            tunnel_exists = False
            
            for tunnel in tunnels:
                if TUNNEL_NAME in tunnel.name:
                    tunnel_exists = True
                    st.session_state.public_url = tunnel.public_url
                    st.session_state.last_reconnect = datetime.now().strftime("%H:%M:%S")
                    st.success(f"連線正常！")
                    break
            
            if not tunnel_exists:
                new_url = get_or_create_tunnel()
                if new_url:
                    st.session_state.public_url = new_url
                    st.session_state.last_reconnect = datetime.now().strftime("%H:%M:%S")
                    st.success(f"已重新建立連線")
        except Exception as e:
            st.error(f"檢查連線失敗: {e}")
    
    # 清除所有紀錄
    st.subheader("資料管理")
    if st.button("🗑️ 清除所有紀錄"):
        confirm = st.checkbox("我確認要清除所有紀錄")
        if confirm:
            st.session_state.records = []
            if os.path.exists("婚禮禮金簿紀錄.csv"):
                os.remove("婚禮禮金簿紀錄.csv")
            st.success("已清除所有紀錄！")
    
    # 顯示系統資訊
    st.subheader("系統資訊")
    st.write(f"資料來源: 1.xlsx")
    st.write(f"對照表內容數量: {len(df_ref)}筆")
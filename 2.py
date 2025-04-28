# wedding_giftbook_app.py
import streamlit as st
import pandas as pd
import os
from pyngrok import ngrok, conf
import threading
import time
import requests
from datetime import datetime
import logging
import socket

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("ngrok_connection.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
# Ngrok認證令牌
NGROK_AUTH_TOKEN = "2vvP504csSSepBnoYt82qZDiAoj_aGuA31J5H65ojaR9qW91"
# 最大重試次數
MAX_RETRIES = 5
# 檢查間隔（秒）
CHECK_INTERVAL = 120  # 2分鐘檢查一次
# 健康檢查超時（秒）
HEALTH_CHECK_TIMEOUT = 5

# 獲取或創建固定隧道
def get_or_create_tunnel(retries=MAX_RETRIES):
    """
    獲取現有隧道或創建新隧道，帶有重試機制
    """
    for attempt in range(retries):
        try:
            # 設置Ngrok認證令牌
            conf.get_default().auth_token = NGROK_AUTH_TOKEN
            
            # 確保ngrok進程在運行（如果不在運行則啟動）
            try:
                # 嘗試取得隧道列表，如果失敗代表ngrok未啟動
                tunnels = ngrok.get_tunnels()
            except Exception as e:
                logger.warning(f"Ngrok似乎未運行，嘗試啟動: {e}")
                # 強制啟動Ngrok進程
                ngrok._connect_current_proc_auth_token()
            
            # 檢查是否已存在相同名稱的隧道
            tunnels = ngrok.get_tunnels()
            logger.info(f"當前隧道數量: {len(tunnels)}")
            
            for tunnel in tunnels:
                if TUNNEL_NAME in tunnel.name:
                    logger.info(f"找到現有隧道: {tunnel.public_url}")
                    
                    # 檢查隧道是否能訪問
                    if is_tunnel_healthy(tunnel.public_url):
                        logger.info(f"隧道運作正常: {tunnel.public_url}")
                        return tunnel.public_url
                    else:
                        logger.warning(f"隧道異常，準備關閉並重建: {tunnel.public_url}")
                        try:
                            # 嘗試關閉異常的隧道
                            ngrok.disconnect(tunnel.public_url)
                        except:
                            # 關閉失敗則繼續嘗試創建新的
                            pass
            
            # 如果沒有找到健康的隧道，創建新的隧道並指定名稱
            logger.info("創建新隧道...")
            
            # 嘗試獲取本地Streamlit端口
            port = get_streamlit_port()
            
            # 連接並創建隧道
            tunnel = ngrok.connect(addr=port, proto="http", name=TUNNEL_NAME)
            logger.info(f"新隧道創建成功: {tunnel.public_url}")
            
            # 驗證新創建的隧道是否健康
            if is_tunnel_healthy(tunnel.public_url):
                return tunnel.public_url
            else:
                logger.error(f"新創建的隧道無法訪問，將重試: {tunnel.public_url}")
                try:
                    ngrok.disconnect(tunnel.public_url)
                except:
                    pass
                continue  # 重試
                
        except Exception as e:
            logger.error(f"隧道創建嘗試 {attempt+1}/{retries} 失敗: {e}")
            time.sleep(2)  # 短暫睡眠後再重試
    
    # 所有嘗試都失敗了
    logger.critical("所有隧道創建嘗試都失敗了！")
    return None

# 檢查隧道健康狀態
def is_tunnel_healthy(url, timeout=HEALTH_CHECK_TIMEOUT):
    """
    檢查隧道是否能夠訪問
    """
    try:
        response = requests.head(url, timeout=timeout)
        # 即使得到4xx錯誤也視為連接正常（可能是認證問題）
        return True
    except requests.RequestException as e:
        logger.warning(f"隧道健康檢查失敗: {url}, 錯誤: {e}")
        return False

# 獲取Streamlit的運行端口
def get_streamlit_port():
    """
    嘗試獲取Streamlit的運行端口，默認為8501
    """
    try:
        # 嘗試檢查8501端口是否被Streamlit占用
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('127.0.0.1', 8501))
        sock.close()
        
        if result == 0:
            logger.info("確認Streamlit在8501端口運行")
            return "8501"
        
        # 如果8501不可用，檢查其他可能的端口
        for port in ["8502", "8503", "8504", "8505"]:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', int(port)))
            sock.close()
            if result == 0:
                logger.info(f"確認Streamlit在{port}端口運行")
                return port
    except Exception as e:
        logger.warning(f"獲取Streamlit端口時出錯: {e}")
    
    # 找不到確切的端口，使用默認值
    logger.info("無法確定Streamlit端口，使用默認8501")
    return "8501"

# 自動重連Ngrok的函數 (保持相同URL)
def reconnect_ngrok():
    """
    定期檢查隧道狀態並根據需要重新連接
    """
    consecutive_failures = 0
    
    while True:
        try:
            # 等待一段時間後再檢查，讓程式啟動有時間完成
            time.sleep(CHECK_INTERVAL)
            logger.info(f"定期檢查隧道狀態...")
            
            if 'public_url' not in st.session_state:
                logger.warning("session_state中沒有public_url，將重新創建")
                url = get_or_create_tunnel()
                if url:
                    st.session_state.public_url = url
                    st.session_state.last_reconnect = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                continue
            
            # 獲取當前的公開URL
            current_url = st.session_state.public_url
            
            # 檢查當前URL是否健康
            if is_tunnel_healthy(current_url):
                logger.info(f"隧道健康檢查通過: {current_url}")
                st.session_state.last_reconnect = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                consecutive_failures = 0
                continue
            
            # 隧道不健康，檢查是否存在同名隧道
            logger.warning(f"隧道健康檢查失敗: {current_url}，將檢查隧道列表")
            tunnels = ngrok.get_tunnels()
            tunnel_exists = False
            
            for tunnel in tunnels:
                if TUNNEL_NAME in tunnel.name:
                    # 找到了同名隧道，檢查是否健康
                    if is_tunnel_healthy(tunnel.public_url):
                        logger.info(f"找到健康的同名隧道: {tunnel.public_url}")
                        st.session_state.public_url = tunnel.public_url
                        st.session_state.last_reconnect = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        tunnel_exists = True
                        consecutive_failures = 0
                        break
            
            # 沒有找到健康的同名隧道，重新創建
            if not tunnel_exists:
                logger.warning("沒有找到健康的同名隧道，將重新創建")
                
                # 嘗試清理所有隧道
                try:
                    for tunnel in tunnels:
                        if TUNNEL_NAME in tunnel.name:
                            logger.info(f"關閉現有隧道: {tunnel.public_url}")
                            ngrok.disconnect(tunnel.public_url)
                except Exception as e:
                    logger.error(f"關閉現有隧道時出錯: {e}")
                
                # 重新創建新隧道
                new_url = get_or_create_tunnel()
                if new_url:
                    logger.info(f"成功重新創建隧道: {new_url}")
                    st.session_state.public_url = new_url
                    st.session_state.last_reconnect = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    consecutive_failures = 0
                else:
                    logger.error("無法重新創建隧道")
                    consecutive_failures += 1
            
            # 如果連續失敗次數過多，增加檢查頻率
            if consecutive_failures > 3:
                logger.warning(f"連續{consecutive_failures}次失敗，將更頻繁地檢查")
                time.sleep(30)  # 縮短檢查間隔至30秒
            elif consecutive_failures > 5:
                logger.critical(f"連續{consecutive_failures}次失敗，可能需要人工介入")
                # 嘗試重新啟動ngrok進程
                try:
                    # 強制關閉現有ngrok進程並重新啟動
                    logger.info("嘗試重置ngrok進程...")
                    ngrok.kill()
                    time.sleep(2)
                    conf.get_default().auth_token = NGROK_AUTH_TOKEN
                    ngrok._connect_current_proc_auth_token()
                    time.sleep(3)
                    new_url = get_or_create_tunnel()
                    if new_url:
                        st.session_state.public_url = new_url
                        st.session_state.last_reconnect = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        consecutive_failures = 0
                        logger.info(f"ngrok進程重置成功: {new_url}")
                except Exception as e:
                    logger.error(f"嘗試重置ngrok進程失敗: {e}")
        
        except Exception as e:
            logger.error(f"重連檢查出錯: {e}")
            consecutive_failures += 1
            if consecutive_failures > 10:
                logger.critical("嚴重錯誤：連續10次失敗，將短暫暫停重連線程")
                time.sleep(300)  # 等待5分鐘後再繼續
                consecutive_failures = 5  # 重設計數器但保持警戒狀態

# 密碼驗證函數
def verify_password(password):
    # 設定密碼
    correct_password = "nfuyyds"
    return password == correct_password

# 初始化或獲取公開URL
if 'public_url' not in st.session_state:
    logger.info("首次啟動，獲取公開URL")
    public_url = get_or_create_tunnel()
    if public_url:
        st.session_state.public_url = public_url
        st.session_state.last_reconnect = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"成功獲取公開URL: {public_url}")
        
        # 啟動重新連接線程
        if 'reconnect_thread_started' not in st.session_state:
            logger.info("啟動重連線程")
            reconnect_thread = threading.Thread(target=reconnect_ngrok, daemon=True)
            reconnect_thread.start()
            st.session_state.reconnect_thread_started = True
    else:
        logger.critical("無法獲取公開URL！")
else:
    public_url = st.session_state.public_url
    logger.info(f"使用現有公開URL: {public_url}")

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
            logger.error("Excel檔案中沒有'全名'列")
            return pd.DataFrame({"全名": []})
            
        df = df.dropna(subset=["全名"]).reset_index(drop=True)
        logger.info(f"成功載入對照表，共{len(df)}筆資料")
        return df
    except Exception as e:
        st.error(f"讀取Excel時發生錯誤: {e}")
        logger.error(f"讀取Excel時發生錯誤: {e}")
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
        try:
            df_records = pd.DataFrame(st.session_state.records)
            df_records.to_csv("婚禮禮金簿紀錄.csv", index=False, encoding="utf-8-sig")
            logger.info("成功保存資料到CSV")
            
            # 創建備份
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            df_records.to_csv(f"婚禮禮金簿紀錄_備份_{timestamp}.csv", index=False, encoding="utf-8-sig")
        except Exception as e:
            logger.error(f"保存CSV時發生錯誤: {e}")

# 讀取已有資料
def load_from_csv():
    try:
        if os.path.exists("婚禮禮金簿紀錄.csv"):
            df = pd.read_csv("婚禮禮金簿紀錄.csv", encoding="utf-8-sig")
            st.session_state.records = df.to_dict('records')
            logger.info(f"成功載入CSV，共{len(df)}筆記錄")
    except Exception as e:
        st.error(f"讀取記錄檔案時發生錯誤: {e}")
        logger.error(f"讀取記錄檔案時發生錯誤: {e}")

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
else:
    st.error("⚠️ 無法獲取公開連結，請檢查網路狀態")
    logger.critical("無法顯示公開連結！")

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
            logger.info(f"已新增紀錄: {selected_name}, 金額: {current_amount}")
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
                logger.info("統計頁面驗證成功")
            else:
                st.error("密碼錯誤，請重試。")
                logger.warning("統計頁面密碼錯誤")
    
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
                logger.info("用戶登出統計頁面")
        else:
            st.info("尚未有任何紀錄")
            
            # 登出按鈕
            if st.button("登出"):
                st.session_state.authenticated = False
                logger.info("用戶登出統計頁面")

elif tab == "⚙️ 設定":
    st.subheader("連接資訊")
    if public_url:
        st.write("👇 請分享以下連結給工作人員")
        st.code(public_url)
        
        # 生成QR碼
        qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={public_url}"
        st.image(qr_url, caption="掃描此QR碼連接")
        
        # 顯示系統狀態
        st.info(f"連線自動檢查間隔: {CHECK_INTERVAL//60}分鐘")
        if 'last_reconnect' in st.session_state:
            st.success(f"上次連線檢查時間: {st.session_state.last_reconnect}")
    else:
        st.error("無法獲取公開連結")
        st.info("請使用區域網路連接或重新啟動應用")
    
    # 手動重新檢查連接
    if st.button("🔄 檢查連線狀態"):
        try:
            if 'public_url' in st.session_state:
                # 檢查當前URL是否健康
                if is_tunnel_healthy(st.session_state.public_url):
                    logger.info(f"手動檢查: 連線正常")
                    st.session_state.last_reconnect = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.success("✅ 連線正常！")
                else:
                    # 嘗試創建新的連接
                    logger.warning(f"手動檢查: 連線異常，準備重新創建")
                    new_url = get_or_create_tunnel()
                    if new_url:
                        st.session_state.public_url = new_url
                        st.session_state.last_reconnect = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        st.success(f"✅ 已重新建立連線")
                        logger.info(f"手動重建連線成功: {new_url}")
                    else:
                        st.error("❌ 無法重新建立連線")
                        logger.error("手動重建連線失敗")
            else:
                # 尚未有連接，創建新的
                new_url = get_or_create_tunnel()
                if new_url:
                    st.session_state.public_url = new_url
                    st.session_state.last_reconnect = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.success(f"✅ 已建立連線")
                    logger.info(f"首次手動建立連線成功: {new_url}")
                else:
                    st.error("❌ 無法建立連線")
                    logger.error("首次手動建立連線失敗")
        except Exception as e:
            st.error(f"檢查連線失敗: {e}")
            logger.error(f"手動檢查連線失敗: {e}")
    
    # 系統狀態檢查
    if st.button("🔍 檢視詳細連接狀態"):
        try:
            tunnels = ngrok.get_tunnels()
            st.success(f"找到 {len(tunnels)} 個活躍隧道")
            
            for i, tunnel in enumerate(tunnels):
                st.write(f"隧道 {i+1}: {tunnel.name} - {tunnel.public_url}")
                health = is_tunnel_healthy(tunnel.public_url)
                st.write(f"健康狀態: {'✅ 正常' if health else '❌ 異常'}")
            
            # 顯示日誌片段
            if os.path.exists("ngrok_connection.log"):
                with open("ngrok_connection.log", "r") as f:
                    logs = f.readlines()
                    recent_logs = logs[-10:]  # 顯示最近10行
                    st.write("最近的連接日誌:")
                    for log in recent_logs:
                        st.write(log.strip())
        except Exception as e:
            st.error(f"獲取隧道狀態失敗: {e}")
            logger.error(f"獲取隧道狀態失敗: {e}")
    
    # 清除所有紀錄
    st.subheader("資料管理")
    if st.button("🗑️ 清除所有紀錄"):
        confirm = st.checkbox("我確認要清除所有紀錄")
        if confirm:
            st.session_state.records = []
            if os.path.exists("婚禮禮金簿紀錄.csv"):
                os.remove("婚禮禮金簿紀錄.csv")
            st.success("已清除所有紀錄！")
            logger.info("用戶清除了所有紀錄")
    
    # 顯示系統資訊
    st.subheader("系統資訊")
    st.write(f"資料來源: 1.xlsx")
    st.write(f"對照表內容數量: {len(df_ref)}筆")
    st.write(f"程式執行狀態: 正常")
    st.write(f"系統版本: 婚禮禮金簿 1.1 (穩定連接加強版)")
    
    # 重置ngrok進程
    with st.expander("⚠️ 進階選項"):
        st.warning("以下操作可能會暫時中斷連接，請謹慎使用")
        if st.button("🔄 重置ngrok進程"):
            try:
                logger.warning("用戶手動重置ngrok進程")
                st.info("正在重置ngrok進程...")
                
                # 關閉所有隧道
                tunnels = ngrok.get_tunnels()
                for tunnel in tunnels:
                    logger.info(f"關閉隧道: {tunnel.public_url}")
                    ngrok.disconnect(tunnel.public_url)
                
                # 重置ngrok進程
                ngrok.kill()
                time.sleep(2)
                
                # 重新設置
                conf.get_default().auth_token = NGROK_AUTH_TOKEN
                ngrok._connect_current_proc_auth_token()
                time.sleep(3)
                
                # 重新創建隧道
                new_url = get_or_create_tunnel()
                if new_url:
                    st.session_state.public_url = new_url
                    st.session_state.last_reconnect = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.success(f"✅ ngrok進程重置成功！")
                    st.write(f"新的連接URL: {new_url}")
                    logger.info(f"ngrok進程重置成功: {new_url}")
                else:
                    st.error("❌ 無法重新建立連線")
                    logger.error("ngrok進程重置後無法建立新連接")
            except Exception as e:
                st.error(f"重置ngrok失敗: {e}")
                logger.error(f"重置ngrok失敗: {e}")
                
        # 顯示授權資訊
        if st.button("查看授權狀態"):
            try:
                # 檢查ngrok授權狀態
                if NGROK_AUTH_TOKEN:
                    st.success("✅ Ngrok授權令牌已設置")
                else:
                    st.error("❌ Ngrok授權令牌未設置")
            except Exception as e:
                st.error(f"檢查授權狀態失敗: {e}")
                
# 當Streamlit退出時嘗試清理資源
def cleanup():
    try:
        logger.info("應用正在關閉，嘗試保持隧道運行...")
    except:
        pass

# 註冊清理函數
import atexit
atexit.register(cleanup)
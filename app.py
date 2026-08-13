import streamlit as st
import pandas as pd
import re

# 1. Cấu hình giao diện Streamlit
st.set_page_config(
    page_title="The GG - Internal Database App",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Thiết lập giao diện Dark Mode hiện đại bằng CSS kết hợp Tooltip hover hình ảnh
st.markdown("""
<style>
    .main-title {
        font-size: 38px;
        font-weight: 800;
        color: #FF4B4B;
        margin-bottom: 5px;
    }
    .minigame-container {
        background-color: #1E1E24;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #FF9800;
        margin-bottom: 20px;
    }
    .game-card {
        background-color: #0E1117;
        padding: 8px 15px;
        border-radius: 5px;
        border: 1px solid #30363D;
        margin-bottom: 6px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    /* Cấu trúc Tooltip CSS siêu mượt */
    .tooltip-container {
        position: relative;
        display: block;
        width: 100%;
        text-decoration: none;
        color: inherit;
    }
    .tooltip-container .tooltip-image {
        visibility: hidden;
        position: absolute;
        z-index: 99999;
        border: 3px solid #FF4B4B;
        border-radius: 8px;
        background-color: #1E1E24;
        padding: 5px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.6);
        top: 50%;
        left: 102%;
        transform: translateY(-50%);
        opacity: 0;
        transition: opacity 0.2s ease, visibility 0.2s ease;
        max-width: 250px;
        max-height: 180px;
        height: auto;
    }
    .tooltip-container:hover .tooltip-image {
        visibility: visible;
        opacity: 1;
    }
</style>
""", unsafe_allow_html=True)

# 2. Cấu hình URL xuất CSV từ 2 Tabs mới của bạn
G_SHEET_GAMES_URL = st.secrets.get(
    "g_sheet_games_url", 
    "the_gg_games_tab.csv" # Mặc định chạy local bằng file CSV đi kèm
)
G_SHEET_ACCOUNTS_URL = st.secrets.get(
    "g_sheet_accounts_url", 
    "the_gg_accounts_tab.csv"
)

# Hàm tự động chuyển đổi link chia sẻ Google Drive thành link xem ảnh trực tiếp (Direct Image Link)
def convert_google_drive_link(link):
    if pd.isna(link) or not isinstance(link, str):
        return ""
    link = link.strip()
    
    # Pattern 1: https://drive.google.com/file/d/FILE_ID/view?usp=sharing hoặc tương tự
    match_file = re.search(r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)', link)
    if match_file:
        file_id = match_file.group(1)
        return f"https://drive.google.com/uc?export=view&id={file_id}"
        
    # Pattern 2: https://drive.google.com/open?id=FILE_ID
    match_open = re.search(r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)', link)
    if match_open:
        file_id = match_open.group(1)
        return f"https://drive.google.com/uc?export=view&id={file_id}"
        
    return link

# 3. Hàm tải dữ liệu Tab Games (Xử lý gộp dòng ffill và làm sạch cột Image)
@st.cache_data(ttl=120)
def load_games_data(url_or_path):
    try:
        df = pd.read_csv(url_or_path, dtype={'Portal': str})
        df['Portal'] = df['Portal'].astype(str).str.strip()
        
        # Tự động điền các ô trống do gộp dòng (ffill)
        df['Portal'] = df['Portal'].ffill()
        df['Link'] = df['Link'].ffill()
        df['Minigame nhà'] = df['Minigame nhà'].ffill()
        df['Thể loại'] = df.groupby('Portal')['Thể loại'].ffill()
        
        # Nếu cột Image chưa tồn tại, tự động tạo cột trống
        if 'Image' not in df.columns:
            df['Image'] = ""
            
        df['Image'] = df['Image'].ffill()
        df['Game'] = df['Game'].fillna("Không rõ tên")
        
        # Tự động chuyển hóa toàn bộ link Google Drive trong cột Image sang link trực tiếp
        df['Image'] = df['Image'].apply(convert_google_drive_link)
        
        return df
    except Exception as e:
        st.error(f"❌ Không thể tải dữ liệu Games. Chi tiết lỗi: {e}")
        return None

# 4. Hàm tải dữ liệu Tab Accounts
@st.cache_data(ttl=120)
def load_accounts_data(url_or_path):
    try:
        df = pd.read_csv(url_or_path, dtype={'Portal': str})
        df['Portal'] = df['Portal'].astype(str).str.strip()
        df['Username'] = df['Username'].astype(str).str.strip()
        df['Password'] = df['Password'].astype(str).str.strip()
        return df
    except Exception as e:
        return pd.DataFrame(columns=['Portal', 'Username', 'Password'])

# Tải dữ liệu vào ứng dụng
df_games = load_games_data(G_SHEET_GAMES_URL)
df_accounts = load_accounts_data(G_SHEET_ACCOUNTS_URL)

if df_games is not None:
    # --- PHẦN SIDEBAR TRÁI ---
    st.sidebar.markdown("<h2 style='text-align: center; color: #FF4B4B;'>🎮 THE GG APP</h2>", unsafe_allow_html=True)
    st.sidebar.write("---")
    
    # Hiển thị mỗi button trên 1 dòng riêng biệt để tránh tràn chữ và cân đối
    if st.sidebar.button("🔄 Làm mới dữ liệu", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
        
    st.sidebar.link_button("📎 Attachment Center", "#", use_container_width=True)

    # Danh sách các Portal duy nhất
    portals = sorted(df_games['Portal'].unique())
    
    st.sidebar.write("---")
    st.sidebar.subheader("📍 Chọn Cổng Game")
    selected_portal = st.sidebar.selectbox(
        "Lọc theo mã Portal:",
        options=portals,
        index=0
    )
    
    # Bộ lọc tìm kiếm nhanh game (TOÀN CỤC)
    st.sidebar.write("---")
    st.sidebar.subheader("Tìm kiếm Game")
    search_query = st.sidebar.text_input("Nhập tên hoặc mã game", "").strip()
    
    # Thống kê nhanh ở sidebar
    st.sidebar.write("---")
    st.sidebar.subheader("📊 Thống kê nhanh")
    st.sidebar.write(f"- Tổng số Portal: `{len(portals)}`")
    st.sidebar.write(f"- Tổng số đầu game: `{df_games['Game'].nunique()}`")
    if df_accounts is not None and not df_accounts.empty:
        st.sidebar.write(f"- Tổng số tài khoản test: `{len(df_accounts)}`")
        
    # Thêm Copyright trong Sidebar
    st.sidebar.write("---")
    st.sidebar.markdown(
        "<div style='text-align: center; color: #888888; font-size: 11px;'>"
        "© 2026 The GG App<br>"
        "Developed by <b>Nobita</b>"
        "</div>", 
        unsafe_allow_html=True
    )

    # --- KHU VỰC TRANG CHÍNH ---
    # Áp dụng bộ lọc tìm kiếm TOÀN CỤC nếu có nhập từ khóa
    if search_query:
        st.markdown(f"<div class='main-title'>Kết quả tìm kiếm toàn cục: \"{search_query}\"</div>", unsafe_allow_html=True)
        st.write("---")
        
        filtered_games = df_games[df_games['Game'].str.contains(search_query, case=False, na=False)]
        
        if filtered_games.empty:
            st.warning("❌ Không tìm thấy game nào khớp với từ khóa tìm kiếm trên toàn hệ thống.")
        else:
            st.success(f"🔍 Tìm thấy {len(filtered_games)} kết quả phù hợp từ các Portal:")
            grouped_results = filtered_games.groupby('Portal')
            
            for portal_id, group in grouped_results:
                st.markdown(f"#### 📍 Portal {portal_id}")
                portal_link = group.iloc[0]['Link']
                
                link_str = str(portal_link).strip()
                if ": " in link_str:
                    label, url = link_str.split(": ", 1)
                    st.markdown(f"**🔗 Đường dẫn truy cập:** {label}: [{url}]({url})")
                else:
                    st.markdown(f"**🔗 Đường dẫn truy cập:** [{link_str}]({link_str})")
                
                for idx, row in group.iterrows():
                    parts = row['Game'].strip().split(" ", 1)
                    img_url = row['Image'] if pd.notna(row['Image']) and str(row['Image']).strip() else ""
                    
                    # Xác định chuỗi tên hiển thị
                    if len(parts) == 2 and parts[0].isdigit():
                        game_text = f"📂 <b>{row['Thể loại']}</b> | <span style='color: #FF4B4B; font-weight: bold;'>{parts[0]}</span> | {parts[1]}"
                    else:
                        game_text = f"📂 <b>{row['Thể loại']}</b> | {row['Game']}"
                        
                    # Dựng thẻ HTML hover hình ảnh
                    if img_url:
                        game_html = f"""
                        <div class='tooltip-container'>
                            <div class='game-card'>
                                <span>{game_text}</span>
                                <span style='font-size: 11px; color: #888;'>🖼️ Hover xem ảnh</span>
                            </div>
                            <img class='tooltip-image' src='{img_url}' alt='{row["Game"]}'>
                        </div>
                        """
                    else:
                        game_html = f"<div class='game-card'>{game_text}</div>"
                        
                    st.markdown(game_html, unsafe_allow_html=True)
                st.write("")
        st.write("---")
        
    else:
        # Hiển thị chi tiết theo Portal được chọn (Mặc định)
        portal_games = df_games[df_games['Portal'] == selected_portal]
        first_row = portal_games.iloc[0]
        portal_link = first_row['Link']
        minigames_raw = first_row['Minigame nhà']
        
        st.markdown(f"<div class='main-title'>Portal {selected_portal}</div>", unsafe_allow_html=True)
        
        link_str = str(portal_link).strip()
        if ": " in link_str:
            label, url = link_str.split(": ", 1)
            st.markdown(f"**🔗 Đường dẫn truy cập:** {label}: [{url}]({url})")
        else:
            st.markdown(f"**🔗 Đường dẫn truy cập:** [{link_str}]({link_str})")
            
        st.write("---")
        
        col_left, col_right = st.columns([1, 1])
        
        # CỘT TRÁI: HIỂN THỊ DANH SÁCH GAME CÓ HOVER HÌNH ẢNH
        with col_left:
            st.subheader("🎮 Danh Sách Trò Chơi")
            categories = portal_games['Thể loại'].unique()
            
            for category in categories:
                st.markdown(f"##### 📂 {category}")
                cat_data = portal_games[portal_games['Thể loại'] == category]
                
                for idx, row in cat_data.iterrows():
                    game_name = row['Game']
                    parts = game_name.strip().split(" ", 1)
                    img_url = row['Image'] if pd.notna(row['Image']) and str(row['Image']).strip() else ""
                    
                    if len(parts) == 2 and parts[0].isdigit():
                        game_text = f"<span style='color: #FF4B4B; font-weight: bold;'>{parts[0]}</span> | {parts[1]}"
                    else:
                        game_text = game_name
                        
                    # Dựng thẻ HTML hover hình ảnh
                    if img_url:
                        game_html = f"""
                        <div class='tooltip-container'>
                            <div class='game-card'>
                                <span>{game_text}</span>
                                <span style='font-size: 11px; color: #888;'>🖼️ Hover xem ảnh</span>
                            </div>
                            <img class='tooltip-image' src='{img_url}' alt='{game_name}'>
                        </div>
                        """
                    else:
                        game_html = f"<div class='game-card'>{game_text}</div>"
                        
                    st.markdown(game_html, unsafe_allow_html=True)
                st.write("")
                
        # CỘT PHẢI: MINIGAME NHÀ & TÀI KHOẢN KHÁCH HÀNG
        with col_right:
            st.subheader("🃏 Minigame Nhà")
            if pd.isna(minigames_raw) or str(minigames_raw).strip().lower() in ["không có", "nan", ""]:
                st.info("Cổng này hiện **không có** Minigame nhà.")
            else:
                m_list = re.split(r'<br>|\n', str(minigames_raw))
                minigame_html = "<div class='minigame-container'>"
                for m in m_list:
                    if m.strip():
                        minigame_html += f"<div style='margin-bottom: 5px; color: #FFFFFF;'>🔹 <b>{m.strip()}</b></div>"
                minigame_html += "</div>"
                st.markdown(minigame_html, unsafe_allow_html=True)
                
            st.write("---")
            
            st.subheader("🔑 Tài Khoản Test (Nội Bộ)")
            if df_accounts is not None and not df_accounts.empty:
                portal_accs = df_accounts[df_accounts['Portal'] == selected_portal]
                
                if len(portal_accs) > 0:
                    st.markdown("**👤 Username**")
                    for idx, row in portal_accs.reset_index(drop=True).iterrows():
                        st.code(row['Username'], language="")
                    st.caption("💡 Bạn có thể click vào biểu tượng sao chép ở góc phải của ô Username để copy nhanh.")
                else:
                    st.warning("⚠️ Hiện chưa có tài khoản test nào được đăng ký cho cổng này.")
            else:
                st.warning("⚠️ Chưa cấu hình hoặc không tìm thấy dữ liệu tài khoản từ Tab Accounts.")
                
    # Phần copyright ở chân trang chính
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #888888; font-size: 13px; margin-top: 20px;'>"
        "© 2026 The GG. All rights reserved. <br>"
        "Developed by <b>Nobita</b>"
        "</div>", 
        unsafe_allow_html=True
    )
else:
    st.info("Vui lòng cấu hình URL Database của bạn trong cài đặt secrets.")

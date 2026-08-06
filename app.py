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

# Thiết lập giao diện Dark Mode hiện đại bằng CSS
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
    }
    .account-row {
        padding: 8px 0;
        border-bottom: 1px solid #222;
        align-items: center;
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

# 3. Hàm tải dữ liệu Tab Games (Xử lý gộp dòng ffill phòng trường hợp bạn copy/paste thủ công)
@st.cache_data(ttl=120)  # Bộ nhớ đệm 2 phút để tự động cập nhật khi bạn sửa Sheet
def load_games_data(url_or_path):
    try:
        # Đọc dữ liệu, ép kiểu Portal thành str để giữ nguyên các mã như 098, 055
        df = pd.read_csv(url_or_path, dtype={'Portal': str})
        
        # Làm sạch cột Portal
        df['Portal'] = df['Portal'].astype(str).str.strip()
        
        # Tự động điền các ô trống do gộp dòng (ffill)
        df['Portal'] = df['Portal'].ffill()
        df['Link'] = df['Link'].ffill()
        df['Minigame nhà'] = df['Minigame nhà'].ffill()
        df['Thể loại'] = df.groupby('Portal')['Thể loại'].ffill()
        
        df['Game'] = df['Game'].fillna("Không rõ tên")
        return df
    except Exception as e:
        st.error(f"❌ Không thể tải dữ liệu Games. Chi tiết lỗi: {e}")
        return None

# 4. Hàm tải dữ liệu Tab Accounts (Cấu trúc bảng sạch 3 cột)
@st.cache_data(ttl=120)
def load_accounts_data(url_or_path):
    try:
        df = pd.read_csv(url_or_path, dtype={'Portal': str})
        df['Portal'] = df['Portal'].astype(str).str.strip()
        df['Username'] = df['Username'].astype(str).str.strip()
        df['Password'] = df['Password'].astype(str).str.strip()
        return df
    except Exception as e:
        # Nếu chưa cấu hình hoặc cấu hình lỗi, trả về DataFrame trống để không lỗi app
        return pd.DataFrame(columns=['Portal', 'Username', 'Password'])

# Tải dữ liệu vào ứng dụng
df_games = load_games_data(G_SHEET_GAMES_URL)
df_accounts = load_accounts_data(G_SHEET_ACCOUNTS_URL)

if df_games is not None:
    # --- PHẦN SIDEBAR TRÁI ---
    st.sidebar.markdown("<h2 style='text-align: center; color: #FF4B4B;'>🎮 THE GG APP</h2>", unsafe_allow_html=True)
    st.sidebar.write("---")
    
    # Nút bấm làm mới dữ liệu thủ công
    if st.sidebar.button("🔄 Làm mới dữ liệu từ Google Sheet"):
        st.cache_data.clear()
        st.rerun()

    # Danh sách các Portal duy nhất
    portals = sorted(df_games['Portal'].unique())
    
    st.sidebar.subheader("📍 Chọn Cổng Game")
    selected_portal = st.sidebar.selectbox(
        "Lọc theo mã Portal:",
        options=portals,
        index=0
    )
    
    # Bộ lọc tìm kiếm nhanh tên game
    st.sidebar.write("---")
    st.sidebar.subheader("🔍 Tìm kiếm nhanh Game")
    search_query = st.sidebar.text_input("Nhập tên hoặc mã game:", "").strip()
    
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
    # Lấy thông tin game của Portal được chọn
    portal_games = df_games[df_games['Portal'] == selected_portal]
    
    # Lấy thông tin chung của Portal từ dòng đầu tiên trong nhóm
    first_row = portal_games.iloc[0]
    portal_link = first_row['Link']
    minigames_raw = first_row['Minigame nhà']
    
    # Tiêu đề Portal
    st.markdown(f"<div class='main-title'>Portal {selected_portal}</div>", unsafe_allow_html=True)
    
    # Hiển thị đường link dạng text clickable đẹp mắt, không trùng lặp, bỏ button "Mở Cổng Game"
    link_str = str(portal_link).strip()
    if ": " in link_str:
        label, url = link_str.split(": ", 1)
        st.markdown(f"**🔗 Đường dẫn truy cập:** {label}: [{url}]({url})")
    else:
        st.markdown(f"**🔗 Đường dẫn truy cập:** [{link_str}]({link_str})")
        
    st.write("---")
    
    # Áp dụng bộ lọc tìm kiếm nếu có nhập từ khóa
    if search_query:
        # Tìm kiếm không phân biệt hoa thường
        filtered_games = portal_games[portal_games['Game'].str.contains(search_query, case=False, na=False)]
        st.info(f"🔍 Kết quả tìm kiếm từ khóa '{search_query}' trong Portal {selected_portal}:")
        if filtered_games.empty:
            st.warning("Không tìm thấy game nào khớp với từ khóa tìm kiếm.")
        else:
            for idx, row in filtered_games.iterrows():
                st.markdown(f"<div class='game-card'>📂 <b>{row['Thể loại']}</b> | {row['Game']}</div>", unsafe_allow_html=True)
        st.write("---")
    
    col_left, col_right = st.columns([1, 1])
    
    # CỘT TRÁI: HIỂN THỊ DANH SÁCH GAME PHÂN THEO THỂ LOẠI
    with col_left:
        st.subheader("🎮 Danh Sách Trò Chơi")
        categories = portal_games['Thể loại'].unique()
        
        for category in categories:
            st.markdown(f"##### 📂 {category}")
            cat_games = portal_games[portal_games['Thể loại'] == category]['Game'].tolist()
            
            for game in cat_games:
                parts = game.strip().split(" ", 1)
                # Đổi màu mã số game cho nổi bật và dễ nhìn
                if len(parts) == 2 and parts[0].isdigit():
                    game_html = f"<div class='game-card'><span style='color: #FF4B4B; font-weight: bold;'>{parts[0]}</span> | {parts[1]}</div>"
                else:
                    game_html = f"<div class='game-card'>{game}</div>"
                st.markdown(game_html, unsafe_allow_html=True)
            st.write("")
            
    # CỘT PHẢI: MINIGAME NHÀ & TÀI KHOẢN KHÁCH HÀNG
    with col_right:
        # 1. Minigame nhà (ĐÃ SỬA LỖI RỚT KHUNG)
        st.subheader("🃏 Minigame Nhà")
        if pd.isna(minigames_raw) or str(minigames_raw).strip().lower() in ["không có", "nan", ""]:
            st.info("Cổng này hiện **không có** Minigame nhà.")
        else:
            # Tách các minigame nếu chúng cách nhau bằng thẻ <br> hoặc xuống dòng
            m_list = re.split(r'<br>|\n', str(minigames_raw))
            # Ghép toàn bộ nội dung HTML lại để render trong 1 hàm st.markdown duy nhất
            minigame_html = "<div class='minigame-container'>"
            for m in m_list:
                if m.strip():
                    minigame_html += f"<div style='margin-bottom: 5px; color: #FFFFFF;'>🔹 <b>{m.strip()}</b></div>"
            minigame_html += "</div>"
            
            st.markdown(minigame_html, unsafe_allow_html=True)
            
        st.write("---")
        
        # 2. Tài khoản nội bộ được lấy trực tiếp từ Tab Accounts sạch đẹp
        st.subheader("🔑 Tài Khoản Test (Nội Bộ)")
        
        if df_accounts is not None and not df_accounts.empty:
            # Lọc tài khoản tương ứng với Portal được chọn
            portal_accs = df_accounts[df_accounts['Portal'] == selected_portal]
            
            if len(portal_accs) > 0:
                # Tiêu đề cột
                col_u_hdr, col_p_hdr, col_b_hdr = st.columns([3, 3, 1])
                with col_u_hdr:
                    st.markdown("**👤 Username**")
                with col_p_hdr:
                    st.markdown("**🔒 Password**")
                with col_b_hdr:
                    st.markdown("<div style='text-align: center;'><b>Show</b></div>", unsafe_allow_html=True)
                
                # Hiển thị từng tài khoản với nút Show/Hide riêng biệt
                for idx, row in portal_accs.reset_index(drop=True).iterrows():
                    # Tạo khóa session_state riêng cho từng tài khoản để quản lý trạng thái show/hide độc lập
                    key = f"show_{selected_portal}_{idx}_{row['Username']}"
                    if key not in st.session_state:
                        st.session_state[key] = False
                    
                    st.markdown("<div style='margin: 1px 0;'>", unsafe_allow_html=True)
                    col_user, col_pass, col_btn = st.columns([3, 3, 1])
                    
                    with col_user:
                        st.code(row['Username'], language="")
                        
                    with col_pass:
                        display_pass = row['Password'] if st.session_state[key] else "••••••••"
                        st.code(display_pass, language="")
                        
                    with col_btn:
                        btn_label = "🔒 Hide" if st.session_state[key] else "👁️ Show"
                        if st.button(btn_label, key=f"btn_{key}", use_container_width=True):
                            st.session_state[key] = not st.session_state[key]
                            st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
                    
                st.caption("💡 Bạn có thể click vào biểu tượng sao chép ở góc phải của ô Username/Password để copy nhanh.")
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
    st.info("Vui lòng cấu hình URL Google Sheet của bạn trong cài đặt secrets.")

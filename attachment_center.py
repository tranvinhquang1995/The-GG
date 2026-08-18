import streamlit as st
import os
import zipfile
import tempfile

def show_attachment_center():
    st.markdown("<div class='main-title'>📎 Attachment Center</div>", unsafe_allow_html=True)
    st.markdown("##### Công cụ Nén và Tải dữ liệu trực tiếp lên Google Drive")
    st.write("---")
    
    # CSS riêng cho hộp công cụ của Attachment Center
    st.markdown("""
    <style>
        .tool-box {
            background-color: #161B22;
            padding: 25px;
            border-radius: 10px;
            border: 1px solid #30363D;
            margin-top: 15px;
        }
    </style>
    """, unsafe_allow_html=True)
    
    with st.container():
        st.markdown("<div class='tool-box'>", unsafe_allow_html=True)
        st.subheader("📤 Khu Vực Upload & Xử Lý File")
        
        # 1. Kéo thả file chuẩn bị nén
        uploaded_files = st.file_uploader(
            "Kéo và thả các file ảnh hoặc tài liệu cần nén vào đây:", 
            accept_multiple_files=True,
            key="attachment_uploader"
        )
        
        # 2. Tùy chọn cấu hình
        col_opt1, col_opt2 = st.columns(2)
        with col_opt1:
            zip_name = st.text_input("📁 Đặt tên file nén (.zip):", value="GG_Attachments_New").strip()
            if not zip_name:
                zip_name = "GG_Attachments_New"
        with col_opt2:
            drive_folder_id = st.text_input(
                "🔑 ID Thư mục Google Drive (Để trống nếu dùng mặc định):", 
                placeholder="Nhập ID thư mục Drive...",
                disabled=True  # Vô hiệu hóa trường nhập ID do tính năng upload đang đóng
            ).strip()
            
        st.write("---")
        
        # 3. Khu vực nút xử lý
        col_btn1, col_btn2 = st.columns(2)
        
        with col_btn1:
            # TÍNH NĂNG 1: NÉN FILE (ĐC CHUYỂN SANG Ổ ĐĨA TẠM THỜI ĐỂ TIẾT KIỆM RAM)
            if st.button("⚡ Bắt đầu Nén File", type="primary", use_container_width=True):
                if not uploaded_files:
                    st.warning("⚠️ Vui lòng upload ít nhất 1 file để nén.")
                else:
                    st.info("🔄 Đang tiến hành nén file trên ổ đĩa tạm thời...")
                    
                    try:
                        # Sử dụng tempfile.TemporaryDirectory() để tạo thư mục tạm trên ổ cứng (Disk)
                        with tempfile.TemporaryDirectory() as temp_dir:
                            zip_file_path = os.path.join(temp_dir, f"{zip_name}.zip")
                            
                            # Tiến hành ghi file và nén bằng zipfile
                            with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                                for uploaded_file in uploaded_files:
                                    # Ghi file tạm xuống đĩa cứng để giải phóng RAM
                                    temp_file_path = os.path.join(temp_dir, uploaded_file.name)
                                    with open(temp_file_path, "wb") as f:
                                        f.write(uploaded_file.getbuffer())
                                    
                                    # Thêm file vào file zip
                                    zip_file.write(temp_file_path, arcname=uploaded_file.name)
                            
                            # Đọc file zip dưới dạng bytes để cho phép người dùng tải xuống trực tiếp
                            with open(zip_file_path, "rb") as f:
                                zip_bytes = f.read()
                                
                            st.success(f"🎉 Đã nén thành công {len(uploaded_files)} file!")
                            
                            # Cho phép tải xuống file zip đã nén
                            st.download_button(
                                label="📥 Tải xuống file .ZIP",
                                data=zip_bytes,
                                file_name=f"{zip_name}.zip",
                                mime="application/zip",
                                use_container_width=True
                            )
                    except Exception as e:
                        st.error(f"❌ Có lỗi xảy ra trong quá trình nén: {e}")
                        
        with col_btn2:
            # TÍNH NĂNG 2: UPLOAD LÊN GOOGLE DRIVE (TẠM THỜI DISABLE THEO YÊU CẦU)
            # Dùng nút bấm vô hiệu hóa bằng thuộc tính disabled=True
            st.button("☁️ Tải lên Google Drive (Tạm khóa)", type="secondary", use_container_width=True, disabled=True)
            st.caption("🔒 *Tính năng tải lên Drive hiện đang tạm khóa để bảo trì hệ thống API.*")
            
        st.markdown("</div>", unsafe_allow_html=True)
        
    # Hướng dẫn sử dụng nhanh
    st.write("")
    st.subheader("📖 Hướng dẫn sử dụng nhanh")
    st.markdown("""
    1. **Bước 1:** Kéo thả một hoặc nhiều file hình ảnh, tài liệu của game vào khung upload ở trên.
    2. **Bước 2:** Đặt tên cho file nén (hệ thống sẽ tự động thêm đuôi `.zip`).
    3. **Bước 3:** Bấm nút **Bắt đầu Nén File** để hệ thống tự động gộp và nén trên ổ cứng tạm thời.
    4. **Bước 4:** Bấm **Tải xuống file .ZIP** để lưu tệp nén về thiết bị của bạn.
    5. *(Lưu ý: Tính năng đồng bộ trực tiếp lên Google Drive hiện tại đang tạm đóng để nâng cấp).*
    """)

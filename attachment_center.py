import streamlit as st
import os
import io
import re
import tempfile
import subprocess
from PIL import Image

# Thử nạp các thư viện của Google Drive. 
# Nếu người dùng chưa cài đặt trong requirements.txt, cơ chế này giúp tránh làm sập ứng dụng khi GDRIVE_ENABLED = False.
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    GDRIVE_IMPORTS_OK = True
except ImportError:
    GDRIVE_IMPORTS_OK = False

### --- KHAI BÁO BẬT/TẮT TÍNH NĂNG GOOGLE DRIVE ---
### BẠN CÓ THỂ ĐỔI GIÁ TRỊ NÀY THÀNH True KHI ĐÃ SẴN SÀNG KÍCH HOẠT LẠI TÍNH NĂNG UPLOAD GOOGLE DRIVE
GDRIVE_ENABLED = False

### --- HẰNG SỐ & ĐỊNH CẤU HÌNH ---
### ID thư mục mẹ trên Google Drive (Mọi thư mục con như 109, 110 sẽ được tạo ở đây)
PARENT_FOLDER_ID = st.secrets.get("gdrive", {}).get("parent_folder_id", "YOUR_GOOGLE_DRIVE_PARENT_FOLDER_ID")

### --- HÀM KHỞI TẠO GOOGLE DRIVE SERVICE ---
@st.cache_resource
def get_gdrive_service():
    """Khởi tạo Drive API Service sử dụng Google Service Account từ Secrets"""
    if not GDRIVE_IMPORTS_OK:
        st.error("❌ Không thể khởi chạy Google Drive API do thiếu thư viện. Vui lòng thêm `google-api-python-client` và `google-auth` vào file requirements.txt!")
        return None
    try:
        gcp_info = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            gcp_info, scopes=["https://www.googleapis.com/auth/drive"]
        )
        service = build("drive", "v3", credentials=creds)
        return service
    except Exception as e:
        st.error(f"❌ Không thể cấu hình Google Drive API. Vui lòng kiểm tra st.secrets. Lỗi: {e}")
        return None

### --- CÁC HÀM XỬ LÝ GOOGLE DRIVE ---
def find_or_create_folder(service, folder_name, parent_id):
    """Tìm thư mục con bằng tên dưới thư mục mẹ. Nếu chưa có thì tạo mới."""
    query = f"name = '{folder_name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    try:
        results = service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get("files", [])
        if items:
            return items[0]['id']
        else:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            folder = service.files().create(body=file_metadata, fields='id').execute()
            return folder.get('id')
    except Exception as e:
        st.error(f"❌ Lỗi khi tìm hoặc tạo thư mục: {e}")
        return None

def upload_file_to_drive(service, file_bytes, filename, mime_type, folder_id):
    """Upload file từ bộ nhớ lên thư mục chỉ định trên Google Drive"""
    file_metadata = {
        "name": filename,
        "parents": [folder_id]
    }
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=True)
    try:
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink"
        ).execute()
        return file
    except Exception as e:
        st.error(f"❌ Lỗi khi upload file lên Drive: {e}")
        return None

### --- CÁC HÀM NÉN HÌNH ẢNH & VIDEO (TỐI ƯU DISK-BASED TRÁNH SẬP RAM) ---
def compress_image(image_bytes, file_ext, target_size_mb=10.0):
    """Giảm chất lượng hình ảnh về dưới mức dung lượng mục tiêu (10MB)"""
    target_size_bytes = target_size_mb * 1024 * 1024
    if len(image_bytes) <= target_size_bytes:
        return image_bytes, False
        
    try:
        # Ghi file tạm ra ổ đĩa thay vì xử lý hoàn toàn trên RAM để bảo vệ 1GB RAM của Streamlit
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, f"temp_input{file_ext}")
            with open(input_path, "wb") as f:
                f.write(image_bytes)
            
            img = Image.open(input_path)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            quality = 90
            output_path = os.path.join(temp_dir, "temp_output.jpg")
            img.save(output_path, "JPEG", quality=quality)
            
            while os.path.getsize(output_path) > target_size_bytes and quality > 10:
                quality -= 10
                img.save(output_path, "JPEG", quality=quality)
                
            with open(output_path, "rb") as f:
                compressed_bytes = f.read()
                
            return compressed_bytes, True
    except Exception as e:
        st.error(f"❌ Lỗi khi nén ảnh: {e}")
        return image_bytes, False

def get_video_duration(input_path):
    """Sử dụng ffprobe để lấy thời lượng video phục vụ tính toán bitrate"""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_path
    ]
    try:
        output = subprocess.check_output(cmd).decode().strip()
        return float(output)
    except Exception:
        return None

def compress_video(video_bytes, target_size_mb=10.0):
    """Nén video về dưới 10MB bằng cách tự động tính toán bitrate và dùng ffmpeg"""
    target_size_bytes = target_size_mb * 1024 * 1024
    if len(video_bytes) <= target_size_bytes:
        return video_bytes, False
        
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, "temp_input.mp4")
            output_path = os.path.join(temp_dir, "temp_output.mp4")
            
            with open(input_path, "wb") as f:
                f.write(video_bytes)
                
            duration = get_video_duration(input_path)
            if not duration:
                return video_bytes, False
                
            # Tính toán bitrate mục tiêu (trừ hao 15% cho audio và container overhead)
            target_bitrate_kbps = int((target_size_bytes * 8) / (duration * 1000) * 0.85)
            
            # Chạy ffmpeg
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-b:v", f"{target_bitrate_kbps}k",
                "-maxrate", f"{target_bitrate_kbps}k",
                "-bufsize", f"{target_bitrate_kbps // 2}k",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-profile:v", "baseline", "-level", "3.0",
                "-c:a", "aac", "-b:a", "128k",
                output_path
            ]
            
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                with open(output_path, "rb") as f:
                    compressed_bytes = f.read()
                return compressed_bytes, True
            
        return video_bytes, False
    except Exception as e:
        st.error(f"❌ Lỗi khi nén video: {e}")
        return video_bytes, False

### --- HÀM CHÍNH SHOW GIAO DIỆN CHUYỂN TỪ APP CHÍNH ---
def show_attachment_center():
    # CSS Khóa cứng giao diện tối và căn chỉnh footer đúng bản sắc Nobita
    st.markdown(
        """
        <style>
        #MainMenu {visibility: hidden;}
        .nobita-footer {
            position: fixed;
            left: 0;
            bottom: 0;
            width: 100%;
            background-color: #0E1117;
            color: #888888;
            text-align: center;
            padding: 10px 0;
            font-size: 12px;
            border-top: 1px solid #30363D;
            z-index: 9999;
        }
        .main-container-spacer {
            height: 80px;
        }
        .stButton>button {
            width: 100%;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    st.title("📁 Attachment Center (v5)")
    st.markdown("Tool tối ưu dung lượng attachment để gửi Discord hoặc upload trực tiếp lên Google Drive.")
    st.markdown("---")
    
    # Khởi tạo service chỉ khi GDRIVE_ENABLED bật
    service = None
    if GDRIVE_ENABLED:
        if GDRIVE_IMPORTS_OK:
            service = get_gdrive_service()
        else:
            st.error("❌ Không thể nạp thư viện Google Drive. Vui lòng thêm `google-api-python-client` và `google-auth` vào requirements.txt!")
            
    st.subheader("📤 Upload Attachment & Lựa chọn chức năng")
    uploaded_file = st.file_uploader(
        "Kéo thả hoặc chọn file hình ảnh/video của bạn",
        type=["png", "jpg", "jpeg", "mp4", "mov", "avi", "mkv"]
    )
    
    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        file_name = uploaded_file.name
        file_size_mb = len(file_bytes) / (1024 * 1024)
        mime_type = uploaded_file.type
        file_ext = os.path.splitext(file_name)[1].lower()
        
        # Khởi tạo session state để lưu trạng thái file đã xử lý
        if "processed_file" not in st.session_state or st.session_state.get("original_name") != file_name:
            st.session_state.processed_file = None
            st.session_state.is_compressed = False
            st.session_state.original_name = file_name
            st.session_state.compression_ratio = 0.0
            st.session_state.show_upload_form = False
            
        # Hiển thị thông số file gốc
        st.info(f"📁 **File đã chọn:** {file_name} | ⚖️ **Dung lượng:** {file_size_mb:.2f} MB")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("⚡ Compress (Nén file)", type="primary"):
                st.caption("Giảm dung lượng file xuống dưới 10MB để gửi Discord.")
                if file_size_mb <= 10.0:
                    st.success("✅ File gốc đã dưới 10MB! Sẵn sàng tải về hoặc upload thẳng lên Drive.")
                    st.session_state.processed_file = file_bytes
                    st.session_state.is_compressed = False
                else:
                    with st.spinner("🔄 Đang xử lý nén file dưới 10MB..."):
                        if file_ext in [".png", ".jpg", ".jpeg"]:
                            compressed_bytes, ok = compress_image(file_bytes, file_ext)
                        elif file_ext in [".mp4", ".mov", ".avi", ".mkv"]:
                            compressed_bytes, ok = compress_video(file_bytes)
                        else:
                            compressed_bytes, ok = file_bytes, False
                            
                        if ok:
                            final_size_mb = len(compressed_bytes) / (1024 * 1024)
                            ratio = (1 - (len(compressed_bytes) / len(file_bytes))) * 100
                            st.session_state.processed_file = compressed_bytes
                            st.session_state.is_compressed = True
                            st.session_state.compression_ratio = ratio
                            
                            st.success(f"🎉 Nén thành công! Dung lượng mới: **{final_size_mb:.2f} MB** (Giảm **{ratio:.1f}%**)")
                            if ratio >= 90.0:
                                st.warning("⚠️ Cảnh báo: Chất lượng file đã bị giảm sâu (>90%) để đạt mức dung lượng dưới 10MB.")
                        else:
                            st.error("❌ Không thể nén file về dưới 10MB. Vui lòng kiểm tra lại định dạng hoặc độ dài.")
                            
            # Nếu đã có file được xử lý, hiển thị nút tải về
            if st.session_state.processed_file is not None:
                out_filename = file_name
                if st.session_state.is_compressed:
                    name_part, ext_part = os.path.splitext(file_name)
                    out_filename = f"{name_part}_compressed{ext_part}"
                    
                st.download_button(
                    label="📥 Tải file tạm thời",
                    data=st.session_state.processed_file,
                    file_name=out_filename,
                    mime=mime_type
                )
                
        with col2:
            # Nút Upload Google Drive
            upload_disabled = not GDRIVE_ENABLED
            upload_label = "☁️ Upload Google Drive"
            if upload_disabled:
                upload_label += " [In-process]"
                st.caption("⏳ *Dev đang lỏ! Vui lòng chờ build sau*")
                
            if st.button(upload_label, type="secondary", disabled=upload_disabled):
                st.session_state.show_upload_form = True
                
        # Hiển thị Form cấu hình upload khi click vào Upload
        if GDRIVE_ENABLED and st.session_state.get("show_upload_form", False):
            st.markdown("---")
            st.subheader("📝 Cấu hình thư mục & Tên file trên Drive")
            
            default_folder = "Chung"
            default_save_name = file_name
            
            match = re.match(r"^([a-zA-Z0-9]+)[-_](.+)$", file_name)
            if match:
                default_folder = match.group(1)
                default_save_name = match.group(2)
            
            if st.session_state.processed_file is not None and st.session_state.is_compressed:
                name_part, ext_part = os.path.splitext(default_save_name)
                if "_compressed" not in name_part:
                    default_save_name = f"{name_part}_compressed{ext_part}"
            
            with st.form("gdrive_upload_form"):
                target_folder = st.text_input("📁 Tên thư mục lưu trữ (Ví dụ: 055, 109):", value=default_folder)
                save_name = st.text_input("📄 Tên file sẽ lưu trên Drive:", value=default_save_name)
                
                submit_upload = st.form_submit_button("🚀 Xác nhận tải lên Drive")
                
                if submit_upload:
                    if not service:
                        st.error("❌ Google Drive Service chưa được khởi tạo. Vui lòng cấu hình st.secrets.")
                    else:
                        with st.spinner("📤 Đang tải file lên Google Drive..."):
                            upload_bytes = st.session_state.processed_file if st.session_state.processed_file is not None else file_bytes
                            
                            folder_id = find_or_create_folder(service, target_folder, PARENT_FOLDER_ID)
                            if folder_id:
                                uploaded_gfile = upload_file_to_drive(service, upload_bytes, save_name, mime_type, folder_id)
                                if uploaded_gfile:
                                    st.success(f"🎉 Tải lên thành công! File ID: `{uploaded_gfile.get('id')}`")
                                    st.markdown(f"🔗 **Đường dẫn truy cập:** [{uploaded_gfile.get('webViewLink')}]({uploaded_gfile.get('webViewLink')})")
                                    st.session_state.show_upload_form = False
                                else:
                                    st.error("❌ Tải lên thất bại. Vui lòng kiểm tra lại file hoặc quyền truy cập.")
                            else:
                                st.error("❌ Không thể xác định thư mục lưu trữ.")
                                
        if GDRIVE_ENABLED and service is None:
            st.info("💡 Hướng dẫn cấu hình st.secrets nằm trong file README-v5.md.")

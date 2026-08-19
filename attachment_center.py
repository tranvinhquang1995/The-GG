import streamlit as st
import os
import io
import re
import tempfile
import subprocess
from PIL import Image
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- KHAI BÁO BẬT/TẮT TÍNH NĂNG GOOGLE DRIVE ---
# Bạn có thể đổi giá trị này thành True khi đã sẵn sàng kích hoạt lại tính năng upload Google Drive
GDRIVE_ENABLED = False

# --- HẰNG SỐ & ĐỊNH CẤU HÌNH ---
# ID thư mục mẹ trên Google Drive (Mọi thư mục con như 109, 110 sẽ được tạo ở đây)
PARENT_FOLDER_ID = st.secrets.get("gdrive", {}).get("parent_folder_id", "YOUR_GOOGLE_DRIVE_PARENT_FOLDER_ID")

# --- HÀM KHỞI TẠO GOOGLE DRIVE SERVICE ---
@st.cache_resource
def get_gdrive_service():
    """Khởi tạo Drive API Service sử dụng Google Service Account từ Secrets"""
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

# --- CÁC HÀM XỬ LÝ GOOGLE DRIVE ---
def find_or_create_folder(service, folder_name, parent_id):
    """Tìm thư mục con bằng tên dưới thư mục mẹ. Nếu chưa có thì tạo mới."""
    query = f"name = '{folder_name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    try:
        results = service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get("files", [])
        if items:
            return items[0]["id"]
        else:
            file_metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id]
            }
            folder = service.files().create(body=file_metadata, fields="id").execute()
            return folder.get("id")
    except Exception as e:
        st.error(f"❌ Lỗi tìm/tạo thư mục Drive: {e}")
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
        st.error(f"❌ Lỗi tải file lên Drive: {e}")
        return None

# --- CÁC HÀM NÉN HÌNH ẢNH & VIDEO (Sử dụng Ổ Đĩa Tạm Thời để bảo vệ 1GB RAM) ---
def compress_image(image_bytes, file_ext, target_size_mb=10.0):
    """Giảm chất lượng hình ảnh về dưới mức dung lượng mục tiêu (10MB) sử dụng Disk tạm thời để tiết kiệm RAM"""
    target_size_bytes = target_size_mb * 1024 * 1024
    if len(image_bytes) <= target_size_bytes:
        return image_bytes, False
        
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_in = os.path.join(temp_dir, f"input.{file_ext}")
        temp_out = os.path.join(temp_dir, f"output.jpg")
        
        with open(temp_in, "wb") as f:
            f.write(image_bytes)
            
        img = Image.open(temp_in)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
            
        quality = 85
        img.save(temp_out, format="JPEG", quality=quality)
        
        # Lặp giảm chất lượng ảnh
        while os.path.getsize(temp_out) > target_size_bytes and quality > 15:
            quality -= 10
            img.save(temp_out, format="JPEG", quality=quality)
            
        # Nếu vẫn quá lớn, thực hiện thay đổi độ phân giải (Resize)
        scale = 0.9
        while os.path.getsize(temp_out) > target_size_bytes and scale > 0.1:
            w, h = img.size
            new_size = (int(w * scale), int(h * scale))
            resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
            resized_img.save(temp_out, format="JPEG", quality=quality)
            scale -= 0.1
            
        with open(temp_out, "rb") as f:
            compressed_bytes = f.read()
            
        # Kiểm tra xem chất lượng có bị giảm quá sâu (> 90% dung lượng gốc)
        reduced_percent = (1 - (len(compressed_bytes) / len(image_bytes))) * 100
        is_low_quality = quality <= 20 or scale <= 0.4 or reduced_percent > 90
        
        return compressed_bytes, is_low_quality

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

def compress_video(video_bytes, file_ext, target_size_mb=10.0):
    """Nén video về dưới 10MB bằng cách tự động tính toán bitrate và dùng ffmpeg trên ổ đĩa tạm"""
    target_size_bytes = target_size_mb * 1024 * 1024
    if len(video_bytes) <= target_size_bytes:
        return video_bytes, False
        
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_in = os.path.join(temp_dir, f"input.{file_ext}")
        temp_out = os.path.join(temp_dir, f"output.mp4")
        
        with open(temp_in, "wb") as f:
            f.write(video_bytes)
            
        duration = get_video_duration(temp_in)
        if not duration:
            return video_bytes, False
            
        # Tính toán bitrate mục tiêu (90% dung lượng tối đa để dự phòng sai số âm thanh)
        target_size_bits = target_size_bytes * 8 * 0.9
        target_bitrate = int(target_size_bits / duration)
        
        if target_bitrate < 100000:
            target_bitrate = 100000
            
        # Sử dụng FFMPEG chuyển mã video
        cmd = [
            "ffmpeg", "-y", "-i", temp_in,
            "-b:v", str(target_bitrate),
            "-b:a", "128k",
            "-preset", "veryfast",
            temp_out
        ]
        
        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            with open(temp_out, "rb") as f:
                compressed_bytes = f.read()
                
            reduced_percent = (1 - (len(compressed_bytes) / len(video_bytes))) * 100
            is_low_quality = reduced_percent > 90
            return compressed_bytes, is_low_quality
        except Exception:
            return video_bytes, False

# --- HÀM CHÍNH ĐỂ HIỂN THỊ MÀN HÌNH CHỨC NĂNG ---
def show_attachment_center():
    st.markdown("<div class='main-title'>📎 Attachment Center</div>", unsafe_allow_html=True)
    st.markdown("##### Công cụ tối ưu hóa kích thước hình ảnh/video dành cho Tester (Đã khóa giao diện tối).")
    st.write("---")
    
    # CSS Khóa cứng giao diện tối và chân trang cố định
    st.markdown("""
    <style>
        /* CSS Khóa giao diện tối */
        #MainMenu {visibility: hidden;}
        
        .main-container-spacer {
            height: 100px;
        }
        
        .nobita-footer {
            position: fixed;
            left: 0;
            bottom: 0;
            width: 100%;
            background-color: #0E1117;
            border-top: 1px solid #30363D;
            color: #888888;
            text-align: center;
            padding: 10px 0;
            font-size: 13px;
            z-index: 999;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Khởi chạy Google Drive service nếu tính năng được bật
    service = None
    if GDRIVE_ENABLED:
        service = get_gdrive_service()
        
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
        file_ext = file_name.split(".")[-1].lower() if "." in file_name else "bin"
        
        st.info(f"📁 Tên file: **{file_name}** | Dung lượng gốc: **{file_size_mb:.2f} MB**")
        
        # Khởi tạo trạng thái xử lý trong Session State
        if "compressed_bytes" not in st.session_state:
            st.session_state.compressed_bytes = None
            st.session_state.is_compressed = False
            st.session_state.low_quality_alert = False
            st.session_state.upload_form_visible = False
            st.session_state.current_file_id = None
            
        col_act1, col_act2 = st.columns(2)
        
        with col_act1:
            # 1. TÍNH NĂNG NÉN COMPRESS
            if st.button("⚡ Compress (Nén tối ưu < 10MB)", type="primary", use_container_width=True):
                with st.spinner("⏳ Đang tiến hành xử lý nén tối ưu file..."):
                    if file_size_mb > 10.0:
                        if file_ext in ["png", "jpg", "jpeg"]:
                            comp_bytes, low_qual = compress_image(file_bytes, file_ext)
                            st.session_state.compressed_bytes = comp_bytes
                            st.session_state.is_compressed = True
                            st.session_state.low_quality_alert = low_qual
                        elif file_ext in ["mp4", "mov", "avi", "mkv"]:
                            comp_bytes, low_qual = compress_video(file_bytes, file_ext)
                            st.session_state.compressed_bytes = comp_bytes
                            st.session_state.is_compressed = True
                            st.session_state.low_quality_alert = low_qual
                        else:
                            st.warning("⚠️ Định dạng file chưa hỗ trợ nén tự động.")
                            st.session_state.compressed_bytes = file_bytes
                            st.session_state.is_compressed = False
                            st.session_state.low_quality_alert = False
                    else:
                        st.success("✅ File gốc đã hợp lệ (dưới 10MB), sẵn sàng cho tải về mà không nén!")
                        st.session_state.compressed_bytes = file_bytes
                        st.session_state.is_compressed = False
                        st.session_state.low_quality_alert = False
                        
            # Hiển thị nút tải xuống file nén nếu có
            if st.session_state.compressed_bytes is not None:
                comp_size_mb = len(st.session_state.compressed_bytes) / (1024 * 1024)
                st.success(f"📊 Dung lượng file sau xử lý: **{comp_size_mb:.2f} MB**")
                
                if st.session_state.low_quality_alert:
                    st.warning("⚠️ Cảnh báo: Chất lượng file bị giảm sâu (> 90%) để đạt dung lượng dưới 10MB!")
                    
                st.download_button(
                    label="📥 Tải file tạm thời",
                    data=st.session_state.compressed_bytes,
                    file_name=f"compressed_{file_name}" if st.session_state.is_compressed else file_name,
                    mime=mime_type,
                    use_container_width=True
                )
                
        with col_act2:
            # 2. TÍNH NĂNG TẢI LÊN GOOGLE DRIVE (Kiểm soát bởi flag)
            if not GDRIVE_ENABLED:
                st.button("☁️ Upload Google Drive [In-process]", disabled=True, use_container_width=True)
                st.caption("🔒 *Nút Upload hiện đang tạm khóa. Bạn chỉ cần sửa GDRIVE_ENABLED = True trong code để mở lại.*")
            else:
                if st.button("☁️ Upload Google Drive", use_container_width=True):
                    st.session_state.upload_form_visible = True
                    
        # Popup form hiển thị cấu hình chi tiết trước khi tải lên
        if GDRIVE_ENABLED and st.session_state.upload_form_visible:
            st.write("---")
            st.subheader("⚙️ Cấu hình Tải lên Google Drive")
            
            # Tự động bóc tách tên file gốc (109-B109-47.mp4 -> thư mục 109 và tên B109-47.mp4)
            match = re.match(r'^(\d+)[-_](.*)$', file_name)
            if match:
                suggested_folder = match.group(1)
                suggested_name = match.group(2)
            else:
                suggested_folder = "Chung"
                suggested_name = file_name
                
            with st.form("gdrive_upload_form"):
                folder_input = st.text_input("📁 Tên thư mục đích trên Drive (Ví dụ: 109):", value=suggested_folder)
                filename_input = st.text_input("📄 Tên file lưu trữ trên Drive:", value=suggested_name)
                submit_upload = st.form_submit_button("🚀 Xác nhận Tải lên Drive")
                
                if submit_upload:
                    with st.spinner("⏳ Đang tiến hành tải dữ liệu lên Google Drive..."):
                        # Liên kết thông minh: Ưu tiên lấy file nén nếu đã nhấn Compress trước, ngược lại lấy file gốc
                        final_bytes = st.session_state.compressed_bytes if st.session_state.compressed_bytes is not None else file_bytes
                        
                        if service is not None:
                            # 1. Tìm hoặc tạo thư mục con dưới thư mục mẹ
                            target_folder_id = find_or_create_folder(service, folder_input, PARENT_FOLDER_ID)
                            if target_folder_id:
                                # 2. Upload file lên Drive
                                uploaded_result = upload_file_to_drive(service, final_bytes, filename_input, mime_type, target_folder_id)
                                if uploaded_result:
                                    st.success(f"🎉 Tải lên thành công! File ID: `{uploaded_result.get('id')}`")
                                    link = uploaded_result.get("webViewLink")
                                    if link:
                                        st.link_button("🔗 Mở file trên Drive", link)
                            else:
                                st.error("❌ Không thể xác định hoặc khởi tạo thư mục đích trên Drive.")
                        else:
                            st.error("❌ Dịch vụ Google Drive chưa được kích hoạt. Hãy cấu hình Secrets.")
                            
    if GDRIVE_ENABLED and service is None:
        st.info("💡 Hướng dẫn cấu hình st.secrets nằm trong file README-v5.md.")
        
    st.markdown("<div class='main-container-spacer'></div>", unsafe_allow_html=True)
    st.markdown(
        """
        <div class='nobita-footer'>
            © 2026 Attachment Center. All Rights Reserved. Developed by <b>Nobita</b>
        </div>
        """, 
        unsafe_allow_html=True
    )

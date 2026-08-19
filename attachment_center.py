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
        st.error(f"❌ Lỗi khi tìm/tạo thư mục: {e}")
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
        st.error(f"❌ Lỗi khi upload file lên Google Drive: {e}")
        return None

# --- CÁC HÀM NÉN HÌNH ẢNH & VIDEO (Được tối ưu chạy Disk-based để tiết kiệm RAM) ---
def compress_image(image_bytes, file_ext, target_size_mb=10.0):
    """Giảm chất lượng hình ảnh về dưới mức dung lượng mục tiêu (10MB)"""
    target_size_bytes = target_size_mb * 1024 * 1024
    if len(image_bytes) <= target_size_bytes:
        return image_bytes, False
        
    try:
        # Sử dụng ổ đĩa tạm để xử lý (Disk-based) cứu RAM khỏi bị tràn khi làm việc với file lớn
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, f"temp_input{file_ext}")
            output_path = os.path.join(temp_dir, f"temp_output{file_ext}")
            
            with open(input_path, "wb") as f:
                f.write(image_bytes)
                
            img = Image.open(input_path)
            
            # Chuyển đổi mode nếu lưu sang JPG
            if img.mode in ("RGBA", "P") and file_ext.lower() in [".jpg", ".jpeg"]:
                img = img.convert("RGB")
                
            quality = 95
            img.save(output_path, quality=quality)
            
            while os.path.getsize(output_path) > target_size_bytes and quality > 10:
                quality -= 5
                img.save(output_path, quality=quality)
                
            # Nếu vẫn quá dung lượng thì resize giảm độ phân giải dần
            scale = 0.9
            while os.path.getsize(output_path) > target_size_bytes and scale > 0.2:
                width, height = img.size
                new_size = (int(width * scale), int(height * scale))
                resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
                resized_img.save(output_path, quality=quality)
                scale -= 0.1
                
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
        # Sử dụng ổ đĩa tạm để nén video bằng ffmpeg (Disk-based) cứu RAM khỏi bị tràn
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = os.path.join(temp_dir, "input.mp4")
            output_path = os.path.join(temp_dir, "output.mp4")
            
            with open(input_path, "wb") as f:
                f.write(video_bytes)
                
            duration = get_video_duration(input_path)
            if not duration:
                return video_bytes, False
                
            # Tính toán target bitrate
            target_bitrate = int((target_size_mb * 8 * 1024 * 1024) / duration) - 128000
            if target_bitrate < 100000:
                target_bitrate = 100000
                
            cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-b:v", f"{target_bitrate}",
                "-maxrate", f"{target_bitrate * 2}",
                "-bufsize", f"{target_bitrate}",
                "-preset", "veryfast",
                "-c:a", "aac", "-b:a", "128k",
                output_path
            ]
            
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            
            with open(output_path, "rb") as f:
                compressed_bytes = f.read()
                
            return compressed_bytes, True
    except Exception as e:
        st.error(f"❌ Lỗi khi nén video: {e}")
        return video_bytes, False


# --- GIAO DIỆN CHÍNH (Được gọi từ app chính) ---
def show_attachment_center():
    # CSS riêng để khóa giao diện tối và định dạng footer
    st.markdown("""
    <style>
        .tool-box {
            background-color: #161B22;
            padding: 25px;
            border-radius: 10px;
            border: 1px solid #30363D;
            margin-top: 15px;
        }
        .main-container-spacer {
            height: 100px;
        }
        .nobita-footer {
            text-align: center;
            color: #888888;
            font-size: 13px;
            margin-top: 50px;
            padding: 20px;
            border-top: 1px solid #222;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<div class='main-title'>📁 Attachment Center (v5)</div>", unsafe_allow_html=True)
    st.markdown("Công cụ tối ưu hóa kích thước hình ảnh/video dành cho Tester.")
    st.write("---")

    # Khởi tạo Service Google Drive
    service = None
    if GDRIVE_ENABLED:
        service = get_gdrive_service()
        if service is None:
            st.warning("⚠️ Chế độ Drive được bật nhưng không thể khởi tạo Service. Hãy kiểm tra secrets.")
            
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

        # Quản lý trạng thái nén trong session state để liên kết thông minh
        if "current_file" not in st.session_state or st.session_state.current_file != file_name:
            st.session_state.current_file = file_name
            st.session_state.compressed_bytes = None
            st.session_state.is_compressed = False
            st.session_state.compression_ratio = 0.0
            st.session_state.show_upload_form = False

        st.info(f"📄 **Thông tin file:** `{file_name}` | Dung lượng gốc: `{file_size_mb:.2f} MB` | Loại file: `{mime_type}`")

        # Nút nén và tải lên riêng biệt theo đúng yêu cầu
        col1, col2 = st.columns(2)

        # 1. Xử lý nút COMPRESS
        with col1:
            if st.button("⚡ Compress (Nén file tạm)", use_container_width=True, type="primary"):
                if file_size_mb <= 10.0:
                    st.success("✅ File gốc hợp lệ (< 10MB) và sẵn sàng để tải về!")
                    st.session_state.compressed_bytes = file_bytes
                    st.session_state.is_compressed = True
                    st.session_state.compression_ratio = 0.0
                else:
                    st.info("🔄 Đang tiến hành nén file về dưới 10MB...")
                    _, ext = os.path.splitext(file_name)
                    
                    if ext.lower() in [".png", ".jpg", ".jpeg"]:
                        comp_bytes, success = compress_image(file_bytes, ext)
                    elif ext.lower() in [".mp4", ".mov", ".avi", ".mkv"]:
                        comp_bytes, success = compress_video(file_bytes)
                    else:
                        comp_bytes, success = file_bytes, False
                        st.error("❌ Định dạng file không được hỗ trợ nén!")

                    if success:
                        st.session_state.compressed_bytes = comp_bytes
                        st.session_state.is_compressed = True
                        ratio = (1 - len(comp_bytes) / len(file_bytes)) * 100
                        st.session_state.compression_ratio = ratio
                        st.success(f"🎉 Nén thành công! Dung lượng mới: `{len(comp_bytes)/(1024*1024):.2f} MB` (Giảm {ratio:.1f}%)")
                    else:
                        st.error("❌ Nén thất bại hoặc file không thể tối ưu thêm. Đã sử dụng file gốc.")
                        st.session_state.compressed_bytes = file_bytes
                        st.session_state.is_compressed = False

            # Hiển thị nút tải file tạm thời sau khi nén
            if st.session_state.is_compressed and st.session_state.compressed_bytes is not None:
                if st.session_state.compression_ratio > 90.0:
                    st.warning("⚠️ Cảnh báo: Chất lượng hình ảnh/video bị giảm sâu (> 90%) do dung lượng file gốc quá lớn.")
                
                st.download_button(
                    label="📥 Tải file tạm thời",
                    data=st.session_state.compressed_bytes,
                    file_name=f"compressed_{file_name}",
                    mime=mime_type,
                    use_container_width=True
                )

        # 2. Xử lý nút UPLOAD (Tải lên Drive)
        with col2:
            if not GDRIVE_ENABLED:
                st.button("☁️ Upload to Google Drive [In-process]", disabled=True, use_container_width=True)
                st.caption("🔒 *Tính năng tải lên Drive hiện đang tạm khóa để bảo trì hệ thống API.*")
            else:
                if st.button("☁️ Upload to Google Drive", use_container_width=True):
                    st.session_state.show_upload_form = True

        # Giao diện Popup Form xuất hiện phía dưới khi bấm Upload
        if GDRIVE_ENABLED and st.session_state.show_upload_form:
            st.markdown("---")
            st.subheader("📝 Xác nhận cấu hình tải lên")
            
            # Nhận diện thư mục thông minh dựa trên tên file gốc (Ví dụ: 109-B109-47.mp4 -> Thư mục 109 và Tên B109-47.mp4)
            default_folder = ""
            default_filename = file_name
            match = re.match(r'^([^-]+)-(.*)$', file_name)
            if match:
                default_folder = match.group(1).strip()
                default_filename = match.group(2).strip()

            with st.form("upload_drive_form"):
                folder_input = st.text_input("📁 Tên thư mục đích trên Drive:", value=default_folder)
                filename_input = st.text_input("📄 Tên file lưu trên Drive:", value=default_filename)
                
                # Hiển thị ghi chú nguồn dữ liệu nào sẽ được tải lên
                if st.session_state.is_compressed:
                    st.info("💡 **Liên kết thông minh:** Hệ thống sẽ tự động lấy file **đã nén** (< 10MB) để tải lên Drive.")
                else:
                    st.info("💡 **Liên kết thông minh:** Hệ thống sẽ tự động lấy file **gốc** chưa nén để tải lên Drive.")

                submit_btn = st.form_submit_button("🚀 Xác nhận tải lên Google Drive", use_container_width=True)
                
                if submit_btn:
                    if not folder_input or not filename_input:
                        st.error("❌ Vui lòng điền đầy đủ thông tin Thư mục và Tên file!")
                    else:
                        st.info("🔄 Đang tiến hành kết nối và tải file lên Drive...")
                        
                        # Quyết định lấy bytes nén hay bytes gốc dựa theo cơ chế liên kết thông minh
                        bytes_to_upload = st.session_state.compressed_bytes if st.session_state.is_compressed else file_bytes
                        
                        folder_id = find_or_create_folder(service, folder_input, PARENT_FOLDER_ID)
                        if folder_id:
                            result = upload_file_to_drive(service, bytes_to_upload, filename_input, mime_type, folder_id)
                            if result:
                                st.success(f"🎉 Tải lên Google Drive thành công! File ID: `{result.get('id')}`")
                                st.markdown(f"🔗 [Mở file trên Drive]({result.get('webViewLink')})")
                                st.balloons()
                                st.session_state.show_upload_form = False
                            else:
                                st.error("❌ Không thể tải file lên Drive.")
                        else:
                            st.error("❌ Không tìm thấy hoặc không thể tạo thư mục đích.")

    # Thêm thẻ khoảng trống để không bị footer đè lên
    st.markdown("<div class='main-container-spacer'></div>", unsafe_allow_html=True)
    
    # --- CHÂN TRANG BẢN QUYỀN (FOOTER) ---
    st.markdown("""
    <div class='nobita-footer'>
        © 2026 Attachment Center. All Rights Reserved. Developed by <b>Nobita</b>
    </div>
    """, unsafe_allow_html=True)

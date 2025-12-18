from flask import Flask, render_template, request, send_file
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
import io
import base64
from datetime import datetime
import os
import math
import hashlib

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# ข้อมูลสาขา
BRANCHES = {
    'M015': 'M015 แม็กแวลู่ สุขาภิบาล 1',
    'M487': 'M487 โลตัส สุขาภิบาล 1',
    'M571': 'M571 โลตัส นวลจันทร์'
}

WORK_TYPES = [
    'ตรวจสอบระบบน้ำไฟและแอร์ เรียบร้อยค่ะ',
    'ทำความสะอาดร่องน้ำเรียบร้อยค่ะ',
    'ตรวจสอบอุณหภูมิตู้เย็นรอบปิดร้านเรียบร้อยค่ะ',
    'ทำความสะอาดบ่อดักไขมันเรียบร้อยค่ะ',
    'ซีลประตูหน้าร้านเรียบร้อยค่ะ',
    'คลุมหุ่นยนต์เรียบร้อยค่ะ',
    'เปิด App Food เรียบร้อยค่ะ',
    'ตรวจความพร้อมอุปกรณ์ เรียบร้อยค่ะ',
    'Tablet 9 เครื่องครบค่ะ'
]

# ขนาดกระดาษ A4 (pixel at 300 DPI)
A4_WIDTH_PX = 2480  # 210mm
A4_HEIGHT_PX = 3508  # 297mm

def get_thai_font(size):
    """โหลดฟอนต์ภาษาไทยจากโฟลเดอร์ fonts"""
    font_paths = [
        'fonts/THSarabunNew Bold.ttf',
        'fonts/THSarabunNew.ttf',
        'fonts/THSarabunNew Bolditalic.ttf',
        'Sarabun-Bold.ttf',
        'THSarabunNew Bold.ttf',
        'THSarabunNew.ttf'
    ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue

    # ลองใช้ฟอนต์ระบบ
    system_fonts = [
        "C:/Windows/Fonts/THSarabunNew Bold.ttf",
        "C:/Windows/Fonts/THSarabunNew.ttf",
        "/System/Library/Fonts/Thonburi.ttc",
        "/usr/share/fonts/truetype/tlwg/Garuda-Bold.ttf"
    ]

    for font_path in system_fonts:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue

    print("⚠️ ไม่พบฟอนต์ภาษาไทย ใช้ฟอนต์เริ่มต้น")
    return ImageFont.load_default()

def _open_image_from_bytes(img_data: bytes) -> Image.Image:
    """
    เปิดรูปจาก bytes ให้ปลอดภัย:
    - ตรวจว่าเป็นรูปจริง (verify)
    - เปิดใหม่อีกครั้งเพื่อใช้งานต่อ (เพราะ verify ทำให้ไฟล์ pointer เปลี่ยน)
    """
    if not img_data:
        raise UnidentifiedImageError("Empty image bytes")

    bio = io.BytesIO(img_data)
    img = Image.open(bio)
    img.verify()

    bio2 = io.BytesIO(img_data)
    img2 = Image.open(bio2)

    # ป้องกันบางไฟล์มีโหมดแปลก ๆ
    return img2.convert("RGB")

def calculate_optimal_layout(num_images):
    """
    คำนวณ layout ที่เหมาะสมที่สุด (สูงสุด 3 แถว, ขยายเต็มพื้นที่ 100%)
    """
    if num_images <= 0:
        return 1, 1, 800
    
    spacing = 8  # ระยะห่างระหว่างรูปน้อยมาก
    
    # กรณีพิเศษ: 1-3 รูป → 1 แถว (ขยายเต็มความกว้าง 100%)
    if num_images <= 3:
        available_width = A4_WIDTH_PX - ((num_images - 1) * spacing)
        img_size = available_width // num_images
        return num_images, 1, img_size
    
    # กรณีพิเศษ: 4 รูป → 2x2
    if num_images == 4:
        available_width = A4_WIDTH_PX - spacing
        img_size = available_width // 2
        return 2, 2, img_size
    
    # กรณีพิเศษ: 5 รูป → 3 + 2
    if num_images == 5:
        available_width = A4_WIDTH_PX - (2 * spacing)
        img_size = available_width // 3
        return 3, 2, img_size
    
    # สำหรับ 6 รูปขึ้นไป: แบ่งเป็น 2 หรือ 3 แถว (ขยายเต็มพื้นที่)
    if num_images <= 9:
        cols = math.ceil(num_images / 3)
        rows = min(3, math.ceil(num_images / cols))
        available_width = A4_WIDTH_PX - ((cols - 1) * spacing)
        img_size = available_width // cols
        return cols, rows, img_size
    
    # มากกว่า 9 รูป: กระจายให้เท่ากันใน 3 แถว
    cols = math.ceil(num_images / 3)
    rows = 3
    available_width = A4_WIDTH_PX - ((cols - 1) * spacing)
    img_size = available_width // cols
    
    return cols, rows, img_size

def create_report_image(images_data, branch, date, work_description):
    """สร้างภาพรายงานแบบทางการ (แก้ไข: ไม่มีช่องว่างข้างและล่างรูป, จำกัด 3 แถว)"""
    num_images = len(images_data)
    
    # คำนวณ layout อัตโนมัติ
    cols, rows, img_size = calculate_optimal_layout(num_images)
    
    # Header (ไม่มี footer)
    header_height = 280
    margin_top = 60
    margin_bottom = 40  # ลดช่องว่างล่างลง
    margin_side = 40     # ลดช่องว่างข้างลง
    spacing = 15         # ระยะห่างระหว่างรูป
    
    # คำนวณความสูงของพื้นที่รูปภาพ
    images_area_height = rows * img_size + (rows - 1) * spacing
    
    # ขนาด canvas ที่พอดี
    canvas_width = A4_WIDTH_PX
    canvas_height = margin_top + header_height + images_area_height + margin_bottom
    
    # สร้าง canvas พื้นหลังสีขาว
    canvas = Image.new('RGB', (canvas_width, canvas_height), color='white')
    draw = ImageDraw.Draw(canvas)
    
    # โหลดฟอนต์ภาษาไทย
    title_font = get_thai_font(100)
    date_font = get_thai_font(75)
    desc_font = get_thai_font(70)
    
    y_offset = margin_top
    
    # สาขา - สีดำ
    branch_text = BRANCHES.get(branch, branch)
    bbox = draw.textbbox((0, 0), branch_text, font=title_font)
    text_width = bbox[2] - bbox[0]
    text_x = (canvas_width - text_width) // 2
    draw.text((text_x, y_offset), branch_text, fill=(0, 0, 0), font=title_font)
    y_offset += bbox[3] - bbox[1] + 25
    
    # วันที่ (วัน/เดือน/ปี พ.ศ. แบบย่อ)
    date_parts = date.split('-')
    year_be_short = (int(date_parts[0]) + 543) % 100
    thai_date = f"วันที่ {date_parts[2]}/{date_parts[1]}/{year_be_short:02d}"
    
    bbox = draw.textbbox((0, 0), thai_date, font=date_font)
    text_width = bbox[2] - bbox[0]
    text_x = (canvas_width - text_width) // 2
    draw.text((text_x, y_offset), thai_date, fill=(60, 60, 60), font=date_font)
    y_offset += bbox[3] - bbox[1] + 20
    
    # รายละเอียดงาน
    bbox = draw.textbbox((0, 0), work_description, font=desc_font)
    text_width = bbox[2] - bbox[0]
    text_x = (canvas_width - text_width) // 2
    draw.text((text_x, y_offset), work_description, fill=(80, 80, 80), font=desc_font)
    y_offset += bbox[3] - bbox[1] + 35
    
    # วางรูปภาพ (ไม่มีช่องว่างข้าง)
    y_start = y_offset
    
    for idx, img_data in enumerate(images_data):
        row = idx // cols
        col = idx % cols
        
        # คำนวณจำนวนรูปในแถวนี้
        items_in_this_row = min(cols, num_images - row * cols)
        
        # คำนวณความกว้างรวมของแถวนี้
        row_width = items_in_this_row * img_size + (items_in_this_row - 1) * spacing
        
        # จัดกึ่งกลาง
        start_x = (canvas_width - row_width) // 2
        
        x = start_x + col * (img_size + spacing)
        y = y_start + row * (img_size + spacing)
        
        # โหลดและปรับขนาดรูปภาพ (ปลอดภัย)
        try:
            img = _open_image_from_bytes(img_data)
        except UnidentifiedImageError:
            raise UnidentifiedImageError("พบไฟล์ที่ไม่ใช่รูปภาพ/ไฟล์เสีย กรุณาลองเลือกไฟล์รูปใหม่ (JPG/PNG)")
        
        img_width, img_height = img.size
        aspect_ratio = img_width / img_height if img_height else 1.0
        
        # ครอปให้เป็นสี่เหลี่ยมจัตุรัส
        if aspect_ratio < 0.7:  # ภาพแนวตั้งมาก
            if img_width < img_height:
                top = (img_height - img_width) // 2
                img = img.crop((0, top, img_width, top + img_width))
            else:
                left = (img_width - img_height) // 2
                img = img.crop((left, 0, left + img_height, img_height))
        elif aspect_ratio > 1.5:  # ภาพแนวนอนมาก
            if img_width > img_height:
                left = (img_width - img_height) // 2
                img = img.crop((left, 0, left + img_height, img_height))
            else:
                top = (img_height - img_width) // 2
                img = img.crop((0, top, img_width, top + img_width))
        else:
            min_side = min(img_width, img_height)
            left = (img_width - min_side) // 2
            top = (img_height - min_side) // 2
            img = img.crop((left, top, left + min_side, top + min_side))
        
        img = img.resize((img_size, img_size), Image.Resampling.LANCZOS)
        canvas.paste(img, (x, y))
    
    return canvas

def _collect_unique_images(files):
    """
    อ่านไฟล์รูปจาก request.files โดย:
    - อ่าน bytes แค่ครั้งเดียว
    - ตัดไฟล์ซ้ำด้วย md5
    - ข้ามไฟล์ว่าง
    """
    images_data = []
    seen = set()

    for f in files:
        if not f or not f.filename:
            continue

        data = f.read()  # ✅ อ่านครั้งเดียว
        if not data:
            continue

        h = hashlib.md5(data).hexdigest()
        if h in seen:
            continue

        seen.add(h)
        images_data.append(data)

    return images_data

@app.route('/')
def index():
    return render_template('index.html', branches=BRANCHES, work_types=WORK_TYPES)

@app.route('/generate', methods=['POST'])
def generate():
    try:
        branch = request.form.get('branch')
        date = request.form.get('date')
        work_description = request.form.get('work_description')

        files = request.files.getlist('images')
        images_data = _collect_unique_images(files)

        if not images_data:
            return "กรุณาอัพโหลดรูปภาพอย่างน้อย 1 รูป", 400

        report_image = create_report_image(images_data, branch, date, work_description)

        img_io = io.BytesIO()
        report_image.save(img_io, 'PNG', quality=95, dpi=(300, 300))
        img_io.seek(0)

        filename = f"รายงาน_{branch}_{date}.png"
        return send_file(
            img_io,
            mimetype='image/png',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        return f"เกิดข้อผิดพลาด: {str(e)}", 500

@app.route('/preview', methods=['POST'])
def preview():
    try:
        branch = request.form.get('branch')
        date = request.form.get('date')
        work_description = request.form.get('work_description')

        files = request.files.getlist('images')
        images_data = _collect_unique_images(files)

        if not images_data:
            return {"error": "กรุณาอัพโหลดรูปภาพอย่างน้อย 1 รูป"}, 400

        report_image = create_report_image(images_data, branch, date, work_description)

        img_io = io.BytesIO()
        report_image.save(img_io, 'PNG', quality=85)
        img_io.seek(0)
        img_base64 = base64.b64encode(img_io.getvalue()).decode()

        return {"preview": f"data:image/png;base64,{img_base64}"}

    except Exception as e:
        return {"error": str(e)}, 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
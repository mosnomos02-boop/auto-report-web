from flask import Flask, render_template, request, send_file
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io
import os
import uuid
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "THSarabunNew.ttf")

app = Flask(__name__)

# กัน 413 (ปรับได้ เช่น 64MB, 100MB)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024  # 64MB


# =========================
#  ตั้งค่า dropdown
# =========================
BRANCH_OPTIONS = [
    "M015 แม็กแวลู่ สุขาภิบาล 1",
    "M487 โลตัส สุขาภิบาล 1",
    "M571 โลตัส นวลจันทร์",
]

DETAIL_PRESETS = [
    "เปิด App Food เรียบร้อยค่ะ",
    "ตรวจความพร้อมอุปกรณ์ เรียบร้อยค่ะ",
    "ทำความสะอาดร่องน้ำเรียบร้อยค่ะ",
    "ทำความสะอาดบ่อดักไขมันเรียบร้อยค่ะ",
    "ตรวจสอบอุณหภูมิตู้เย็นรอบปิดร้านเรียบร้อยค่ะ",
    "ตรวจสอบระบบน้ำไฟและแอร์ เรียบร้อยค่ะ",
    "ซีลประตูหน้าร้านเรียบร้อยค่ะ",
    "คลุมหุ่นยนต์เรียบร้อยค่ะ",
    "Tablet 9 เครื่องครบค่ะ",
]


# =========================
#  Layout เลือกตามจำนวนรูปที่ใช้บ่อย
#  แต่ถ้า n อื่น ๆ จะคำนวณอัตโนมัติ
# =========================
LAYOUT_MAP = {
    1: (1, 1),
    2: (1, 2),
    3: (1, 3),
    4: (2, 2),
    5: (2, 3),
    6: (2, 3),
    7: (3, 3),
    8: (2, 4),
    9: (3, 3),
    10: (3, 4),
    12: (3, 4),
    15: (3, 5),
    18: (3, 6),
}

def pick_layout(n: int):
    """เลือก rows/cols ให้ดูลงตัว และรองรับ n ทุกจำนวน"""
    if n in LAYOUT_MAP:
        return LAYOUT_MAP[n]

    # heuristic: เลือก cols ตามช่วงจำนวนรูป
    if n <= 3:
        cols = n
    elif n <= 6:
        cols = 3
    elif n <= 8:
        cols = 4
    elif n <= 12:
        cols = 4
    elif n <= 18:
        cols = 6
    else:
        cols = 6

    rows = (n + cols - 1) // cols
    return rows, cols


def safe_open_image(file_storage) -> Image.Image:
    """
    เปิดรูปให้ปลอดภัย:
    - แก้รูปเอียง/กลับหัวตาม EXIF
    - แปลงเป็น RGB
    - บีบอัด/ย่อเพื่อกันไฟล์ใหญ่มาก (ลดโอกาส 413 + เร็วขึ้น)
    """
    img = Image.open(file_storage)
    img = ImageOps.exif_transpose(img)  # สำคัญ: แก้หมุนตามที่ถ่ายจริง
    img = img.convert("RGB")

    # จำกัดขนาดด้านยาวสุด (ปรับได้)
    max_side = 2200
    w, h = img.size
    if max(w, h) > max_side:
        scale = max_side / float(max(w, h))
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    return img


def contain_resize(img: Image.Image, target_w: int, target_h: int, bg=(255, 255, 255)) -> Image.Image:
    """
    ย่อ/ขยายแบบ CONTAIN (ไม่ตัดรูป ไม่บิด)
    ถ้าสัดส่วนไม่พอดี จะเติมพื้นหลังให้เต็มช่อง
    """
    iw, ih = img.size
    scale = min(target_w / iw, target_h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    resized = img.resize((nw, nh), Image.LANCZOS)

    canvas = Image.new("RGB", (target_w, target_h), bg)
    x = (target_w - nw) // 2
    y = (target_h - nh) // 2
    canvas.paste(resized, (x, y))
    return canvas


def draw_center_text(draw: ImageDraw.ImageDraw, text: str, y: int, font: ImageFont.ImageFont, canvas_w: int, fill=(20, 20, 20)):
    text = (text or "").strip()
    if not text:
        return y
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (canvas_w - tw) // 2
    draw.text((x, y), text, fill=fill, font=font)
    return y + th + 8


@app.errorhandler(413)
def too_large(e):
    return "ไฟล์รูปใหญ่เกินไป (413). ลองลดจำนวนรูป/ลดขนาดไฟล์ก่อนอัปโหลดนะครับ", 413


@app.route("/")
def index():
    return render_template(
        "index.html",
        branches=BRANCH_OPTIONS,
        presets=DETAIL_PRESETS
    )


@app.route("/generate", methods=["POST"])
def generate():
    # รับค่าจากฟอร์ม
    branch = (request.form.get("branch") or "").strip()
    date = (request.form.get("date") or "").strip()
    detail = (request.form.get("detail") or "").strip()

    files = request.files.getlist("images")
    if not files or len(files) == 0:
        return "ยังไม่ได้เลือกรูป", 400

    # เปิดรูป + แก้ EXIF + ย่อ
    imgs = [safe_open_image(f) for f in files]
    n = len(imgs)

    # เลือก layout
    rows, cols = pick_layout(n)

    # =========================
    #  ตั้งค่า canvas / ช่องรูป
    # =========================
    pad = 14                 # ช่องว่างระหว่างรูป
    outer = 18               # ขอบรอบนอก
    cell_w, cell_h = 420, 420

    # Header สูงแบบพอดี ไม่ให้กินพื้นที่มาก
    header_pad_top = 18
    header_pad_bottom = 14

    # ฟอนต์
    try:
        font_title = ImageFont.truetype(FONT_PATH, 76)
        font_date  = ImageFont.truetype(FONT_PATH, 56)
        font_body  = ImageFont.truetype(FONT_PATH, 58)
    except OSError:
        return f"เปิดฟอนต์ไม่ได้ ตรวจไฟล์: {FONT_PATH}", 500

    # กะความสูงหัวข้อจากข้อความจริง
    tmp = Image.new("RGB", (10, 10), "white")
    dtmp = ImageDraw.Draw(tmp)

    def text_h(text, font):
        if not (text or "").strip():
            return 0
        b = dtmp.textbbox((0, 0), text, font=font)
        return (b[3] - b[1]) + 8

    h_title = text_h(branch, font_title)
    h_date = text_h(date, font_date)
    h_detail = text_h(detail, font_body)

    header_h = header_pad_top + h_title + h_date + h_detail + header_pad_bottom

    canvas_w = outer * 2 + cols * cell_w + (cols - 1) * pad
    canvas_h = outer * 2 + header_h + rows * cell_h + (rows - 1) * pad

    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
    draw = ImageDraw.Draw(canvas)

    # วาดหัวข้อ
    y = outer + header_pad_top
    y = draw_center_text(draw, branch, y, font_title, canvas_w)
    y = draw_center_text(draw, date, y + 2, font_date, canvas_w)
    y = draw_center_text(draw, detail, y + 6, font_body, canvas_w)

    # จุดเริ่มวางรูป
    grid_top = outer + header_h

    # =========================
    #  วางรูปแบบ "จัดกึ่งกลางทุกกรณี"
    #  - แถวเต็ม: เริ่มจากซ้ายปกติ
    #  - แถวสุดท้ายที่ไม่เต็ม: คำนวณ offset ให้กึ่งกลาง
    # =========================
    for i, img in enumerate(imgs):
        r = i // cols
        c = i % cols

        if r >= rows:
            break

        # จำนวนรูปในแถวนี้
        start_i = r * cols
        end_i = min(start_i + cols, n)
        items_in_row = end_i - start_i

        # ถ้าแถวนี้ไม่เต็ม (มักเป็นแถวสุดท้าย) -> center
        row_width = items_in_row * cell_w + (items_in_row - 1) * pad
        full_row_width = cols * cell_w + (cols - 1) * pad

        if items_in_row < cols:
            # ใช้ c ตาม index ในแถว (0..items_in_row-1)
            c_in_row = i - start_i
            x_start = outer + (full_row_width - row_width) // 2
            x0 = x_start + c_in_row * (cell_w + pad)
        else:
            x0 = outer + c * (cell_w + pad)

        y0 = grid_top + r * (cell_h + pad)

        tile = contain_resize(img, cell_w, cell_h, bg=(255, 255, 255))
        canvas.paste(tile, (x0, y0))

    # ชื่อไฟล์สุ่มกันซ้ำ
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = f"report_{stamp}_{uuid.uuid4().hex[:8]}.jpg"

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=92, optimize=True)
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg", as_attachment=True, download_name=out_name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

from flask import Flask, render_template, request, send_file
from PIL import Image, ImageDraw, ImageFont
import io
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "THSarabunNew.ttf")


app = Flask(__name__)



# เลือก layout ให้เหมาะกับจำนวนรูปที่คุณใช้บ่อย
LAYOUT_MAP = {
    2:  (1, 2),
    3:  (1, 3),
    4:  (2, 2),
    6:  (2, 3),
    8:  (2, 4),
    18: (3, 6),
}

def cover_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """ย่อ/ขยายแบบ Cover แล้วครอปให้พอดีช่อง (ไม่บิด ไม่ยืด)"""
    img_w, img_h = img.size
    scale = max(target_w / img_w, target_h / img_h)
    new_w, new_h = int(img_w * scale), int(img_h * scale)
    img2 = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img2.crop((left, top, left + target_w, top + target_h))

def pick_layout(n: int, mode: str):
    """เลือกจำนวนแถว/คอลัมน์ตามจำนวนรูป (หรือเลือกจาก dropdown)"""
    n_for_layout = n
    if mode and mode != "auto":
        try:
            n_for_layout = int(mode)
        except:
            n_for_layout = n

    if n_for_layout in LAYOUT_MAP:
        return LAYOUT_MAP[n_for_layout]

    # fallback: ถ้าเจอจำนวนอื่น ให้ใช้ 3 คอลัมน์เป็นหลัก
    cols = 3
    rows = (n + cols - 1) // cols
    return (rows, cols)

def draw_center_text(draw: ImageDraw.ImageDraw, text: str, y: int, font: ImageFont.ImageFont, canvas_w: int):
    """วาดข้อความกึ่งกลางแนวนอน"""
    text = (text or "").strip()
    if not text:
        return y
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (canvas_w - text_w) // 2
    draw.text((x, y), text, fill="black", font=font)
    return y + text_h + 8

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate():
    title = request.form.get("title", "").strip()
    date = request.form.get("date", "").strip()
    detail = request.form.get("detail", "").strip()
    mode = request.form.get("count_mode", "auto")

    files = request.files.getlist("images")
    imgs = [Image.open(f).convert("RGB") for f in files]
    n = len(imgs)
    if n == 0:
        return "ยังไม่ได้เลือกรูป", 400

    rows, cols = pick_layout(n, mode)

    # ===== ปรับขนาดหน้า/ช่องรูป =====
    cell_w, cell_h = 420, 420   # ขนาดช่องรูป
    pad = 14                    # ระยะขอบ/ช่องว่าง
    top_h = 260                 # พื้นที่หัวข้อด้านบน (เพิ่มแล้ว)

    canvas_w = cols * cell_w + (cols + 1) * pad
    canvas_h = top_h + rows * cell_h + (rows + 1) * pad
    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
    draw = ImageDraw.Draw(canvas)

    # ===== ฟอนต์ไทยชัด ๆ =====
    # ถ้าขึ้น error OSError cannot open resource -> ตรวจชื่อไฟล์/ตำแหน่ง FONT_PATH
    font_title = ImageFont.truetype(FONT_PATH, 72)  # หัวเรื่อง
    font_date  = ImageFont.truetype(FONT_PATH, 54)  # วันที่
    font_body  = ImageFont.truetype(FONT_PATH, 58)  # รายละเอียดงาน

    # ===== หัวข้อ 3 บรรทัด กึ่งกลาง =====
    y = 18
    y = draw_center_text(draw, title, y, font_title, canvas_w)
    y = draw_center_text(draw, date, y, font_date, canvas_w)
    y = draw_center_text(draw, detail, y + 6, font_body, canvas_w)

    # ===== วางรูปแบบ cover crop =====
    for i, img in enumerate(imgs):
        r = i // cols
        c = i % cols
        if r >= rows:
            break

        x0 = pad + c * (cell_w + pad)
        y0 = top_h + pad + r * (cell_h + pad)

        tile = cover_resize(img, cell_w, cell_h)
        canvas.paste(tile, (x0, y0))

    # ===== ส่งออกเป็น JPG ไฟล์เดียว =====
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=92)
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg", as_attachment=True, download_name="report.jpg")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

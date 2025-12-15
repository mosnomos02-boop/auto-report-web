from flask import Flask, render_template, request, send_file
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io
import os
import uuid

app = Flask(__name__)

# ===== ฟอนต์ไทยในโปรเจกต์ =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "THSarabunNew.ttf")


# ------------------------------
# Helpers
# ------------------------------
def draw_center_text(draw, text, y, font, canvas_w):
    text = (text or "").strip()
    if not text:
        return y
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (canvas_w - text_w) // 2
    draw.text((x, y), text, fill="black", font=font)
    return y + text_h + 6


def cover_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """
    เต็มช่อง ไม่มีขอบขาว (อาจครอปขอบเล็กน้อย) เหมือนแอปคอลลาจ
    """
    return ImageOps.fit(img, (target_w, target_h), method=Image.LANCZOS, centering=(0.5, 0.5))


def paste_tile(canvas, img, x, y, w, h):
    tile = cover_resize(img, w, h)
    canvas.paste(tile, (x, y))


def pick_grid(n: int):
    """
    fallback grid สำหรับจำนวนรูปอื่น ๆ
    """
    if n <= 2:
        return 1, 2
    if n == 3:
        return 1, 3
    if n == 4:
        return 2, 2
    if n == 6:
        return 2, 3
    if n == 8:
        return 2, 4
    if n == 18:
        return 3, 6
    cols = 3
    rows = (n + cols - 1) // cols
    return rows, cols


def compose_hero_layout_landscape(canvas_w, header_safe_h, pad, n):
    """
    Layout แนวนอน (เหมาะกับรูปเยอะ)
    17 รูป: top 4 / mid (3 + hero + 3) / bottom 6
    18 รูป: top 5 / mid (3 + hero + 3) / bottom 6
    """
    top_cols = 4 if n == 17 else 5

    top_strip_h = 180
    hero_h = 460
    bottom_strip_h = 200

    canvas_h = header_safe_h + pad + top_strip_h + pad + hero_h + pad + bottom_strip_h + pad
    canvas = Image.new("RGB", (canvas_w, canvas_h), "white")
    return canvas, top_cols, top_strip_h, hero_h, bottom_strip_h


# ------------------------------
# Routes
# ------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    branch = (request.form.get("branch") or "").strip()
    date = (request.form.get("date") or "").strip()
    detail = (request.form.get("detail") or "").strip()

    # เลือกรูปเด่น (1-based index)
    try:
        center_index = int(request.form.get("center_index", "1"))
    except:
        center_index = 1

    files = request.files.getlist("images")
    if not files:
        return "ยังไม่ได้เลือกรูป", 400

    # โหลดรูป + หมุนตาม EXIF (ให้ตรงกับที่ถ่ายจากมือถือ)
    imgs = []
    for f in files:
        img = Image.open(f)
        img = ImageOps.exif_transpose(img)  # ✅ กันรูปกลับหัว/เอียง
        img = img.convert("RGB")
        imgs.append(img)

    n = len(imgs)
    if center_index < 1 or center_index > n:
        center_index = 1

    # ย้ายรูปเด่นไปเป็นรูปแรก (hero)
    hero_img = imgs[center_index - 1]
    others = [imgs[i] for i in range(n) if i != (center_index - 1)]
    ordered = [hero_img] + others  # ordered[0] = hero

    # ===== ตั้งค่าหน้าแนวนอน =====
    canvas_w = 1920
    pad = 8

    # เผื่อหัวแบบปลอดภัย (เพราะข้อความยาวไม่เท่ากัน)
    header_safe_h = 260

    # ฟอนต์
    font_title = ImageFont.truetype(FONT_PATH, 72)
    font_date = ImageFont.truetype(FONT_PATH, 54)
    font_body = ImageFont.truetype(FONT_PATH, 58)

    # ==============================
    # Hero layout สำหรับ 17/18
    # ==============================
    if n in (17, 18):
        canvas, top_cols, top_strip_h, hero_h, bottom_strip_h = compose_hero_layout_landscape(
            canvas_w, header_safe_h, pad, n
        )
        draw = ImageDraw.Draw(canvas)

        # ----- วาดข้อความก่อน -----
        y = 22
        y = draw_center_text(draw, branch, y, font_title, canvas_w)
        y = draw_center_text(draw, date, y + 4, font_date, canvas_w)
        y = draw_center_text(draw, detail, y + 8, font_body, canvas_w)

        # เริ่มวางรูปใต้ข้อความจริง (กันซ้อน)
        TEXT_BOTTOM_GAP = 16
        y0 = y + TEXT_BOTTOM_GAP

        # ----- แถวบน -----
        top_w = (canvas_w - (top_cols + 1) * pad) // top_cols
        for i in range(top_cols):
            x = pad + i * (top_w + pad)
            paste_tile(canvas, ordered[1 + i], x, y0, top_w, top_strip_h)

        # ----- โซนกลาง: ซ้าย 3 + hero + ขวา 3 -----
        y1 = y0 + top_strip_h + pad

        side_w = 260  # ✅ เหมาะกับแนวนอน ทำให้รูปกลางใหญ่ขึ้น
        hero_w = canvas_w - (side_w * 2) - (pad * 4)
        hero_x = pad * 2 + side_w

        paste_tile(canvas, ordered[0], hero_x, y1, hero_w, hero_h)

        side_tile_h = (hero_h - 2 * pad) // 3

        left_start = 1 + top_cols
        left_x = pad
        for j in range(3):
            yy = y1 + j * (side_tile_h + pad)
            paste_tile(canvas, ordered[left_start + j], left_x, yy, side_w, side_tile_h)

        right_start = left_start + 3
        right_x = hero_x + hero_w + pad
        for j in range(3):
            yy = y1 + j * (side_tile_h + pad)
            paste_tile(canvas, ordered[right_start + j], right_x, yy, side_w, side_tile_h)

        # ----- แถวล่าง 6 -----
        y2 = y1 + hero_h + pad
        bottom_cols = 6
        bottom_w = (canvas_w - (bottom_cols + 1) * pad) // bottom_cols

        bottom_start = right_start + 3
        for k in range(6):
            x = pad + k * (bottom_w + pad)
            paste_tile(canvas, ordered[bottom_start + k], x, y2, bottom_w, bottom_strip_h)

        out_name = f"report_{uuid.uuid4().hex[:10]}.jpg"
        buf = io.BytesIO()
        canvas.save(buf, format="JPEG", quality=92)
        buf.seek(0)
        return send_file(buf, mimetype="image/jpeg", as_attachment=True, download_name=out_name)

    # ==============================
    # Fallback grid (2/3/4/6/8/อื่นๆ)
    # ==============================
    rows, cols = pick_grid(n)
    cell_w, cell_h = 520, 520

    # สร้าง canvas แบบแนวนอน/กว้างพอดีกริด
    canvas_w2 = cols * cell_w + (cols + 1) * pad
    # วาดหัวบน canvas ก่อน แล้วค่อยเริ่มรูปใต้หัวจริง
    canvas_h2 = header_safe_h + rows * cell_h + (rows + 2) * pad
    canvas = Image.new("RGB", (canvas_w2, canvas_h2), "white")
    draw = ImageDraw.Draw(canvas)

    # วาดหัว
    y = 22
    y = draw_center_text(draw, branch, y, font_title, canvas_w2)
    y = draw_center_text(draw, date, y + 4, font_date, canvas_w2)
    y = draw_center_text(draw, detail, y + 8, font_body, canvas_w2)

    y0 = y + 16  # เริ่มรูปใต้ข้อความจริง

    for i, img in enumerate(ordered):
        r = i // cols
        c = i % cols
        if r >= rows:
            break
        x0 = pad + c * (cell_w + pad)
        y_img = y0 + pad + r * (cell_h + pad)
        paste_tile(canvas, img, x0, y_img, cell_w, cell_h)

    out_name = f"report_{uuid.uuid4().hex[:10]}.jpg"
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=92)
    buf.seek(0)
    return send_file(buf, mimetype="image/jpeg", as_attachment=True, download_name=out_name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

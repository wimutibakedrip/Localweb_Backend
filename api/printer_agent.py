import datetime
import os
import time
from zoneinfo import ZoneInfo

from escpos.printer import Network
from PIL import Image, ImageDraw, ImageFont
import requests
import qrcode 

# ==============================================================================
# CONFIGURATION
# ==============================================================================

#VERCEL_API_URL = "/api"
VERCEL_API_URL = "http://localhost:8000/api"
PRINTER_IP = "192.168.1.87"  # IP เครื่องพิมพ์ Worrex Wi-Fi

try:
    if os.name == "nt":  # ถ้าทำงานบน Windows
        font_title = ImageFont.truetype("C:/Windows/Fonts/tahomabd.ttf", 26)
        font_bold = ImageFont.truetype("C:/Windows/Fonts/tahomabd.ttf", 22)
        font_normal = ImageFont.truetype("C:/Windows/Fonts/tahoma.ttf", 22)
        font_small = ImageFont.truetype("C:/Windows/Fonts/tahoma.ttf", 20)
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(BASE_DIR, "images", "logo.jpg")
        qrcode_path = os.path.join(BASE_DIR, "images", "qrcode.jpg")
    else:  # ถ้าทำงานบน Raspberry Pi / Linux
        font_path_bd = "/usr/share/fonts/truetype/tlwg/Loma-Bold.ttf"
        font_path_reg = "/usr/share/fonts/truetype/tlwg/Loma.ttf"
        font_title = ImageFont.truetype(font_path_bd, 26)
        font_bold = ImageFont.truetype(font_path_bd, 22)
        font_normal = ImageFont.truetype(font_path_reg, 22)
        font_small = ImageFont.truetype(font_path_reg, 20)
        logo_path = "/home/ajcool/pythonfile/images/logo.jpg"
        qrcode_path = "/home/ajcool/pythonfile/images/qrcode.jpg"
except Exception as e:
    print(f"[Warning] โหลดฟอนต์ระบบไม่สำเร็จ ใช้ฟอนต์เริ่มต้น: {e}")
    font_title = font_bold = font_normal = font_small = ImageFont.load_default()

# ==============================================================================
# CREATE QRCODE ----------------------------------------------------------------
def crc16_ccitt(data: bytes) -> str:
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"

def generate_promptpay_qr_image(phone_number: str, amount: float) -> Image.Image:
    # แปลงเบอร์โทร 088-451-XXXX เป็นรูปแบบ 006688451XXXX
    clean_phone = phone_number.replace("-", "").strip()
    if clean_phone.startswith("0"):
        clean_phone = "0066" + clean_phone[1:]
    
    # โครงสร้างมาตรฐาน EMVCo PromptPay
    merchant_info = f"0016A0000006770101110113{clean_phone}"
    merchant_tag = f"29{len(merchant_info):02d}{merchant_info}"
    
    amount_str = f"{amount:.2f}"
    amount_tag = f"54{len(amount_str):02d}{amount_str}"
    
    payload = f"000201010212{merchant_tag}5303764{amount_tag}5802TH6304"
    checksum = crc16_ccitt(payload.encode('ascii'))
    full_payload = payload + checksum

    # สร้างภาพ QR Code
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(full_payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("L")
    
    # ปรับขนาดให้กว้าง 280px เท่ากับรูป QR เดิม
    return img.resize((280, 280), Image.Resampling.LANCZOS)

# ==============================================================================
# GRAPHIC GENERATION FUNCTIONS
# ==============================================================================
def create_order_ticket(order):
    img_width = 576
    margin = 20
    lines = []
    
    lines.append(("center", "\n", font_normal))
    lines.append(("center", "** ORDER TICKET **", font_title))
    lines.append(("center", "-" * 66, font_normal))
    
    order_id = order.get('id', '-')
    created_at = order.get('created_at', '')
    customer_name = order.get('customer_name') or 'หน้าร้าน'
    dt_th = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00')).astimezone(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M:%S")

    lines.append(("left_right", (f"Order : ", f"#{order_id}"), font_bold))
    lines.append(("left_right", (f"เวลา : ", f"{dt_th}"), font_normal))
    lines.append(("left", f"ลูกค้า: {customer_name}", font_bold))
    lines.append(("center", "-" * 66, font_normal))
    lines.append(("left_right", ("Qty x Description", "Item"), font_normal))
    lines.append(("center", "-" * 66, font_normal))

    raw_items = order.get('items') or order.get('order_items') or []
    def get_item_name(item):
        product_info = item.get('product') or {}
        return product_info.get('name') or item.get('product_name') or 'สินค้า'
    items = sorted(raw_items, key=get_item_name)

    qty_total = 0
    for item in items:
        p_name = get_item_name(item)
        qty = item.get('quantity', 1)
        qty_total += qty
        
        lines.append(("left", f"{qty}x {p_name}", font_bold if qty > 1 else font_normal))
        if item.get('custom_text'):
            lines.append(("left", f"  - หน้าเค้ก: \"{item['custom_text']}\"", font_small))

    lines.append(("center", "-" * 66, font_normal))
    lines.append(("left_right", ("Total Quantity:", f"{qty_total} PCS."), font_bold))
    if order.get('notes'):
        lines.append(("center", "-" * 66, font_normal))
        lines.append(("left", f"📌 Notes: {order.get('notes')}", font_bold))
    lines.append(("center", "\n\n", font_normal))

    img = Image.new('RGB', (img_width, len(lines) * 26 + 40), color='white')
    d = ImageDraw.Draw(img)
    current_y = margin
    for line_type, text_data, font in lines:
        if line_type == "center":
            bbox = d.textbbox((0, 0), text_data, font=font)
            d.text(((img_width - (bbox[2] - bbox[0])) / 2, current_y), text_data, fill='black', font=font)
        elif line_type == "left":
            d.text((margin, current_y), text_data, fill='black', font=font)
        elif line_type == "left_right":
            left_text, right_text = text_data
            d.text((margin, current_y), left_text, fill='black', font=font)
            bbox = d.textbbox((0, 0), right_text, font=font)
            d.text((img_width - margin - (bbox[2] - bbox[0]), current_y), right_text, fill='black', font=font)
        current_y += 26
    return img.crop((0, 0, img_width, current_y + 10))

#======================================================================
# modify qrcode and promptpay -----------------------------------------
def generate_receipt_graphic(order, title):
    img_width = 576  
    margin = 20
    lines = []
    logo_img, qrcode_img = None, None
     
    # ตั้งค่าข้อมูลพร้อมเพย์ (แก้เลข XXXX เป็นเบอร์จริงของคุณ)
    PROMPTPAY_PHONE = "080-XXX-5111"
    PROMPTPAY_NAME = "นาย อรรถกร เสนาะกรรณ์"
    
    # รับค่าเงื่อนไข selectqrcode
    select_qr = 'Y'
    net_total = float(order.get('grandtotal_price', order.get('total_price', 0)))

    # โหลดโลโก้ร้าน
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("L")
            basewidth = 300
            wpercent = basewidth / float(logo.size[0])
            logo = logo.resize((basewidth, int(float(logo.size[1]) * float(wpercent))), Image.Resampling.LANCZOS)
            logo_img = logo
        except Exception as e: print(f"[Error] โหลดโลโก้ไม่สำเร็จ: {e}")
    
    # ตรวจสอบเงื่อนไข selectqrcode
    if select_qr == 'Y':
        if os.path.exists(qrcode_path):
            try:
                qr = Image.open(qrcode_path).convert("L")
                qr_width = 280
                wpercent = qr_width / float(qr.size[0])
                qr_height = int(float(qr.size[1]) * float(wpercent))
                qrcode_img = qr.resize((qr_width, qr_height), Image.Resampling.LANCZOS)
            except Exception as e:
                print(f"[Error] โหลด QR Code ไม่สำเร็จ: {e}")
    elif select_qr == 'N':
        try:
            # สร้าง QR พร้อมเพย์ตามยอดเงินสุทธิ (net_total)
            qrcode_img = generate_promptpay_qr_image(PROMPTPAY_PHONE, net_total)
        except Exception as e:
            print(f"[Error] สร้าง PromptPay QR ไม่สำเร็จ: {e}")

    lines.extend([("center", "\n", font_normal), ("center", title, font_title if "COPY" in title else font_normal), ("center", "-" * 66, font_normal)])
    dt_th = datetime.datetime.fromisoformat(order.get('created_at', '').replace('Z', '+00:00')).astimezone(ZoneInfo("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M:%S")
    lines.extend([("left_right", ("Order : ", f"#{order.get('id', '-')}"), font_normal), ("left_right", ("เวลา : ", f"{dt_th}"), font_normal), ("left_right", (f"ลูกค้า: {order.get('customer_name') or 'หน้าร้าน'}", f"ชำระ: {order.get('payment_method') or '-'}"), font_normal), ("center", "-" * 66, font_normal), ("left_right", ("Qty x Description", "Total"), font_normal), ("center", "-" * 66, font_normal)])
    
    raw_items = order.get('items') or order.get('order_items') or []
    def get_item_name(item):
        product_info = item.get('product') or {}
        return product_info.get('name') or item.get('product_name') or 'สินค้า'
    items = sorted(raw_items, key=get_item_name)

    qty_total = 0
    for item in items:
        p_name = get_item_name(item)
        qty = item.get('quantity', 1)
        price = item.get('price', 0)
        qty_total += qty
        
        total_row_price = price * qty
        left_display_text = f"{qty}x {p_name} ({price:,.2f}/ea)"
        right_display_text = f"{total_row_price:,.2f}"
        
        lines.append(("item_row", (left_display_text, right_display_text), font_small))
        if item.get('custom_text'): 
            lines.append(("left", f"  - หน้าเค้ก: \"{item['custom_text']}\"", font_small))

    lines.extend([("center", "-" * 66, font_normal), ("left", f"Total: {qty_total} PCS.", font_normal), ("left_right", ("Sub Total:", f"{order.get('subtotal_price', order.get('total_price', 0)):,.2f} ฿"), font_normal)])
    if order.get('discount_price', 0) > 0: lines.append(("left_right", ("Discount:", f"-{order['discount_price']:,.2f} ฿"), font_normal))
    lines.extend([("center", "-" * 66, font_normal), ("left_right", ("Net Total:", f"{order.get('grandtotal_price', order.get('total_price', 0)):,.2f} ฿"), font_bold)])
    if order.get('notes'): lines.extend([("center", "-" * 66, font_normal), ("left", f"📌 Notes: {order['notes']}", font_normal)])
    lines.extend([("center", "\n", font_normal), ("center", "-" * 48, font_normal), ("center", "*** Thank you ***", font_small), ("center", "\n", font_normal), ("center", "IG/FB: Wimuti Bake & Drip", font_small), ("center", "\n", font_normal)])

    #=====================================================================================
    # คำนวณความสูงกระดาษ (เพิ่มพื้นที่เผื่อข้อความชื่อและเบอร์โทรอีก 65px กรณี selectqrcode == 'N')
    extra_qr_text_h = 65 if (select_qr == 'N' and qrcode_img) else 0
    logo_h = logo_img.size[1] if logo_img else 0
    qr_h = qrcode_img.size[1] if qrcode_img else 0
    img = Image.new('RGB', (img_width, len(lines) * 24 + 60 + logo_h + qr_h), color='white')
    d = ImageDraw.Draw(img)
    current_y = margin

    if logo_img:
        img.paste(logo_img, (int((img_width - logo_img.size[0]) / 2), int(current_y)))
        current_y += logo_img.size[1] + 15
    for l_type, text_data, font in lines:
        if l_type == "center":
            bbox = d.textbbox((0, 0), text_data, font=font)
            d.text(((img_width - (bbox[2] - bbox[0])) / 2, current_y), text_data, fill='black', font=font)
        elif l_type == "left":
            d.text((margin, current_y), text_data, fill='black', font=font)
        elif l_type in ["left_right", "item_row"]:
            left_txt, right_txt = text_data
            d.text((margin, current_y), left_txt, fill='black', font=font)
            bbox = d.textbbox((0, 0), right_txt, font=font)
            d.text((img_width - margin - (bbox[2] - bbox[0]), current_y), right_txt, fill='black', font=font)
        current_y += 24

    #==========================================================================
    # วาดรูป QR Code และข้อความด้านล่าง
    if qrcode_img:
        img.paste(qrcode_img, (int((img_width - qrcode_img.size[0]) / 2), int(current_y + 5)))
        current_y += qrcode_img.size[1] + 10
        
        # ถ้าเป็นพร้อมเพย์ ('N') ให้พิมพ์ชื่อและเบอร์โทรต่อท้ายด้านล่าง
        if select_qr == 'N':
            # บรรทัดที่ 1: ชื่อ
            bbox1 = d.textbbox((0, 0), PROMPTPAY_NAME, font=font_bold)
            d.text(((img_width - (bbox1[2] - bbox1[0])) / 2, current_y), PROMPTPAY_NAME, fill='black', font=font_bold)
            current_y += 26

            # บรรทัดที่ 2: เบอร์มือถือ
            phone_info = f"เบอร์มือถือ"
            bbox2 = d.textbbox((0, 0), phone_info, font=font_normal)
            d.text(((img_width - (bbox2[2] - bbox2[0])) / 2, current_y), phone_info, fill='black', font=font_normal)
            current_y += 26    

            # บรรทัดที่ 3: หมายเลข
            phone_display = f"โทร: {PROMPTPAY_PHONE}"
            bbox3 = d.textbbox((0, 0), phone_display, font=font_normal)
            d.text(((img_width - (bbox3[2] - bbox3[0])) / 2, current_y), phone_display, fill='black', font=font_normal)
            current_y += 26

    return img.crop((0, 0, img_width, current_y + 10))

def create_receipt_copy_image(order): return generate_receipt_graphic(order, "RECEIPT/ORDER (COPY)")
def create_receipt_image(order): return generate_receipt_graphic(order, "RECEIPT/ORDER")

# ==============================================================================
# NETWORKING & AGENT SYSTEM LOOP
# ==============================================================================
def print_receipt_to_worrex(order, current_type):
    try:
        if current_type == "order":
            printer = Network(PRINTER_IP, port=9100, timeout=5, profile="TUP500")
            printer.image(create_order_ticket(order))
            printer.cut()
            printer.close()  
            print(f"[-] พิมพ์ใบออเดอร์ ออเดอร์ #{order['id']} สำเร็จ")
            time.sleep(2.0)  
            return True

        if current_type == "receipt":
            # 1. พิมพ์ใบสำเนา (Copy)
            printer = Network(PRINTER_IP, port=9100, timeout=15, profile="TUP500")
            printer.image(create_receipt_copy_image(order))
            printer.cut()
            printer.close()
            print(f"[-] พิมพ์ใบเสร็จสำเนา ออเดอร์ #{order['id']} สำเร็จ")
            time.sleep(2.5) 

            # 2. พิมพ์ใบต้นฉบับ
            printer = Network(PRINTER_IP, port=9100, timeout=15, profile="TUP500")
            printer.image(create_receipt_image(order))
            printer.cut()
            printer.close()
            print(f"[-] พิมพ์ใบเสร็จต้นฉบับ ออเดอร์ #{order['id']} สำเร็จ")
            time.sleep(1.5)
            return True

    except Exception as e:
        print(f"[Error] พิมพ์งานประเภท {current_type} ของออเดอร์ #{order.get('id')} ค้าง: {e}")
        return False
        
    return False

# ฟังก์ชันสำหรับแปลงข้อมูลสรุปยอดขายเป็นไฟล์ภาพสำหรับส่งเข้าเครื่องพิมพ์ความร้อน
def create_sales_report_ticket(report_data):
    img_width = 576
    margin = 20
    lines = []
    
    lines.append(("center", "\n", font_normal))
    lines.append(("center", "Wimuti Bake & Drip", font_title))
    lines.append(("center", "\n", font_normal))
    lines.append(("center", "รายงานสรุปยอดขายประจำสัปดาห์", font_bold))
    lines.append(("center", f"รอบวันที่: {report_data['start_date']} ถึง {report_data['end_date']}", font_normal))
    lines.append(("center", "-" * 66, font_normal))
    
    # ข้อมูลสรุปตัวเลขหลัก
    lines.append(("left_right", ("รายได้รวมสุทธิ:", f"{report_data['total_revenue']:,.2f} ฿"), font_bold))
    lines.append(("left_right", ("จำนวนออเดอร์ที่สำเร็จ:", f"{report_data['total_orders']} ออเดอร์"), font_normal))
    lines.append(("center", "-" * 66, font_normal)) # เส้นประคั่นการเงิน
    lines.append(("left_right", ("  - ชำระด้วยเงินสด:", f"{report_data['total_cash']:,.2f} ฿"), font_normal))
    lines.append(("left_right", ("  - ชำระด้วยยอดโอน:", f"{report_data['total_transfer']:,.2f} ฿"), font_normal))
    lines.append(("center", "-" * 66, font_normal))
    
    # หัวข้ออันดับสินค้าขายดี
    lines.append(("left", "อันดับเมนูมียอดขายสูงสุด (Top Selling)", font_bold))
    lines.append(("center", "-" * 66, font_normal))
    
    # วาดหัวตารางจำลอง
    # รูปแบบการจัดคอลัมน์: อันดับ สินค้า จำนวนชิ้น ยอดเงิน
    lines.append(("table_header", ("อันดับ / รายชื่อเมนูสินค้า", "ชิ้น", "ยอดเงิน (฿)"), font_normal))
    lines.append(("center", "-" * 66, font_normal))
    total_amount = 0.0
    
    for idx, prod in enumerate(report_data.get("top_products", [])):
        rank_str = f"#{idx + 1} "
        p_name = prod.get("name", "สินค้า")
        qty_str = f"{prod.get('qty', 0)}"
        amount_str = f"{prod.get('total_amount', 0.0):,.2f}"
        total_amount = total_amount + prod.get('total_amount', 0.0)
        
        # ใส่ชื่ออันดับและสินค้าทางฝั่งซ้าย และเก็บจำนวนชิ้นและยอดเงินรวมคอลัมน์ขวาตามลำดับ
        lines.append(("table_row", (f"{rank_str}{p_name}", qty_str, amount_str), font_small))

    discount_total = report_data.get('total_discount', 0.0)
    net_revenue_total = report_data.get('total_revenue', 0.0)

    # ส่วนสรุปท้ายตารางแบบคิดคำนวณภาษี/ส่วนลดเพื่อโยงหาตัวเลขยอดรายได้สุทธิ
    lines.append(("center", "-" * 66, font_normal))
    lines.append(("right", f"ยอดรวมก่อนหักส่วนลด : {total_amount:,.2f} ฿", font_normal))
    lines.append(("right", f"ส่วนลดรวมสะสม (Discount) : -{discount_total:,.2f} ฿", font_normal))
    lines.append(("center", "=" * 56, font_normal))
    lines.append(("right", f"รายได้รวมสุทธิ (Grand Total) : {net_revenue_total:,.2f} ฿", font_bold))
    lines.append(("center", "\n", font_normal))

    lines.append(("center", "-" * 66, font_normal))
    lines.append(("center", f"พิมพ์เมื่อ: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", font_normal))
    lines.append(("center", "\n\n\n", font_normal))

    # คำนวณความสูงหน้ากระดาษแบบยืดหยุ่นตามจำนวนความยาวอันดับสินค้าที่มียอดขายจริง
    img = Image.new('RGB', (img_width, len(lines) * 26 + 60), color='white')
    d = ImageDraw.Draw(img)
    current_y = margin
    
    # ส่วนลูปรันวาดรูปกราฟิกของฟังก์ชัน create_sales_report_ticket ในไฟล์ agent.py
    for line_type, text_data, font in lines:
        if line_type == "center":
            bbox = d.textbbox((0, 0), text_data, font=font)
            d.text(((img_width - (bbox[2] - bbox[0])) / 2, current_y), text_data, fill='black', font=font)
        elif line_type == "left":
            d.text((margin, current_y), text_data, fill='black', font=font)
        
        # เพิ่มเงื่อนไข "right" ชิดขวานี้เข้าไป เพื่อให้ยอดสุทธิแสดงผลออกกระดาษความร้อนสำเร็จ!
        elif line_type == "right":
            bbox = d.textbbox((0, 0), text_data, font=font)
            d.text((img_width - margin - (bbox[2] - bbox[0]), current_y), text_data, fill='black', font=font)
            
        elif line_type == "left_right":
            left_text, right_text = text_data
            d.text((margin, current_y), left_text, fill='black', font=font)
            bbox = d.textbbox((0, 0), right_text, font=font)
            d.text((img_width - margin - (bbox[2] - bbox[0]), current_y), right_text, fill='black', font=font)
        elif line_type == "table_header":
            col1, col2, col3 = text_data
            d.text((margin, current_y), col1, fill='black', font=font)
            d.text((380, current_y), col2, fill='black', font=font)
            bbox = d.textbbox((0, 0), col3, font=font)
            d.text((img_width - margin - (bbox[2] - bbox[0]), current_y), col3, fill='black', font=font)
        elif line_type == "table_row":
            col1, col2, col3 = text_data
            # ดักข้อความชื่อสินค้าภาษาไทยยาวตัดคำไม่ให้ทับคอลัมน์อื่น
            max_chars = 24
            display_col1 = col1[:max_chars] + ".." if len(col1) > max_chars else col1
            d.text((margin, current_y), display_col1, fill='black', font=font)
            d.text((380, current_y), col2, fill='black', font=font)
            bbox = d.textbbox((0, 0), col3, font=font)
            d.text((img_width - margin - (bbox[2] - bbox[0]), current_y), col3, fill='black', font=font)
            
        current_y += 26
        
    return img.crop((0, 0, img_width, current_y + 10))


# ฟังก์ชันคำสั่งยิงพิมพ์รายงานผ่านเข้าเครื่องพิมพ์ Worrex
def print_sales_report_to_worrex(report_data):
    try:
        printer = Network(PRINTER_IP, port=9100, timeout=15, profile="TUP500")
        printer.image(create_sales_report_ticket(report_data))
        printer.cut()
        printer.close()
        print(f"[+] พิมพ์รายงานสรุปยอดรอบ {report_data['start_date']} - {report_data['end_date']} ออกทางกระดาษสำเร็จ!")
        return True
    except Exception as e:
        print(f"[Error] พิมพ์รายงานยอดขายขัดข้อง: {e}")
        return False


def start_agent():
    print(f"[*] Local Printer Agent ทำงานแล้ว (พิมพ์แยกประเภทงาน) | IP: {PRINTER_IP}")
    printed_cache = set()

    while True:
        try:
            response = requests.get(f"{VERCEL_API_URL}/orders/requested-print")
            if response.status_code == 200:
                orders = response.json()
                for order in orders:
                    order_id = order.get("id")
                    is_print_order = order.get('is_print_order', False)
                    is_print_receipt = order.get('is_print_receipt', False)

                    # 1. เช็คคิวฝั่ง "ใบออเดอร์ห้องครัว"
                    if is_print_order:
                        cache_key = (order_id, "order")  

                        # ให้ลบออกจากแคชเดิมทันที เพื่อให้พิมพ์ซ้ำออเดอร์ที่แก้ไขได้
                        if cache_key in printed_cache:
                            printed_cache.discard(cache_key)

                        if cache_key not in printed_cache:
                            printed_cache.add(cache_key)
                            success = print_receipt_to_worrex(order, "order")
                            if success:
                                try:
                                    requests.patch(f"{VERCEL_API_URL}/orders/{order_id}/mark-printed")
                                    print(f"[+] อัปเดตออเดอร์ #{order_id} บน Cloud สำเร็จ")
                                except Exception as e:
                                    print(f"[Error] ส่ง Patch ตั๋วครัวล้มเหลว: {e}")
                            else:
                                printed_cache.discard(cache_key)

                    # 2. เช็คคิวฝั่ง "ใบเสร็จและใบสำเนา"
                    if is_print_receipt:
                        cache_key = (order_id, "receipt")  

                        # ทำการล้างแคชบิลเดิมออกเช่นกัน หากหน้าเว็บส่งพิมพ์ใบเสร็จซ้ำ
                        if cache_key in printed_cache:
                            printed_cache.discard(cache_key)

                        if cache_key not in printed_cache:
                            printed_cache.add(cache_key)
                            success = print_receipt_to_worrex(order, "receipt")
                            if success:
                                try:
                                    requests.patch(f"{VERCEL_API_URL}/orders/{order_id}/mark-printed")
                                    print(f"[+] อัปเดตใบเสร็จออเดอร์ #{order_id} บน Cloud สำเร็จ")
                                except Exception as e:
                                    print(f"[Error] ส่ง Patch ใบเสร็จล้มเหลว: {e}")
                            else:
                                printed_cache.discard(cache_key)

                    if len(printed_cache) > 300:
                        printed_cache.clear()


            # 2. ตรวจสอบคิวพิมพ์รายงานสรุปยอดขายประจำสัปดาห์เพิ่มเติม
            report_response = requests.get(f"{VERCEL_API_URL}/sales/pending-print-report")
            if report_response.status_code == 200:
                jobs = report_response.json()
                for job in jobs:
                    job_id = job.get("job_id")
                    # สั่งพิมพ์งานรายงาน
                    success = print_sales_report_to_worrex(job)
                    if success:
                        # ยิงลบคิวออกจากฝั่ง Cloud เพื่อปิดงานพิมพ์ชิ้นนี้
                        requests.delete(f"{VERCEL_API_URL}/sales/clear-print-report/{job_id}")
                        print(f"[+] ปิดคิวงานพิมพ์รายงานรหัส #{job_id} บนเซิร์ฟเวอร์เรียบร้อย")


        except Exception as e:
            printed_cache.clear()
            print(f"[-] เชื่อมต่อ Cloud Printer ไม่สำเร็จ: {str(e)}")

        # คำสั่งนี้คือ สแกน cycle time every 3 sec. -------------------------------
        time.sleep(3)

if __name__ == "__main__":
    start_agent()

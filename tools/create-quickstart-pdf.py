"""Create a shareable, two-page Russian PDF from real quickstart screenshots."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output/pdf/VEIL-2.0.1-Quickstart-RU.pdf"
OUT.parent.mkdir(parents=True, exist_ok=True)
pdfmetrics.registerFont(TTFont("UI", "C:/Windows/Fonts/segoeui.ttf"))
pdfmetrics.registerFont(TTFont("UIBold", "C:/Windows/Fonts/seguisb.ttf"))
pdfmetrics.registerFontFamily("UI", normal="UI", bold="UIBold", italic="UI", boldItalic="UIBold")
W, H = 595.276, 841.89
M, CW = 40, 515.276
NAVY, BLUE, MUTED = "#111d2b", "#2468b5", "#657387"
RELEASE = "https://github.com/KashAlOt4SV/VlessBoost/releases/tag/v2.0.1"
ZIP = "https://github.com/KashAlOt4SV/VlessBoost/releases/download/v2.0.1/VEIL-2.0.1-windows-x64.zip"
c = canvas.Canvas(str(OUT), pagesize=(W, H))
c.setTitle("VEIL: подключение через AmneziaWG 3.1")
c.setAuthor("VEIL")


def para(text, y, size=10.5, leading=15, color=NAVY, width=CW, x=M, gap=8):
    style = ParagraphStyle("p", fontName="UI", fontSize=size, leading=leading,
                           textColor=colors.HexColor(color), alignment=TA_LEFT)
    p = Paragraph(text, style)
    _, height = p.wrap(width, 900)
    p.drawOn(c, x, y-height)
    return y-height-gap


def header(title, number):
    c.setFillColor(colors.HexColor(NAVY))
    c.rect(0, H-128, W, 128, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#93c5ff"))
    c.setFont("UIBold", 10)
    c.drawString(M, H-30, "VEIL  /  WINDOWS x64  /  AWG 3.1")
    para(title, H-49, size=25, leading=30, color="#ffffff", gap=0)
    c.setFillColor(colors.HexColor(MUTED))
    c.setFont("UI", 8)
    c.drawString(M, 22, "VEIL 2.0.1  ·  Инструкция со скриншотами")
    c.drawRightString(W-M, 22, f"{number} / 2")
    c.linkURL(RELEASE, (M, 17, 260, 33), relative=0)
    return H-149


def step(number, title, y):
    c.setFillColor(colors.HexColor(BLUE))
    c.roundRect(M, y-23, 23, 23, 6, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("UIBold", 11)
    c.drawCentredString(M+11.5, y-16, str(number))
    para(title, y-1, size=14, leading=18, x=M+34, width=CW-34, gap=0)
    return y-34


def screenshot(name, y, max_height):
    image = ImageReader(str(ROOT / "docs/guide" / name))
    iw, ih = image.getSize()
    scale = min(CW/iw, max_height/ih)
    width, height = iw*scale, ih*scale
    c.drawImage(image, M, y-height, width=width, height=height, mask="auto")
    return y-height-8


y = header("Новое подключение<br/>AmneziaWG 3.1", 1)
y = step(1, "Получите файл у «Вездехода»", y)
y = para("Нужен <b>AmneziaWG 3.1 именно файлом .conf</b> от «Вездехода», у которого вы покупаете VPN. Каждый использует свой файл.", y)
y = para("Получите его в боте или личном кабинете, где оформлена подписка. Если не находите нужную выдачу, напишите в поддержку:", y)
quote = "Нужен конфигурационный файл AmneziaWG 3.1 в формате .conf для подключения на Windows. Подскажите, как его получить для моей подписки."
style = ParagraphStyle("quote", fontName="UI", fontSize=10.2, leading=14.8, textColor=colors.HexColor(NAVY))
p = Paragraph(quote, style)
_, ph = p.wrap(CW-28, 500)
c.setFillColor(colors.HexColor("#edf5ff"))
c.roundRect(M, y-ph-24, CW, ph+24, 8, fill=1, stroke=0)
p.drawOn(c, M+14, y-ph-12)
y -= ph+36
y = step(2, "Скачайте и запустите VEIL", y)
y = para(f'<link href="{ZIP}" color="{BLUE}"><b>Скачать ZIP для Windows x64</b></link>   ·   <link href="{RELEASE}" color="{BLUE}">Страница релиза на GitHub</link>', y)
y = para("Распакуйте <b>весь архив</b>, откройте папку VEIL и запустите <b>VEIL.exe</b>. Папки <b>_internal</b> и <b>bin</b> оставьте рядом с EXE. Подтвердите запрос Windows на права администратора.", y)
y = para("Старую версию сначала завершите через <b>трей → Выход</b>: крестик может только скрыть окно.", y, size=9.7, leading=13.7)
y = step(3, "Настройки → Импорт .conf", y-2)
y = para("Выберите полученный от «Вездехода» файл и нажмите «Открыть» в окне выбора файла.", y)
y = screenshot("settings-import.png", y, 120)
y = para("После импорта появится <b>«Профиль AWG 3.1 проверен»</b>. Профиль сохраняется автоматически; ключи скрыты.", y, size=9.5, leading=13)
assert y > 40, y
c.showPage()

y = header("Выберите трафик<br/>и подключитесь", 2)
y = step(4, "Маршрутизация → Туннель", y)
y = para("Включите переключатели для нужных приложений и сервисов. <b>Голубой = правило включено.</b> Остальной трафик идёт напрямую.", y)
y = screenshot("routing-switches.png", y, 206)
y = para("Нет нужной программы? Нажмите <b>«+ Приложение»</b> и выберите её файл .exe. Если меняете правила при работающем VPN, отключитесь и подключитесь снова.", y, size=9.6, leading=13.5)
y = step(5, "Главная → Подключить", y-1)
y = screenshot("home-connect.png", y, 143)
y = para("Адрес на скриншоте демонстрационный. У вас будет сервер из собственного .conf.", y, size=8, leading=11, color=MUTED, gap=7)
y = para("Нажмите <b>«Подключить»</b> и дождитесь статуса <b>«Вы подключены»</b>. Затем откройте выбранное приложение. При необходимости полностью закройте его и запустите снова.", y, size=10, leading=14)
y = para("<b>Если не подключается:</b> уточните у «Вездехода» версию AWG 3.1 и активность подписки. Если включён другой VPN, отключите его и повторите попытку. Для помощи: <b>Журнал событий → Экспорт .log</b> и скриншот ошибки.", y, size=9.5, leading=13)
y = para("Файл .conf содержит личные ключи. Не публикуйте его в общем чате.", y, size=9, leading=12, color=MUTED)
assert y > 40, y
c.save()
print(OUT)

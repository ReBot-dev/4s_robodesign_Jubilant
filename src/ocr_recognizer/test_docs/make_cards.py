"""小さい紙（A5、A4 の上半分を切り取る）用のテスト文書と正解テキストを作る。

マーカーの台紙 card/corner0.pdf（ArUco の ID 1〜4、黒い四角 30mm）の上に、英語の文書を重ねて印刷する。
台紙の仕様（台紙の下半分にも書いてある）:
- A4 縦の上半分（210 × 148.5 mm）を切り取って使う
- 台紙の右端が、読むときの「上」。読む向きでは A5 縦（148.5 × 210 mm）になる
- 読む向きで、左上から時計回りに ID 2, 3, 4, 1
- 黒い四角は紙の端から 15.5mm（白い余白 7.5mm を含めると 8mm）

文字は読む向きで書き、90 度回して台紙に重ねる。四隅のマーカーと、その周りの白い余白には文字を置かない。

使い方（make_docs.py と同じ環境で。台紙との重ね合わせに pypdf も使う）:
    .venv/bin/pip install weasyprint pypdf
    .venv/bin/python make_cards.py
"""
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from weasyprint import HTML

from make_docs import box, lines, space, table, title

HERE = Path(__file__).resolve().parent
OUT = HERE / 'card'
TEMPLATE = OUT / 'corner0.pdf'

CARD_W, CARD_H = 148.5, 210   # 読む向きの紙の大きさ（mm）
SAFE_TOP, SAFE_BOTTOM = 56, 154   # 文字を置く範囲（読む向き、上からの mm）。マーカーと余白（〜53mm）を避ける
SAFE_SIDE = 10                    # 左右の余白（mm）

CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; }
/* 読む向きの紙。台紙の右端が上になるよう、時計回りに 90 度回して置く */
.card { position: absolute; left: 0; top: 0; width: %(w)smm; height: %(h)smm;
        transform-origin: 0 0; transform: translate(210mm, 0) rotate(90deg); }
.safe { position: absolute; left: %(side)smm; right: %(side)smm; top: %(top)smm; height: %(safe_h)smm;
        font-family: '%(font)s'; font-size: %(base)s; color: #000; line-height: 1.5; }
.line, th, td, h1, h2 { white-space: nowrap; }
.left { text-align: left; } .right { text-align: right; } .center { text-align: center; }
h1 { font-size: 13pt; text-align: center; margin: 0 0 2.5mm; font-weight: bold; }
table { border-collapse: collapse; width: 100%%; margin: 1.5mm 0; }
th, td { border: 0.25mm solid #000; padding: 0.8mm 1.5mm; }
th { background: #e6e6e6; font-weight: bold; }
.box { border: 0.4mm solid #000; padding: 1.5mm 3mm; margin: 1.5mm 0; }
.small { font-size: 6.5pt; line-height: 1.4; }
.big { font-size: 10pt; font-weight: bold; }
.sum { width: 50%%; margin-left: auto; }
"""

SERIF, SANS = 'Liberation Serif', 'Liberation Sans'

# (名前, 基本の文字サイズ, 部品, 書体)。部品の作り方は make_docs.py と同じ
CARDS = [
    ('01_notice', '8.5pt', [
        lines('October 20, 2026', align='right'),
        lines('To: All Students and Staff'),
        title('Notice of Fall Fire Drill'),
        lines('A fire and earthquake drill will be held as shown below.',
              'Please stay calm and follow the instructions of the staff.'),
        space(2),
        lines('1. Date: Thursday, November 12, 2026, 10:30 a.m. – 11:15 a.m.',
              '2. Assembly point: Main Field (north side of the front gate)',
              '3. What to bring: Nothing'),
        space(2),
        lines('If it rains, the drill will be replaced by an indoor announcement.',
              'For questions, contact the Facilities Office at ext. 2045.'),
        lines('Facilities Office, Sample Institute of Technology', align='right'),
    ], SERIF),
    ('02_invoice', '7.5pt', [
        title('INVOICE'),
        lines('Invoice No. INV-2026-1102-03', 'Date: 11/02/2026', 'Due Date: 12/15/2026', align='right'),
        lines('Bill to: Department of Robotics, Sample Institute of Technology'),
        lines('From: Example Robotics Supply Co., Tel: (555) 010-4567'),
        table([
            ['Item', 'Description', 'Qty', 'Unit', 'Amount'],
            ['SV-2040', 'Micro servo motor', '4', '24.50', '98.00'],
            ['M3-8-PH100', 'M3×8 screw (100 pcs)', '2', '4.20', '8.40'],
            ['USBC-1M', 'USB-C cable, 1.0 m', '3', '6.49', '19.47'],
        ], aligns=['left', 'left', 'right', 'right', 'right'],
           widths=['22%', '42%', '8%', '12%', '16%']),
        table([
            ['Subtotal', '125.87'],
            ['Sales Tax (8.25%)', '10.38'],
            ['Total (USD)', '$136.25'],
        ], header=False, aligns=['left', 'right'], cls='sum'),
        lines('Bank transfer: First Example Bank, Account No. 0012-3456-78', cls='small'),
    ], SANS),
    ('03_flyer', '8.5pt', [
        title('Robot Workshop for Beginners'),
        lines('Build and program a small line-following robot in one day!', align='center'),
        box(lines('Saturday, December 5, 2026', '1:00 p.m. – 5:00 p.m.', cls='big'),
            lines('Room 204, Engineering Building'), cls='center'),
        lines('• Fee: $15 (parts included, you keep the robot)',
              '• Capacity: 20 people (first come, first served)',
              '• Age: 12 and up; no experience needed'),
        lines('Register by November 30 at robots@example.edu', align='center'),
    ], SANS),
]


def build(name, base, parts, font):
    safe_h = SAFE_BOTTOM - SAFE_TOP
    css = CSS % {'w': CARD_W, 'h': CARD_H, 'side': SAFE_SIDE, 'top': SAFE_TOP,
                 'safe_h': safe_h, 'font': font, 'base': base}
    body = ''.join(p[0] for p in parts)
    html = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><style>{css}</style></head>'
            f'<body><div class="card"><div class="safe">{body}</div></div></body></html>')
    text_pdf = HTML(string=html).write_pdf()

    # 台紙（マーカー）に文字を重ねる
    page = PdfReader(TEMPLATE).pages[0]
    page.merge_page(PdfReader(__import__('io').BytesIO(text_pdf)).pages[0])
    writer = PdfWriter()
    writer.add_page(page)
    writer.add_metadata({'/Title': f'{name} (ArUco card, IDs 1-4)'})
    with open(OUT / f'{name}.pdf', 'wb') as f:
        writer.write(f)
    (OUT / f'{name}.txt').write_text('\n'.join(t for p in parts for t in p[1]) + '\n', encoding='utf-8')
    print(f'card/{name}.pdf / card/{name}.txt')


if __name__ == '__main__':
    for name, base, parts, font in CARDS:
        build(name, base, parts, font)

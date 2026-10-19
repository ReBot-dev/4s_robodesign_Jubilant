"""OCR 比較用のテスト文書（PDF）と正解テキスト（.txt）を作る。

PDF と .txt を同じデータから作るので、印刷される文字と正解が必ず一致する。
1 行ずつ折り返さずに印刷するため、PDF の 1 行 = .txt の 1 行になる。

使い方:
    python3 -m venv .venv && .venv/bin/pip install weasyprint
    .venv/bin/python make_docs.py
"""
from html import escape
from pathlib import Path

from weasyprint import HTML

OUT = Path(__file__).resolve().parent

# ArUco DICT_4X4_50 の ID 0-3（黒枠込み 6x6、1=白 0=黒）。紙の四隅に置く。
ARUCO = {
    0: ['000000', '010110', '001010', '000110', '000100', '000000'],
    1: ['000000', '000000', '011110', '010010', '010100', '000000'],
    2: ['000000', '000110', '000110', '000100', '011010', '000000'],
    3: ['000000', '010010', '010010', '001000', '001100', '000000'],
}
MARKER_MM = 25
MARKER_INSET_MM = 10


def marker_svg(marker_id):
    rects = ''.join(
        f'<rect x="{x}" y="{y}" width="1" height="1"/>'
        for y, row in enumerate(ARUCO[marker_id])
        for x, bit in enumerate(row)
        if bit == '0'
    )
    return (f'<svg viewBox="0 0 6 6" width="{MARKER_MM}mm" height="{MARKER_MM}mm" '
            f'shape-rendering="crispEdges"><rect width="6" height="6" fill="#fff"/>'
            f'<g fill="#000">{rects}</g></svg>')


# ---- 文書の部品。どれも (HTML, 正解テキストの行リスト) を返す ----

def lines(*texts, align='left', cls=''):
    html = ''.join(f'<div class="line">{escape(t)}</div>' for t in texts)
    return f'<div class="lines {align} {cls}">{html}</div>', list(texts)


def title(text, cls=''):
    return f'<h1 class="{cls}">{escape(text)}</h1>', [text]


def heading(text):
    return f'<h2>{escape(text)}</h2>', [text]


def space(mm=4):
    return f'<div style="height:{mm}mm"></div>', []


def table(rows, header=True, aligns=None, widths=None, cls=''):
    out = []
    if widths:
        out.append('<colgroup>' + ''.join(f'<col style="width:{w}">' for w in widths) + '</colgroup>')
    for i, row in enumerate(rows):
        tag = 'th' if header and i == 0 else 'td'
        cells = ''.join(
            f'<{tag} class="{(aligns[j] if aligns else "left")}">{escape(c)}</{tag}>'
            for j, c in enumerate(row)
        )
        out.append(f'<tr>{cells}</tr>')
    text = [' | '.join(c for c in row) for row in rows]
    return f'<table class="{cls}">{"".join(out)}</table>', text


def box(*parts, cls=''):
    html = ''.join(p[0] for p in parts)
    text = [t for p in parts for t in p[1]]
    return f'<div class="box {cls}">{html}</div>', text


def cols(left, right, widths=('50%', '50%')):
    """2 段組み。正解テキストは「左の段 → 右の段」の順。"""
    lh = ''.join(p[0] for p in left)
    rh = ''.join(p[0] for p in right)
    text = [t for p in left for t in p[1]] + [t for p in right for t in p[1]]
    html = (f'<div class="cols"><div style="width:{widths[0]}">{lh}</div>'
            f'<div style="width:{widths[1]}">{rh}</div></div>')
    return html, text


CSS = """
@page { size: %(size)s; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; padding: 40mm 20mm; font-family: 'Noto Sans CJK JP';
       font-size: %(base)s; color: #000; line-height: 1.6; }
.marker { position: fixed; }
.line, th, td, h1, h2 { white-space: nowrap; }
.left { text-align: left; } .right { text-align: right; } .center { text-align: center; }
h1 { font-size: 20pt; text-align: center; margin: 4mm 0 6mm; font-weight: bold; }
h2 { font-size: 12pt; margin: 5mm 0 2mm; font-weight: bold; }
table { border-collapse: collapse; width: 100%%; margin: 2mm 0; }
th, td { border: 0.3mm solid #000; padding: 1.2mm 2mm; }
th { background: #e6e6e6; font-weight: bold; }
.box { border: 0.5mm solid #000; padding: 3mm 4mm; margin: 2mm 0; }
.cols { display: flex; gap: 8mm; align-items: flex-start; }
.small { font-size: 7.5pt; line-height: 1.5; }
.big { font-size: 15pt; font-weight: bold; }
.huge { font-size: 30pt; }
.indent { padding-left: 3.5em; }
.sum { width: 45%%; margin-left: auto; }
"""

DOCS = [
    ('01_oshirase', 'A4', '11pt', [
        lines('2026年10月20日', align='right'),
        lines('学生・教職員各位'),
        lines('サンプル工業大学 総務課', align='right'),
        title('秋季避難訓練の実施について'),
        lines('日頃より防災活動にご協力いただき、ありがとうございます。',
              '地震と火災を想定した避難訓練を、下記のとおり実施します。',
              '訓練中は授業を一時中断し、全員で屋外へ避難します。',
              '落ち着いて、教職員の指示に従って行動してください。'),
        space(),
        lines('記', align='center'),
        space(2),
        lines('1. 日時　2026年11月12日（木）10:30〜11:15',
              '2. 想定　震度6弱の地震と、それに伴う火災の発生',
              '3. 避難場所　正門前の第1グラウンド',
              '4. 持ち物　特になし（貴重品は各自で管理してください）'),
        space(),
        lines('雨天の場合は、屋内での放送訓練に切り替えます。',
              '実施の可否は、当日8:00までに学内ポータルでお知らせします。',
              'ご不明な点は、総務課（内線 2045）までお問い合わせください。'),
        lines('以上', align='right'),
    ]),
    ('02_seikyusho', 'A4', '10pt', [
        title('請求書'),
        lines('No. INV-2026-1019-07', '発行日 2026年10月19日', 'お支払期限 2026年11月30日',
              align='right'),
        space(3),
        cols([
            lines('サンプル工業大学 ロボット工学科 御中', cls='big'),
            lines('件名 演習用部品一式'),
            box(lines('ご請求金額 ¥34,881（税込）', cls='big')),
        ], [
            lines('株式会社みほん精機',
                  '〒123-4567 見本県見本市中央1-2-3',
                  'TEL 012-345-6789 / FAX 012-345-6790',
                  '登録番号 T1234567890123'),
        ], widths=('55%', '45%')),
        space(3),
        table([
            ['No.', '品名', '数量', '単価（円）', '金額（円）'],
            ['1', 'サーボモーター SV-2040', '4', '3,850', '15,400'],
            ['2', 'アルミフレーム 20×20mm（長さ 500mm）', '6', '1,280', '7,680'],
            ['3', 'M3×8 なべ小ねじ（100本入）', '2', '640', '1,280'],
            ['4', 'リチウムポリマー電池 7.4V 2200mAh', '1', '4,980', '4,980'],
            ['5', 'USB-C ケーブル 1.0m', '3', '790', '2,370'],
        ], aligns=['center', 'left', 'right', 'right', 'right'],
           widths=['8%', '50%', '10%', '16%', '16%']),
        table([
            ['小計', '31,710'],
            ['消費税（10%）', '3,171'],
            ['合計', '34,881'],
        ], header=False, aligns=['left', 'right'], cls='sum'),
        space(3),
        lines('お振込先 みほん銀行 本店営業部 普通 1234567 カ）ミホンセイキ'),
        lines('※振込手数料は貴社にてご負担ください。', '※金額の単位はすべて円です。', cls='small'),
    ]),
    ('03_jikanwari', 'A4 landscape', '10pt', [
        title('2026年度 後期 演習室A 利用予定表'),
        lines('本館 2階 / 2026年10月1日 更新', align='right'),
        table([
            ['時限', '時間', '月', '火', '水', '木', '金'],
            ['1限', '9:00–10:40', 'ロボット設計', '—', '制御工学演習', '—', '電子回路実験'],
            ['2限', '10:50–12:30', 'ロボット設計', 'プログラミング基礎', '制御工学演習', '機構学', '電子回路実験'],
            ['3限', '13:20–15:00', '—', 'プログラミング基礎', '空き', '機構学', 'チーム演習'],
            ['4限', '15:10–16:50', '卒研ゼミ', '空き', 'センサ工学', '—', 'チーム演習'],
            ['5限', '17:00–18:40', '自主利用', '自主利用', '—', '自主利用', '—'],
        ], aligns=['center', 'center'] + ['center'] * 5,
           widths=['7%', '13%', '16%', '16%', '16%', '16%', '16%']),
        lines('※「—」は施錠中、「空き」は予約なしで利用できます。',
              '※自主利用は、事前に学生証を登録した人のみ利用できます。',
              '※予定は変更になることがあります。最新の情報は掲示板を確認してください。', cls='small'),
    ]),
    ('04_chirashi', 'A4', '11pt', [
        lines('小・中学生向け', align='center'),
        title('ロボット工作ワークショップ', cls='huge'),
        lines('はじめてのライントレースカーを作ろう！', align='center', cls='big'),
        lines('参加者募集', align='center', cls='big'),
        space(4),
        cols([
            lines('対象　小学5年生〜中学3年生',
                  '定員　20名（先着順）',
                  '参加費　1,500円（材料費込み）',
                  '日時　2026年12月13日（日）'),
            lines('13:30〜16:30', cls='indent'),
            lines('場所　サンプル工業大学'),
            lines('本館 2階 演習室A', cls='indent'),
        ], [
            box(lines('こんなことをします', cls='big'),
                lines('① モーターとセンサーを組み立てる',
                      '② 黒い線をたどるプログラムを書く',
                      '③ みんなでタイムを競うレース大会'),
                lines('完成したロボットは持ち帰れます！')),
        ]),
        space(6),
        box(lines('申込方法　11月30日（月）までに、メールでお申し込みください。',
                  'メールには「氏名・学年・保護者の連絡先」を書いてください。',
                  '申込先　workshop@example.com',
                  '主催　サンプル工業大学 ロボット工学科 学生チーム')),
    ]),
    ('05_shiyosho', 'A4', '9pt', [
        title('小型サーボモーター SV-2040 仕様書'),
        lines('Rev. 1.2 / 2026-10-01', align='right'),
        heading('1. 主な仕様'),
        table([
            ['項目', '値', '条件・備考'],
            ['定格電圧', '4.8–6.0 V', 'DC'],
            ['無負荷速度', '0.12 s/60°', '@6.0 V'],
            ['停動トルク', '2.5 kgf·cm（0.245 N·m）', '@6.0 V'],
            ['動作角度', '±90°（合計 180°）', '—'],
            ['制御パルス幅', '500–2500 μs', '中点 1500 μs'],
            ['PWM周期', '20 ms（50 Hz）', '—'],
            ['消費電流', '待機時 ≦ 10 mA ／ 動作時 ≦ 650 mA', '@6.0 V, 無負荷'],
            ['質量', '9.6 g', 'ケーブルを含まない'],
            ['外形寸法', '23.0 × 12.2 × 29.0 mm', '突起部を除く'],
            ['使用温度範囲', '−10〜+50 ℃', '結露なきこと'],
            ['ケーブル', '3芯 150 mm', '茶: GND / 赤: VCC / 橙: Signal'],
        ], widths=['20%', '45%', '35%']),
        heading('2. 注意事項'),
        lines('① 定格電圧（6.0 V）を超えて使用しないでください。故障や発熱の原因になります。',
              '② 出力軸を手で無理に回さないでください。内部のギアが破損するおそれがあります。',
              '③ 出力軸をロックした状態で通電を続けないでください（目安: 3 s 以上）。',
              '※ 本書の内容は、改良のため予告なく変更することがあります。', cls='small'),
        lines('Doc. No. SV2040-JP-012', align='right', cls='small'),
    ]),
]


def build(name, size, base, parts):
    landscape = 'landscape' in size
    pw, ph = (297, 210) if landscape else (210, 297)
    near, far_x, far_y = MARKER_INSET_MM, pw - MARKER_INSET_MM - MARKER_MM, ph - MARKER_INSET_MM - MARKER_MM
    corners = {0: (near, near), 1: (far_x, near), 2: (far_x, far_y), 3: (near, far_y)}
    markers = ''.join(
        f'<div class="marker" style="left:{x}mm;top:{y}mm">{marker_svg(i)}</div>'
        for i, (x, y) in corners.items()
    )
    body = ''.join(p[0] for p in parts)
    html = (f'<!doctype html><html lang="ja"><head><meta charset="utf-8">'
            f'<style>{CSS % {"size": size, "base": base}}</style></head>'
            f'<body>{markers}{body}</body></html>')
    doc = HTML(string=html).render()
    assert len(doc.pages) == 1, f'{name}: {len(doc.pages)} ページになった'
    doc.write_pdf(OUT / f'{name}.pdf')
    (OUT / f'{name}.txt').write_text('\n'.join(t for p in parts for t in p[1]) + '\n', encoding='utf-8')
    print(f'{name}.pdf / {name}.txt')


if __name__ == '__main__':
    for d in DOCS:
        build(*d)

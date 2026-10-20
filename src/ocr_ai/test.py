import os
here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, "..", "ocr_recognizer", "test_docs", "en", "05_datasheet.txt")
with open(path,encoding="utf-8") as f:
	ocr_text = f.read()

import anthropic
client = anthropic.Anthropic()

response = client.messages.create(
	model="claude-opus-5-5",
	max_tokens=16000,
	system="- 入力は OCR で読み取った英語の文書で、誤字や表の崩れがあるかもしれない- 自然な日本語に翻訳する。読み上げるので、箇条書き・表・記号・Markdown は使わない- 数字・日付・金額・型番は変えずに残す",
	messages=[{"role": "user", "content": ocr_text}],
)
summary = "".join(b.text for b in response.content if b.type == "text")

print(summary)

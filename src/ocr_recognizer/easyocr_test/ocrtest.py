import os
import easyocr

#読む対象のオブジェクトに日本語と英語を指定
reader = easyocr.Reader(['en', 'ja'], gpu=False)

#画像から文字データを抽出
def analyze_picture(target_path: str):
	results = reader.readtext(target_path)
	for result in results:
		print(result)

#試し実験用
if __name__ == "__main__":
	here = os.path.dirname(os.path.abspath(__file__))
	target = os.path.join(here, "test_img.png")
	analyze_picture(target)

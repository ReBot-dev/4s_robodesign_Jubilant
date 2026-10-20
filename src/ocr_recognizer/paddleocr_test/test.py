from paddleocr import PaddleOCR

ocr = PaddleOCR(lang='japan', enable_mkldnn=False)
result = ocr.predict('test_img.png')
for res in result:
	res.print()


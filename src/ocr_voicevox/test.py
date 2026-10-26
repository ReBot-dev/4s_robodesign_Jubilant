import requests

# ① 読み方のデータを作ってもらう（text と speaker は URL の後ろに付ける）
q = requests.post("http://localhost:50021/audio_query",
                  params={"text": "こんにちは", "speaker": 3})

# ② そのデータを本文に入れて、音声を作ってもらう
wav = requests.post("http://localhost:50021/synthesis",
                    params={"speaker": 3}, json=q.json())

# ③ 返ってきた音声をファイルに保存
with open("test.wav", "wb") as f:
    f.write(wav.content)

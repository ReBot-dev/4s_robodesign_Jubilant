# =============================================================================
# ocr_node — カメラ画像から紙を見つけて、Claude で日本語にし、VOICEVOX で読み上げるノード
#
# 流れ（画像が届くたびに on_image が呼ばれる）:
#   1. ArUco マーカー（ID 1〜4）を 4 つ探す
#   2. マーカーが「止まったまま 1 秒」見えたら、その紙を読むと決める（安定判定）
#   3. 紙を真上から見た形に補正し、読む向きに 90 度回す
#   4. 補正した画像を Claude に送り、要点・全文・不明な点を受け取る
#   5. 要点を VOICEVOX で音声にしてスピーカーで鳴らし、/ocr/done に「読み終わった」を出す
#      （4 と 5 は時間がかかるので、別のスレッドで動かす）
#
# 動かす前に:
#   source .venv/bin/activate                        # anthropic が入った仮想環境
#   read -rs ANTHROPIC_API_KEY && export ANTHROPIC_API_KEY
#   VOICEVOX のアプリを起動しておく（開いている間だけ音声合成のサーバーが動く）
# =============================================================================

# ros2 package
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge

# AruCo detect
import cv2
import numpy as np

# Claude
import base64
import os
import threading
import time
import anthropic
from pydantic import BaseModel

# VOICEVOX
import subprocess
import requests

from ocr_recognizer.prompt import SYSTEM_PROMPT


# ---- 設定（数字を変えて調整するところ） ------------------------------------

# 紙（カード）の仕様。台紙 test_docs/card/corner0.pdf の下半分に書いてある数字
#   - A4 の上半分を切り取ったカード。印刷した向き（台紙の向き）で横 210 × 縦 148.5 mm
#   - 台紙の「右端」が読むときの「上」。読む向きでは A5 縦（148.5 × 210 mm）になる
#   - 台紙の向きで、左上 ID 1・右上 ID 2・右下 ID 3・左下 ID 4
SHEET_W, SHEET_H = 210, 148.5  # 台紙の向きでの紙の大きさ（mm）
MARKER_MM = 30                 # マーカーの黒い四角の一辺（mm）
EDGE_MM = 15.5                 # 紙の端から黒い四角までの距離（mm）。白い余白 7.5mm を含む
MARKER_IDS = [1, 2, 3, 4]      # 4 つそろったら紙があるとみなす
PX_PER_MM = 10                 # 補正後の画像の細かさ。1mm = 10px（254dpi 相当）

STILL_PX = 5        # 前の画像からこれ以下しか動いていなければ「止まっている」（px）
STILL_SEC = 1.0     # 止まった状態がこの秒数続いたら読む

MODEL = 'claude-opus-5-5'
# ベンチマークでは Haiku（'claude-haiku-5-5'）でも文字の読み取りは十分正確だった。
# 料金や速さを優先したくなったら、ここを変えて比べてみる。

VOICEVOX_URL = 'http://localhost:50021'   # VOICEVOX アプリが開く音声合成サーバー
SPEAKER = 3          # 話者の番号。3 = ずんだもん（2 = 四国めたん、8 = 春日部つむぎ など）
SPEED = 1.2          # 話す速さ。1.0 が標準。要点（250 字くらい）が 1 分近くかかるので少し速める
# 作った音声を人に聞かせるときは「VOICEVOX:ずんだもん」のようにクレジットを表示する決まりがある


# ---- Claude から受け取る形 --------------------------------------------------
# src/ocr_ai/2test.py と同じ。Claude はこの 4 つの欄を必ず埋めて返してくる。

class Reading(BaseModel):
    doc_type: str        # 文書の種類（請求書、お知らせ など）
    summary: str         # 要点の読み上げ文（30 秒くらい）
    full: str            # 全文の読み上げ文
    unclear: list[str]   # 読めなかった・判断できなかった箇所


# ---- 紙の上でのマーカーの位置 -------------------------------------------------

def marker_corners_mm():
    """マーカー ID ごとに、4 つの角の位置（台紙の向きで、紙の左上からの mm）を返す。
    角の順番は OpenCV と同じで、左上 → 右上 → 右下 → 左下。"""
    far_x = SHEET_W - EDGE_MM - MARKER_MM   # 右側のマーカーの左端
    far_y = SHEET_H - EDGE_MM - MARKER_MM   # 下側のマーカーの上端
    # 各マーカーの左上の角の位置
    tl = {1: (EDGE_MM, EDGE_MM), 2: (far_x, EDGE_MM), 3: (far_x, far_y), 4: (EDGE_MM, far_y)}
    s = MARKER_MM
    return {i: np.array([[x, y], [x + s, y], [x + s, y + s], [x, y + s]], np.float32)
            for i, (x, y) in tl.items()}


# ---- VOICEVOX で読み上げる -------------------------------------------------------

def speak(text):
    """text を VOICEVOX で音声（wav）にして、スピーカーで鳴らす。鳴り終わるまで待つ。"""
    # ① 文章から「読み方のデータ」（アクセント・長さなど）を作ってもらう
    query = requests.post(f'{VOICEVOX_URL}/audio_query',
                          params={'text': text, 'speaker': SPEAKER}, timeout=30)
    query.raise_for_status()                 # エラーの返事なら、ここで例外にする
    q = query.json()
    q['speedScale'] = SPEED                  # 読み方のデータの中の「速さ」を書き換える

    # ② 読み方のデータを渡して、音声（wav）を作ってもらう
    wav = requests.post(f'{VOICEVOX_URL}/synthesis',
                        params={'speaker': SPEAKER}, json=q, timeout=120)
    wav.raise_for_status()

    # ③ aplay（Linux の音声再生コマンド）に wav を渡して鳴らす。ファイルには保存しない
    subprocess.run(['aplay', '-q'], input=wav.content, check=True)


# ---- ノード本体 ------------------------------------------------------------------

class OcrNode(Node):
    def __init__(self):
        super().__init__('ocr_node')
        self.bridge = CvBridge()
        self.dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        self.ref = marker_corners_mm()

        # Claude の窓口。API キーは環境変数 ANTHROPIC_API_KEY から自動で読まれる
        self.client = anthropic.Anthropic()
        if not os.environ.get('ANTHROPIC_API_KEY'):
            self.get_logger().warn('ANTHROPIC_API_KEY が設定されていません。このままだと Claude を呼べません')

        # 安定判定のための記録
        self.prev = None          # 前の画像でのマーカーの角の位置（16 点）
        self.still_since = None   # 止まり始めた時刻
        self.done = False         # この紙はもう読んだか
        self.busy = False         # いま Claude に問い合わせ中・読み上げ中か

        # 読み終わったことを知らせるトピック。中身は読み上げた要点（失敗したときは空の文字列）
        # アーム班はこれを受け取ったら、次の動きに進める
        self.done_pub = self.create_publisher(String, '/ocr/done', 10)

        self.create_subscription(Image, '/camera/camera/color/image_raw', self.on_image, 10)
        self.get_logger().info('画像を待っています')

    # 画像が届くたびに呼ばれる ------------------------------------------------
    def on_image(self, msg):
        # Claude に問い合わせ中・読み上げ中は、何もしないですぐ戻る
        if self.busy:
            return

        img = self.bridge.imgmsg_to_cv2(msg, 'bgr8')

        # --- 1. マーカーを探す（OpenCV 4.6 の書き方） ---
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = cv2.aruco.detectMarkers(gray, self.dictionary)
        found = sorted(ids.flatten().tolist()) if ids is not None else []

        if found != MARKER_IDS:
            # 4 つそろっていない ＝ 紙が無い・外れた・アームが動いている
            # → 記録を全部リセットして、次の紙を読めるようにする
            self.prev = None
            self.still_since = None
            self.done = False
            return

        # この紙はもう読んだので、紙が外れるまで何もしない
        if self.done:
            return

        # --- 2. 安定判定 ---
        # detectMarkers が返す順番は毎回バラバラなので、ID の小さい順に並べ直す。
        # こうしておくと、前の画像と「同じマーカーの同じ角」どうしを比べられる。
        order = np.argsort(ids.flatten())
        pts = np.array(corners)[order].reshape(-1, 2)   # 4 マーカー × 4 角 = 16 点

        if self.prev is not None:
            moved = np.abs(pts - self.prev).max()       # 一番大きく動いた点の移動量（px）
            if moved > STILL_PX:
                self.still_since = None                  # 動いた → 時計をリセット
        self.prev = pts

        now = time.monotonic()                           # 経過時間を測る用の時計
        if self.still_since is None:
            self.still_since = now                       # 止まり始めた時刻を覚える
        if now - self.still_since < STILL_SEC:
            return                                       # まだ 1 秒たっていない

        # ここまで来たら「止まったまま 1 秒」→ この紙を読む
        self.done = True

        # --- 3. 真上から見た平らな画像にする（まず台紙の向きで） ---
        src, dst = [], []
        for c, i in zip(corners, ids.flatten()):
            src.extend(c.reshape(4, 2))                  # 画像の上での角の位置
            dst.extend(self.ref[int(i)] * PX_PER_MM)     # 補正後の画像での角の位置
        H, _ = cv2.findHomography(np.array(src), np.array(dst), cv2.RANSAC, 5.0)
        size = (int(SHEET_W * PX_PER_MM), int(SHEET_H * PX_PER_MM))   # 2100 × 1485 px
        flat = cv2.warpPerspective(img, H, size, flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
        # 台紙の右端が「上」なので、左に 90 度回して読む向き（A5 縦）にする
        warped = cv2.rotate(flat, cv2.ROTATE_90_COUNTERCLOCKWISE)
        cv2.imwrite('/tmp/rectified.png', warped)        # 確認用に保存
        self.get_logger().info('紙を見つけました → /tmp/rectified.png。Claude に送ります')

        # --- 4. Claude に送る（別スレッドで） ---
        # Claude の返事には数十秒かかる。ここで待つと、その間 on_image が止まってしまうので、
        # 「別の作業員（スレッド）」に任せて、on_image はすぐ終わらせる。
        self.busy = True
        threading.Thread(target=self.read_with_claude, args=(warped,), daemon=True).start()

    # 別スレッドで動く：Claude に画像を送って結果を受け取り、読み上げる -------------
    def read_with_claude(self, warped):
        summary = ''   # 読み上げた要点。途中で失敗したら空のまま /ocr/done に出す
        try:
            # 画像を JPEG にして、文字列（base64）に変換する。API には文字列で送る決まり
            ok, jpg = cv2.imencode('.jpg', warped, [cv2.IMWRITE_JPEG_QUALITY, 90])
            image_data = base64.standard_b64encode(jpg.tobytes()).decode('utf-8')

            t0 = time.monotonic()
            response = self.client.messages.parse(
                model=MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{
                    'role': 'user',
                    'content': [
                        {'type': 'image',
                         'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': image_data}},
                        {'type': 'text', 'text': 'この文書を読み上げ用にしてください。'},
                    ],
                }],
                output_format=Reading,   # 返事を Reading の形に固定する
            )
            dt = time.monotonic() - t0

            # 安全上の理由で Claude が断ったときは、中身が空なので先に確認する
            if response.stop_reason == 'refusal':
                self.get_logger().warn('Claude が回答を断りました')
                return

            reading = response.parsed_output
            self.get_logger().info(f'Claude の返事（{dt:.1f} 秒）')
            self.get_logger().info(f'種類: {reading.doc_type}')
            self.get_logger().info(f'要点: {reading.summary}')
            self.get_logger().info(f'不明な点: {reading.unclear}')

            # --- 5. VOICEVOX で読み上げる ---
            text = reading.summary
            if reading.unclear:
                # 聞く人は紙を見られないので、読めなかった所があったことだけは伝える
                text += ' なお、読み取れない部分がありました。原本で確認してください。'
            self.get_logger().info('読み上げます')
            speak(text)
            summary = reading.summary
            self.get_logger().info('読み上げ終わり')

        except anthropic.AuthenticationError:
            self.get_logger().error('API キーが違うか、設定されていません（ANTHROPIC_API_KEY）')
        except anthropic.RateLimitError:
            self.get_logger().error('API の回数制限に当たりました。少し待ってから紙を置き直してください')
        except anthropic.APITimeoutError:
            self.get_logger().error('Claude の返事が時間内に来ませんでした（タイムアウト）')
        except anthropic.APIConnectionError as e:
            # e.__cause__ に、つながらなかった本当の理由（名前解決の失敗、接続の切断など）が入っている
            self.get_logger().error(f'Claude につながりません（ネット接続を確認）: {e.__cause__!r}')
        except anthropic.APIStatusError as e:
            self.get_logger().error(f'Claude からエラー {e.status_code}: {e.message}')
        except requests.exceptions.ConnectionError:
            self.get_logger().error('VOICEVOX につながりません（VOICEVOX のアプリを起動してください）')
        except requests.exceptions.RequestException as e:
            self.get_logger().error(f'VOICEVOX からエラー: {e}')
        except subprocess.CalledProcessError:
            self.get_logger().error('音声を鳴らせませんでした（aplay が失敗。スピーカーの設定を確認）')
        except Exception as e:
            # 上のどれにも当てはまらないエラー（キー未設定のときもここに来る）
            self.get_logger().error(f'うまくいきませんでした: {e}')
        finally:
            # 成功しても失敗しても、最後に必ず「読み終わった」を知らせて、「処理中」を解除する
            # （失敗したときに知らせないと、アームがずっと待ち続けてしまう）
            self.done_pub.publish(String(data=summary))
            self.busy = False


def main():
    rclpy.init()
    node = OcrNode()
    rclpy.spin(node)
    rclpy.shutdown()


if __name__ == '__main__':
    main()

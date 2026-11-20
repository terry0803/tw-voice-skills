"""口述轉逐字稿：用本機的 faster-whisper（small 模型）把錄音轉成文字，錄音不上傳。
輸出：錄音檔旁邊的 <檔名>_逐字.txt，每行一段，前面是秒數。
不給模型提示詞、不接續前文（給了提示詞，聽不清楚的地方模型會把提示詞當成講的話）。
用法：python dictate.py 錄音檔或資料夾
環境變數（換電腦時設定）：
  TW_VOICE_STT_PY     有 faster-whisper 的 Python（預設：執行這支程式的 Python）
  TW_VOICE_STT_LIB    faster-whisper 裝在別的資料夾時，指到那個資料夾（預設不用設）
  TW_VOICE_STT_MODEL  模型名稱或本機模型資料夾（預設 small，第一次用會下載）"""
import os, sys, glob, subprocess

PY = os.environ.get("TW_VOICE_STT_PY", sys.executable)
LIB = os.environ.get("TW_VOICE_STT_LIB", "")  # faster-whisper 裝在別的資料夾時才要設
MODEL = os.environ.get("TW_VOICE_STT_MODEL", "small")  # 模型名稱或本機模型資料夾
EXT = (".m4a", ".mp3", ".wav", ".aac", ".ogg", ".flac", ".mp4")


def worker(paths):
    if LIB:
        sys.path.insert(0, LIB)
    from faster_whisper import WhisperModel
    m = WhisperModel(MODEL, device="cpu", compute_type="int8", local_files_only=os.path.isdir(MODEL))
    for p in paths:
        segs, info = m.transcribe(p, language="zh", condition_on_previous_text=False, vad_filter=True)
        out = os.path.splitext(p)[0] + "_逐字.txt"
        with open(out, "w", encoding="utf-8") as f:
            for s in segs:
                f.write(f"[{s.start:6.1f}] {s.text.strip()}\n")
        print(f"{os.path.basename(p)}：{info.duration:.0f} 秒 → {out}", flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print(__doc__)
        return
    if sys.argv[1] == "_worker":
        worker(sys.argv[2:])
        return
    t = sys.argv[1]
    paths = [p for p in sorted(glob.glob(os.path.join(t, "*")))] if os.path.isdir(t) else [t]
    paths = [p for p in paths if p.lower().endswith(EXT) and not os.path.exists(os.path.splitext(p)[0] + "_逐字.txt")]
    if not paths:
        print("沒有還沒轉的錄音檔。")
        return
    for need, name in [(PY, "Python")] + ([(LIB, "faster-whisper 套件")] if LIB else []):
        if not os.path.exists(need):
            print(f"找不到{name}：{need}。這台電腦不能轉錄音，請作者直接貼文字。")
            sys.exit(2)
    sys.exit(subprocess.run([PY, os.path.abspath(__file__), "_worker", *paths]).returncode)


if __name__ == "__main__":
    main()

"""語料打包讀取：把十幾萬個小檔併成一個大檔（.bin）加位置索引（.idx.json），讀一篇只要跳到那個位置。
原因：D 槽是 exFAT，一個資料夾十幾萬個檔時，每開一個檔都要從頭掃目錄，讀一遍要五十分鐘；打包後幾十秒。
用法：
  import corpus; text = corpus.casual(rel)     # rel 是 docs.json 裡的相對路徑；包裡沒有就讀原檔
  python corpus.py pack casual                  # 打包口語語料（docs.json 的全部文章）
  python corpus.py pack academic                # 打包學術全文與摘要（語料/clean/human_body、human_abstract）"""
import os, sys, json, glob

HERE = os.path.dirname(os.path.abspath(__file__))
# 跟 topic.py 一樣看環境變數：裝好的 skill 不在專案資料夾裡，不能用程式所在位置推語料位置
CAS = os.environ.get("TW_VOICE_CORPUS", os.path.join(os.path.expanduser("~"), "tw-voice-corpus"))  # 口語語料資料夾；沒有語料時，用到語料的功能會自己略過
ROOT = os.path.dirname(os.path.abspath(CAS))
CLEAN = os.path.join(ROOT, "語料", "clean")
PACKS = {"casual": os.path.join(CAS, "clean", "pack"), "academic": os.path.join(CLEAN, "pack")}


class Pack:
    def __init__(self, base):
        self.base = base
        self.idx = json.load(open(base + ".idx.json", encoding="utf-8")) if os.path.exists(base + ".idx.json") else {}
        self.f = None

    def get(self, key):
        if key not in self.idx:
            return None
        if self.f is None:
            self.f = open(self.base + ".bin", "rb")
        off, n = self.idx[key]
        self.f.seek(off)
        return self.f.read(n).decode("utf-8")


_P = {}


def _pack(name):
    if name not in _P:
        _P[name] = Pack(PACKS[name])
    return _P[name]


def casual(rel):
    t = _pack("casual").get(rel)
    return t if t is not None else open(os.path.join(CAS, rel), encoding="utf-8").read()


def academic(path):
    """path 可以是完整路徑或「human_body/檔名」。"""
    key = os.path.relpath(path, CLEAN).replace("\\", "/") if os.path.isabs(path) or path.startswith("..") or ":" in path else path
    t = _pack("academic").get(key)
    return t if t is not None else open(path if os.path.exists(path) else os.path.join(CLEAN, key), encoding="utf-8").read()


def pack(name):
    import time
    t0 = time.time()
    if name == "casual":
        want = {d[0] for d in json.load(open(os.path.join(CAS, "clean", "docs.json"), encoding="utf-8"))}
        # 照當初寫入的順序讀（各來源 items.jsonl 的順序），在硬碟上大致連續；照檔名（雜湊）排序讀會到處跳，慢十倍以上
        keys, seen = [], set()
        for code in ("fineweb", "blogger", "pixnet", "gamerforum", "gamerhome", "pcdvd", "fgforum"):
            ip = os.path.join(CAS, code, "items.jsonl")
            if not os.path.exists(ip):
                continue
            for l in open(ip, encoding="utf-8"):
                k = os.path.join(code, "text", json.loads(l)["id"] + ".txt")
                if k in want and k not in seen:
                    keys.append(k)
                    seen.add(k)
        keys += sorted(want - seen)
        src = lambda k: os.path.join(CAS, k)
    else:
        keys = [f"{sub}/{os.path.basename(p)}" for sub in ("human_body", "human_abstract")
                for p in sorted(glob.glob(os.path.join(CLEAN, sub, "*.txt")))]
        src = lambda k: os.path.join(CLEAN, k)
    base = PACKS[name]
    idx, off = {}, 0
    with open(base + ".bin.tmp", "wb") as f:
        for i, k in enumerate(keys, 1):
            try:
                b = open(src(k), encoding="utf-8").read().encode("utf-8")
            except Exception:
                continue
            f.write(b)
            idx[k] = [off, len(b)]
            off += len(b)
            if i % 20000 == 0:
                print(f"  {i:,}/{len(keys):,}（{time.time() - t0:.0f} 秒）", flush=True)
    os.replace(base + ".bin.tmp", base + ".bin")
    json.dump(idx, open(base + ".idx.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{name}：{len(idx):,} 篇，{off / 1e6:,.0f} MB（{time.time() - t0:.0f} 秒）", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1] == "pack":
        pack(sys.argv[2])

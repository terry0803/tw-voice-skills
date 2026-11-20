"""同主題的真人文章（參考，不計分）：在口語語料（2012–2021 台灣部落格與論壇，約 14 萬篇）裡找含有全部關鍵字的文章，
統計真人寫這個主題「常提到的東西」與「常用的說法」，以及句子節奏。只輸出字串和比例，不輸出原文句子。
常提到的東西是別人的經歷，只能當線索：作者自己有的才寫，沒有的不要編。
用法：python topic.py 玉山,攻頂 [稿子.txt]；check.py 加 --topic 玉山,攻頂 也會呼叫它。
語料位置：環境變數 TW_VOICE_CORPUS（預設 ~/tw-voice-corpus）。語料沒有附在這個 repo 裡。"""
import sys, os, re, json, math, random
from collections import Counter
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features as F

C = os.environ.get("TW_VOICE_CORPUS", os.path.join(os.path.expanduser("~"), "tw-voice-corpus"))
DOCS = os.path.join(C, "clean", "docs.json")
BG = os.path.join(C, "clean", "bg_df.json")
EXPR = ["真的", "還好", "終於", "其實", "不過", "結果", "然後", "差點", "感覺", "好像", "竟然", "有點", "超級", "反正",
        "剛好", "後來", "還是", "吧", "啦", "呢", "喔", "耶", "哈哈", "XD", "好累", "好冷", "好美", "好熱", "感動", "值得", "傻眼", "崩潰"]
KW = []
EDGE_STOP = set("的了是在有和也就都很過著把被與及或而但則嗎呢吧啊喔啦耶我你他她它們這那個些還又才再要會能不一到從對給讓")


def _init(kws):
    global KW
    KW = kws


def _read(rel):
    """從打包的大檔讀（corpus.py）；沒有打包或沒有 corpus.py 時讀原檔。"""
    try:
        import corpus
        return corpus.casual(rel)
    except Exception:
        try:
            return open(os.path.join(C, rel), encoding="utf-8").read()
        except Exception:
            return ""


# 團購比價、訂房網這類灌字頁（11/19 晚上查到：「飯店＋入住」3,663 篇裡 75% 是這種，常提到的東西全是「限時、團購、特價、排行」）
SPAMWORDS = ["限時", "團購", "特價", "排行", "熱賣", "周年慶", "評比", "開箱文", "去哪買", "評鑑大隊", "優惠價", "訂房", "立即預訂",
             "最低價", "比價", "折扣碼", "免運", "請洽", "專線", "加LINE"]


def _match(item):
    t = _read(item[0])
    if not (t and all(k in t for k in KW)):
        return None
    return None if sum(1 for w in SPAMWORDS if w in t) >= 4 else t


def grams(t):
    s = re.sub(f"[^{F.CJK}]", " ", t)
    out = set()
    for w in s.split():
        for n in (2, 3, 4):
            for i in range(len(w) - n + 1):
                out.add(w[i:i + n])
    return out


def strip_boiler(texts):
    """拿掉同一句在很多篇裡一字不差出現的固定字（訂房網頁的「客房清潔服務」、部落格模板的「請暫時關閉廣告過濾器」）。
    11/19 晚上加：以前這些字串會被當成「真人寫這個主題常提到的東西」，住宿類主題前十五個幾乎都是它們。"""
    sp = lambda t: [x for x in re.split(r"[。！？!?\n]", t) if len(re.findall(f"[{F.CJK}]", x)) >= 6]
    c = Counter(x.strip() for t in texts for x in set(sp(t)))
    lim = max(4, 0.02 * len(texts))
    boiler = {x for x, k in c.items() if k >= lim}
    if not boiler:
        return texts
    return ["\n".join(x for x in re.split(r"(?<=[。！？!?\n])", t) if x.strip().rstrip("。！？!?") not in boiler and x.strip() not in boiler)
            for t in texts]


DET = re.compile("[這那一每哪某整兩幾]")


def fragment(g, joined):
    """切壞的字串：「家店」（這家店、那家店）、「去旅」（去旅行、去旅遊）、「日客」（每日客房）。
    看這個字串前後一個字：前後接的字很集中（一兩個字就佔了大部分），表示它只是某個更長的詞的一段；
    前面多半是「這、那、一」這類指示詞或數詞，表示它的第一個字是量詞（家、間、位）。"""
    left, right = Counter(), Counter()
    for m in re.finditer(re.escape(g), joined):
        i, j = m.start(), m.end()
        left[joined[i - 1] if i > 0 and re.match(f"[{F.CJK}]", joined[i - 1]) else "#"] += 1
        right[joined[j] if j < len(joined) and re.match(f"[{F.CJK}]", joined[j]) else "#"] += 1
    n = sum(left.values())
    if n < 5:
        return False
    for side in (left, right):
        top = side.most_common(2)
        if top[0][0] != "#" and (top[0][1] / n >= 0.6 or (len(top) > 1 and top[1][0] != "#" and (top[0][1] + top[1][1]) / n >= 0.85)):
            return True
    return sum(k for ch, k in left.items() if DET.match(ch)) / n >= 0.5


def bg_df(docs):
    """背景：隨機 2,000 篇的 2–4 字串文件頻率，第一次用時算好存檔。"""
    if os.path.exists(BG):
        return json.load(open(BG, encoding="utf-8"))
    random.seed(20211231)
    sample = random.sample([d[0] for d in docs], 2000)
    with Pool(8) as pool:
        texts = pool.map(_read, sample, chunksize=50)
    df = Counter()
    for t in texts:
        df.update(grams(t))
    out = dict(n=len(texts), df={g: c for g, c in df.items() if c >= 2})
    json.dump(out, open(BG, "w", encoding="utf-8"), ensure_ascii=False)
    return out


def report(kws, draft=None, header="同主題的真人文章（參考，不計分）", num=None):
    kws = [k.strip() for k in kws if k.strip()]
    title = f"## {num}. {header}" if num else f"## {header}"
    print(f"\n{title}\n")
    if not kws:
        return
    if not os.path.exists(DOCS):
        print(f"找不到口語語料（{C}），這一節略過。")
        return
    docs = json.load(open(DOCS, encoding="utf-8"))
    with Pool(10, initializer=_init, initargs=(kws,)) as pool:
        texts = [t for t in pool.imap_unordered(_match, docs, chunksize=300) if t]
    n = len(texts)
    print(f"關鍵字「{'＋'.join(kws)}」：口語語料裡有 {n} 篇真人文章（2012–2021 台灣部落格與論壇）。")
    if n < 8:
        print("篇數太少，參考價值有限。可以換比較常見的關鍵字。")
        if n == 0:
            return
    texts = strip_boiler(texts)
    B = bg_df(docs)
    nb, dfb = B["n"], B["df"]
    dft = Counter()
    for t in texts:
        dft.update(grams(t))
    # 含關鍵字的字串（例如「實習生」「有限公司」）本身不列，它們拆出來的碎片（「習生」「限公」）也不列
    with_kw = [g for g, c in dft.items() if c >= 3 and any(k in g for k in kws)]
    cand = []
    for g, c in dft.items():
        share = c / n
        if c < 3 or share < 0.12:
            continue
        if g[0] in EDGE_STOP or g[-1] in EDGE_STOP or any(g in k or k in g for k in kws):
            continue  # 「山的」「的路」這種跨詞碎片，以及關鍵字本身
        if any(g in e and dft[e] >= 0.7 * c for e in with_kw):
            continue
        ratio = share / ((dfb.get(g, 0) + 1) / (nb + 2))
        if ratio >= 5:
            cand.append((share * math.log(ratio), share, g))
    cand.sort(reverse=True)
    picked = []
    joined = "\n".join(texts)
    for _, share, g in sorted(cand, key=lambda x: (-len(x[2]), -x[0])):
        if any(g in p and dft[p] >= 0.7 * dft[g] for p, _ in picked):
            continue
        if fragment(g, joined):
            continue
        picked.append((g, share))
    picked = sorted(picked, key=lambda x: -x[1])[:15]
    if picked:
        print("\n真人寫這個主題常提到的東西（有提到的文章比例）："
              + "、".join(f"{g}（{s:.0%}）" for g, s in picked))
        print("這些是別人的經歷，只能當線索：你自己這次有的才寫，沒有的不要編。")
    use = [(w, sum(1 for t in texts if w in t) / n) for w in EXPR]
    use = [x for x in sorted(use, key=lambda x: -x[1]) if x[1] >= 0.1][:12]
    if use:
        mark = (lambda w: "（這份有用）" if draft and w in draft else "") if draft else (lambda w: "")
        print("\n真人寫這個主題常用的說法：" + "、".join(f"{w}（{s:.0%}）{mark(w)}" for w, s in use))
    fs = [F.feats(t) for t in texts]

    def med(k):
        xs = sorted(f.get(k, 0) for f in fs)
        return xs[len(xs) // 2]
    rows = [("平均句長（字）", "句長平均"), ("句子長短變化", "句長變異係數"), ("「我」（每千字）", "w:我"), ("語氣詞（每千字）", "語氣詞合計")]
    df_ = F.feats(draft) if draft else {}
    print("\n| 項目 | 同主題真人文章中位數 | 這份 |\n|---|---|---|")
    for name, k in rows:
        print(f"| {name} | {med(k):.2f} | {df_.get(k, 0):.2f} |" if draft else f"| {name} | {med(k):.2f} | – |")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    kws = sys.argv[1].split(",") if len(sys.argv) > 1 else []
    draft = open(sys.argv[2], encoding="utf-8").read() if len(sys.argv) > 2 else None
    report(kws, draft)

"""中文學術文字特徵：清理、切章、算特徵、比較兩組。
用法：
  python features.py prepare            # 把 ntu/nchu 全文清理、切出緒論與摘要，寫到 語料/clean/
  python features.py compare A B        # 比較兩個資料夾（每個 .txt 一份文件），輸出報表
"""
import sys, os, re, json, math, glob, statistics as st
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CORP = os.path.join(ROOT, "語料")

CJK = r"一-鿿"

# ---------- 清理 ----------
def clean_pdf_text(t):
    lines = []
    for ln in t.splitlines():
        s = ln.strip()
        if not s:
            lines.append("")
            continue
        n_cjk = len(re.findall(f"[{CJK}]", s))
        # 頁碼、頁首、圖表標號、公式碎片
        if re.fullmatch(r"[\divxlcIVXLC\-\s·.]+", s):
            continue
        if n_cjk < 3 and len(s) < 40:
            continue
        if re.match(r"^(圖|表)\s*[\d一二三四五六七八九十]+[\-–.．]\d*", s) and n_cjk < 30:
            continue
        lines.append(s)
    # 合併 PDF 斷行：前一行不是以句末標點結束就接起來
    out, buf = [], ""
    for s in lines:
        if s == "":
            if buf:
                out.append(buf); buf = ""
            continue
        if buf and not re.search(r"[。！？：」）)]$", buf):
            buf += s
        else:
            if buf:
                out.append(buf)
            buf = s
    if buf:
        out.append(buf)
    text = "\n".join(out)
    text = re.sub(r"(?<=[" + CJK + r"，。、；：])[ \t]+(?=[" + CJK + r"])", "", text)
    # PDF 抽字常在全形標點前後留空白
    text = re.sub(r"[ \t]+(?=[，。、；：」）！？])", "", text)
    text = re.sub(r"(?<=[，。、；：「（])[ \t]+", "", text)
    return text

def cut_sections(t):
    """回傳 dict(abstract, intro, body)。找不到就盡量給。"""
    res = {}
    m = re.search(r"摘\s*要(.{200,6000}?)(?:關鍵(?:字|詞)|Abstract|ABSTRACT)", t, re.S)
    if m:
        res["abstract"] = m.group(1)
    # 跳過目錄：正文第一章是「第一章」後面接著長段落的那一個
    starts = [mm.start() for mm in re.finditer(r"第\s*一\s*章|^1\s*[\.、]?\s*緒\s*論|^一、\s*緒\s*論", t, re.M)]
    body_start = None
    for s0 in starts:
        seg = t[s0:s0 + 1500]
        if len(re.findall(f"[{CJK}]", seg)) > 600 and seg.count("....") < 3 and not re.search(r"\.{6,}|…{3,}", seg):
            body_start = s0
            break
    if body_start is None and starts:
        body_start = starts[-1]
    if body_start is None:
        # 期刊論文常用「壹、緒論」「一、前言」「1. 前言」；找不到就從摘要之後開始
        mm = re.search(r"^(壹|一)[、.．]\s*(緒論|前言|導論)|^1\s*[.、．]?\s*(緒論|前言|導論)", t, re.M)
        body_start = mm.start() if mm else (m.end() if m else 0)
    if body_start is not None:
        end = None
        for mm in re.finditer(r"參考文獻|參考資料|References|REFERENCES", t[body_start:]):
            end = body_start + mm.start()
        body = t[body_start:end] if end else t[body_start:]
        res["body"] = body
        m2 = re.search(r"第\s*二\s*章|^2\s*[\.、]?\s*\S{2,8}$", body[200:], re.M)
        res["intro"] = body[: (m2.start() + 200) if m2 else 8000]
    return res

def prose_only(t):
    """只留像正文的段落：中文比例高、不是條列碎片。"""
    keep = []
    for p in t.split("\n"):
        n = len(re.findall(f"[{CJK}]", p))
        if n >= 40 and n / max(1, len(p)) > 0.5:
            keep.append(p)
    return "\n".join(keep)

# ---------- 特徵 ----------
CONNECTIVES = ["此外", "然而", "因此", "因而", "所以", "但是", "不過", "而且", "並且", "另外", "另一方面",
               "綜上所述", "總而言之", "總的來說", "換句話說", "也就是說", "值得注意的是", "值得一提的是",
               "首先", "其次", "最後", "接著", "同時", "進一步", "由此可見", "換言之", "亦即", "故", "因為", "由於",
               "雖然", "儘管", "然後", "於是", "例如", "譬如", "像是"]
AI_WORDS = ["至關重要", "關鍵", "顯著", "全面", "深入", "有助於", "旨在", "致力於", "確保", "提升", "優化",
            "賦能", "框架", "挑戰", "潛力", "核心", "本質上", "不僅", "更是", "日益", "越來越", "隨著",
            "有效地", "大幅", "進而", "從而", "以便", "得以", "在此背景下", "扮演", "角色", "不可或缺",
            "面臨", "嶄新", "創新", "全新", "高效", "精準", "無縫", "強大", "穩健", "可擴展"]
HEAVY = ["進行", "作出", "做出", "加以", "予以", "對於", "關於", "針對", "藉由", "透過", "基於", "以及", "其",
         "該", "此", "之", "於", "及", "並", "亦", "皆", "均", "則", "即", "乃"]
SELF = ["本研究", "本論文", "本計畫", "本文", "我們", "筆者", "作者", "本系統", "本實驗"]
NEG = ["沒有", "不是", "不能", "不會", "只有", "只是", "並非", "而非", "不到", "不用", "真的", "一樣", "什麼", "全部", "這樣"]
PUNCT = {"破折號": r"——|—|--", "冒號": r"：", "分號": r"；", "引號": r"「|」", "全形括號": r"（|）",
         "半形括號": r"\(|\)", "頓號": r"、", "問號": r"？", "驚嘆號": r"！", "半形逗號": r"(?<=[" + CJK + r"]),|,(?=[" + CJK + r"])",
         "書名號": r"《|》", "粗體星號": r"\*\*",
         # 口語常見（11/17 加，供口語基準用）
         "半形問號驚嘆號": r"(?<=[" + CJK + r"])[?!]", "刪節號": r"…|\.\.\.|。。", "波浪號": r"~|～", "空格斷句": r"(?<=[" + CJK + r"]) (?=[" + CJK + r"])"}
# 口語詞：第一人稱、語氣詞、口語副詞與口頭禪
CASUAL = ["我", "你", "啊", "吧", "啦", "喔", "哦", "耶", "欸", "呢", "嗎", "哈哈", "超", "好像", "其實", "然後",
          "結果", "就是", "覺得", "反正", "應該", "感覺", "有點", "蠻", "滿", "還是", "竟然", "居然"]
PARTICLES = ["啊", "吧", "啦", "喔", "哦", "耶", "欸", "呢", "嗎"]
PATTERNS = {
    "不是X而是Y": r"不是[^。！？\n]{1,25}而是",  # 11/17 修：舊版不允許中間有逗號，漏掉「不是 X，而是 Y」
    "不僅X更/還Y": r"不僅[^。]{1,30}(更|還|也)",
    "隨著X的Y": r"隨著[^，。]{1,25}的",
    "被字句": r"被",
    "透過X來": r"透過[^，。]{1,20}來",
    "以X為Y": r"以[^，。]{1,15}為",
    "進行+動詞": r"進行[" + CJK + r"]{2}",
    "可以/能夠": r"可以|能夠",
    "將X": r"將",
}

# 書面連接詞。11/19 修：以前直接數「而」「並」兩個字，會把「而且、而已、而是、反而」和「並且、並不、並沒」也算進去（約四成），
# 「然而、進而」還會被算兩次。現在單獨的「而」「並」才算，複合詞各算一次。
CONN_RX = re.compile("因此|因而|從而|此外|然而|由於|透過|藉由|進而|以及|(?<![然進因從反時])而(?![且已是言非後今])|(?<![合一])並(?![且不沒非未無排列肩重存行])")


def sentences(t):
    return [s for s in re.split(r"[。！？；\n]", t) if len(re.findall(f"[{CJK}]", s)) >= 4]

def feats(t):
    n = max(1, len(re.findall(f"[{CJK}]", t)))
    k = 1000 / n
    f = {"cjk_chars": n}
    for w in dict.fromkeys(CONNECTIVES + AI_WORDS + HEAVY + SELF + NEG + CASUAL):
        f["w:" + w] = t.count(w) * k
    f["w:我"] = (t.count("我") - t.count("我們")) * k  # 只算單數「我」
    f["語氣詞合計"] = sum(t.count(w) for w in PARTICLES) * k
    f["否定與限定詞合計"] = sum(t.count(w) for w in NEG[:9]) * k
    f["常見書面連接合計"] = len(CONN_RX.findall(t)) * k
    for name, pat in PUNCT.items():
        f["p:" + name] = len(re.findall(pat, t)) * k
    f["p:逗號"] = t.count("，") * k
    for name, pat in PATTERNS.items():
        f["s:" + name] = len(re.findall(pat, t)) * k
    f["的"] = t.count("的") * k
    ss = sentences(t)
    lens = [len(re.findall(f"[{CJK}A-Za-z0-9]", s)) for s in ss]
    if len(lens) >= 3:
        f["句長平均"] = st.mean(lens)
        f["句長標準差"] = st.pstdev(lens)
        f["句長變異係數"] = f["句長標準差"] / max(1, f["句長平均"])
        f["長句比例(>60字)"] = sum(l > 60 for l in lens) / len(lens)
        f["短句比例(<15字)"] = sum(l < 15 for l in lens) / len(lens)
    clauses = [c for c in re.split(r"[，。！？；、：\n]", t) if c.strip()]
    cl = [len(re.findall(f"[{CJK}A-Za-z0-9]", c)) for c in clauses]
    if cl:
        f["子句平均長"] = st.mean(cl)
    paras = [p for p in t.split("\n") if len(re.findall(f"[{CJK}]", p)) >= 20]
    if paras:
        f["段落平均字數"] = st.mean(len(re.findall(f"[{CJK}]", p)) for p in paras)
    # 相鄰句開頭重複
    heads = [re.sub(r"[^" + CJK + "]", "", s)[:2] for s in ss]
    f["相鄰句同開頭比例"] = sum(1 for a, b in zip(heads, heads[1:]) if a and a == b) / max(1, len(heads) - 1)
    return f

def load_dir(d):
    docs = {}
    for p in sorted(glob.glob(os.path.join(d, "*.txt"))):
        t = open(p, encoding="utf-8").read()
        if len(re.findall(f"[{CJK}]", t)) >= 150:
            docs[os.path.basename(p)] = t
    return docs

def ngram_logodds(A, B, nmin=2, nmax=4, top=60, min_count=8):
    """Monroe et al. 2008 informative Dirichlet log-odds，回傳 A 偏多與 B 偏多的字串。
    以文件數過濾，避免單篇論文的專有名詞。"""
    def grams(t):
        t = re.sub(f"[^{CJK}，。、；：「」（）]", " ", t)
        c = Counter()
        for seg in t.split():
            for n in range(nmin, nmax + 1):
                for i in range(len(seg) - n + 1):
                    g = seg[i:i + n]
                    if re.search(f"[{CJK}]", g):
                        c[g] += 1
        return c
    ca, cb, dfa, dfb = Counter(), Counter(), Counter(), Counter()
    for t in A.values():
        g = grams(t); ca.update(g); dfa.update(set(g))
    for t in B.values():
        g = grams(t); cb.update(g); dfb.update(set(g))
    prior = ca + cb
    a0 = sum(prior.values()) * 0.01 / max(1, len(prior))
    na, nb = sum(ca.values()), sum(cb.values())
    a_tot = a0 * len(prior)
    out = []
    for g, c in prior.items():
        if c < min_count:
            continue
        # 至少出現在兩組各 15% 的文件之一，避免單篇專有名詞
        if dfa[g] / max(1, len(A)) < 0.15 and dfb[g] / max(1, len(B)) < 0.15:
            continue
        ya, yb = ca[g], cb[g]
        l = math.log((ya + a0) / (na + a_tot - ya - a0)) - math.log((yb + a0) / (nb + a_tot - yb - a0))
        var = 1 / (ya + a0) + 1 / (yb + a0)
        out.append((l / math.sqrt(var), g, ya, yb, dfa[g], dfb[g]))
    out.sort()
    return out[-top:][::-1], out[:top]

def compare(da, db, outpath):
    A, B = load_dir(da), load_dir(db)
    FA = [feats(t) for t in A.values()]
    FB = [feats(t) for t in B.values()]
    keys = sorted(set().union(*[f.keys() for f in FA + FB]))
    rows = []
    for k in keys:
        xa = [f.get(k, 0) for f in FA]; xb = [f.get(k, 0) for f in FB]
        ma, mb = st.mean(xa), st.mean(xb)
        sd = math.sqrt((st.pvariance(xa) + st.pvariance(xb)) / 2) or 1e-9
        d = (ma - mb) / sd
        pa = sum(1 for v in xa if v > 0) / len(xa); pb = sum(1 for v in xb if v > 0) / len(xb)
        rows.append((d, k, ma, mb, pa, pb))
    rows.sort(key=lambda r: -abs(r[0]))
    hi, lo = ngram_logodds(A, B)
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(f"# 比較：A={os.path.basename(da)}（{len(A)} 篇）  B={os.path.basename(db)}（{len(B)} 篇）\n\n")
        f.write("每千個漢字的次數（句長等為原值）。d = (A平均 − B平均)/合併標準差，|d|≥0.8 算大差異。\n\n")
        f.write("| 特徵 | A 平均 | B 平均 | d | A 有出現的比例 | B 有出現的比例 |\n|---|---|---|---|---|---|\n")
        for d, k, ma, mb, pa, pb in rows:
            if k == "cjk_chars":
                continue
            f.write(f"| {k} | {ma:.2f} | {mb:.2f} | {d:+.2f} | {pa:.0%} | {pb:.0%} |\n")
        f.write("\n## A 比 B 多用的字串（log-odds z 值）\n\n| z | 字串 | A 次數 | B 次數 | A 文件數 | B 文件數 |\n|---|---|---|---|---|---|\n")
        for z, g, ya, yb, fa, fb in hi:
            f.write(f"| {z:.1f} | {g} | {ya} | {yb} | {fa} | {fb} |\n")
        f.write("\n## B 比 A 多用的字串\n\n| z | 字串 | A 次數 | B 次數 | A 文件數 | B 文件數 |\n|---|---|---|---|---|---|\n")
        for z, g, ya, yb, fa, fb in lo:
            f.write(f"| {z:.1f} | {g} | {ya} | {yb} | {fa} | {fb} |\n")
    print("wrote", outpath, len(A), len(B))

def prepare():
    dst = {k: os.path.join(CORP, "clean", k) for k in ["human_intro", "human_abstract", "human_body"]}
    for d in dst.values():
        os.makedirs(d, exist_ok=True)
    stats = Counter()
    for src in glob.glob(os.path.join(CORP, "*", "text", "*.txt")):
        name = os.path.basename(os.path.dirname(os.path.dirname(src))) + "_" + os.path.basename(src)
        if len(name) > 80:  # 有些期刊的檔名是編碼後的中文篇名，太長會超過 Windows 路徑上限
            import hashlib
            name = name.split("_")[0] + "_" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:16] + ".txt"
        t = clean_pdf_text(open(src, encoding="utf-8").read())
        sec = cut_sections(t)
        for key, folder in [("intro", "human_intro"), ("abstract", "human_abstract"), ("body", "human_body")]:
            if key in sec:
                p = prose_only(sec[key])
                if len(re.findall(f"[{CJK}]", p)) >= 300:
                    open(os.path.join(dst[folder], name), "w", encoding="utf-8").write(p)
                    stats[key] += 1
    # 台科大與中興的公開摘要
    jls = [(p, os.path.basename(os.path.dirname(p)) + "_", "abstract") for p in glob.glob(os.path.join(CORP, "*", "abstracts.jsonl"))]
    jls.append((os.path.join(CORP, "nchu", "items.jsonl"), "nchu_", "abstract"))
    for jl, prefix, key in jls:
        if os.path.exists(jl):
            for line in open(jl, encoding="utf-8"):
                r = json.loads(line)
                rid = r.get("id") or r.get("handle")
                ab = r["abstract"]
                if len(re.findall(f"[{CJK}]", ab)) >= 200:
                    open(os.path.join(dst["human_abstract"], f"{prefix}{rid}.txt"), "w", encoding="utf-8").write(ab)
                    stats["abstract_web"] += 1
    print(dict(stats))

if __name__ == "__main__":
    if sys.argv[1] == "prepare":
        prepare()
    elif sys.argv[1] == "compare":
        compare(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else os.path.join(ROOT, "分析", "compare.md"))

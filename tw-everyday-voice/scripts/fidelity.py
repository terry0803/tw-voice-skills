"""事實保真檢查：比對原稿與改寫稿，列出可能改壞的地方。
- 一定要在的：數字（含百分比、金額、日期、單位）、網址、引號裡的原話、書名、英文名稱。少了就列出來。
- 改寫多出來的數字、英文名稱、引號原話：可能是編的，列出來請作者確認。
- 否定詞與程度詞（可能、預計、尚未、約、至少……）：先把兩邊的句子配對（字的兩兩組合重疊最多的配在一起），
  原句有、配到的改寫句沒有，就提醒「意思可能反過來」或「確定程度可能被拉高」；反過來則是「確定程度可能被降低」。
  否定改直述本來就是建議的改法，所以這兩類只是提醒，要人看一眼，不算錯。
- 「（需作者補充：……）」佔位不算多出來的內容。
用法：python fidelity.py 原稿 改寫稿 [--json]
回傳碼：0 沒有一定要處理的；1 有缺漏或多出來的數字、名稱、原話。"""
import sys, re, json, os

NUM = re.compile(r"(?<![A-Za-z0-9])(?:NT\$|US\$|\$|＄)?\d+(?:[.,]\d+)*\s*(?:%|％|萬|億|千|元|塊|歲|年|月|日|號|點|分|秒|小時|天|週|周|次|人|篇|頁|個|台|臺|張|間|名|位|件|公里|公尺|公分|毫秒|公斤|km|kg|ms|GB|MB|KB|x|倍|成)?")
URL = re.compile(r"https?://[^\s，。）)」]+")
QUOTE = re.compile(r"「([^「」]{1,80})」")
BOOK = re.compile(r"《([^《》]{1,60})》")
LATIN = re.compile(r"[A-Za-z][A-Za-z0-9.+#_\-]*[A-Za-z0-9+#]|[A-Za-z]{2,}")
PLACEHOLDER = re.compile(r"（需作者(補充|確認)[^）]*）")
NEG = ["沒有", "沒", "不是", "不能", "不會", "不要", "不用", "未", "無法", "並非", "非", "別", "勿", "尚未", "還沒", "從未", "不"]
NEG_FALSE = ["不過", "不錯", "不同", "不斷", "不少", "不管", "不僅", "不但", "不如", "不久", "不然", "未來", "無論", "非常", "非得", "沒想到", "別人", "別的", "差別", "分別", "特別", "區別", "個別"]
HEDGE = ["可能", "也許", "或許", "大概", "大約", "約為", "約有", "約佔", "左右", "預計", "計畫", "打算", "正在", "尚未", "還沒", "仍", "應該", "似乎",
         "傾向", "初步", "部分", "有些", "多數", "少數", "至少", "最多", "超過", "不到", "將近", "幾乎", "可望", "希望"]
HEDGE_FALSE = ["可能性", "無限可能", "不可能", "盡可能", "計畫書", "約定", "合約", "契約", "預約", "應該是說", "仍然", "部分的人"]


HEDGE_GROUP = {w: g for g, ws in {"可能": ["可能", "也許", "或許", "似乎", "可望"], "尚未": ["尚未", "還沒"],
                                    "大約": ["大概", "大約", "約為", "約有", "約佔", "左右", "將近", "幾乎"],
                                    "預計": ["預計", "計畫", "打算", "希望"], "部分": ["部分", "有些", "有點", "少數", "多數"]}.items() for w in ws}


# 同一組的說法互相替換不算變（仍→還是、尚未→還沒）。整篇淨增減用這張表算。
GROUP_WORDS = {"可能": ["可能", "也許", "或許", "似乎", "可望"], "尚未": ["尚未", "還沒", "未"], "仍": ["仍", "依然", "依舊", "還是"],
               "大約": ["大概", "大約", "約為", "約有", "約佔", "左右", "將近", "幾乎"], "預計": ["預計", "計畫", "打算", "希望"],
               "部分": ["部分", "有些", "有點", "少數", "多數"]}
HEDGE_GROUP["仍"] = "仍"


def group_count(text, g):
    """整篇裡這一組說法出現幾次（先拿掉不算的詞，例如「可能性」「仍然」）。"""
    text = text.replace("計劃", "計畫")
    for f in HEDGE_FALSE:
        text = text.replace(f, "")
    return sum(text.count(w) for w in GROUP_WORDS.get(g, [g]))


def neg_count(text, w):
    for f in NEG_FALSE:
        text = text.replace(f, "")
    return text.count(w)


def sents(t):
    return [s.strip() for s in re.split(r"(?<=[。！？!?；;])|\n+", t) if s.strip()]


def bigrams(s):
    s = re.sub(r"\s+", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def has_any(s, words, false):
    s = s.replace("計劃", "計畫")  # 只是改成台灣寫法，不是多了「計畫」
    for f in false:
        s = s.replace(f, "")
    return [w for w in words if w in s]


def multiset(xs):
    d = {}
    for x in xs:
        d[x] = d.get(x, 0) + 1
    return d


def norm_num(x):
    return re.sub(r"\s+", "", x).replace("％", "%").replace("＄", "$").replace("臺", "台").replace("周", "週")


def diff(a, b):
    """a 有、b 完全沒有的（只要 b 還出現過一次就不算缺：把重複的提法合併是好事，不是改壞）。"""
    sb = set(b)
    return list(dict.fromkeys(x for x in a if x not in sb))


LISTMARK = re.compile(r"(?m)^\s*(\d{1,2}[.、)）]|[（(]\d{1,2}[)）])")  # 清單編號不是事實
ESCAPED = re.compile(r"\\[nrt]")  # 字面上的 \n 這類跳脫字


def check(orig, new):
    new_clean = PLACEHOLDER.sub("", new)
    res = dict(missing={}, added={}, warn=[], info=[])
    o_num = LISTMARK.sub("", ESCAPED.sub("\n", orig))
    n_num = LISTMARK.sub("", ESCAPED.sub("\n", new_clean))
    for name, rx, f in [("數字", NUM, norm_num), ("網址", URL, str), ("書名", BOOK, str), ("英文名稱", LATIN, str)]:
        src_o, src_n = (o_num, n_num) if name in ("數字", "英文名稱") else (orig, new_clean)
        a = [f(m.group(1) if rx.groups else m.group()) for m in rx.finditer(src_o)]
        b = [f(m.group(1) if rx.groups else m.group()) for m in rx.finditer(src_n)]
        if name == "數字":
            a, b = [x for x in a if re.search(r"\d", x)], [x for x in b if re.search(r"\d", x)]
        miss, add = diff(a, b), diff(b, a)
        if miss:
            res["missing"][name] = miss
        if add:
            res["added"][name] = add
    qa = [m.group(1) for m in QUOTE.finditer(orig)]
    qb = [m.group(1) for m in QUOTE.finditer(new_clean)]
    gone = [q for q in qa if q not in new_clean]
    if gone:
        res["missing"]["引號裡的原話"] = gone
    unq = [q for q in qa if q in new_clean and q not in qb]
    if unq:
        res["info"].append("拿掉引號但內文還在：" + "、".join(unq[:8]))
    addq = [q for q in qb if q not in orig]
    if addq:
        res["added"]["引號裡的原話"] = addq
    so, sn = sents(orig), sents(new_clean)
    bn = [bigrams(s) for s in sn]
    lost_sents = []
    for s in so:
        g = bigrams(s)
        if len(g) < 4:
            continue
        # 配對看「原句的兩字組合有幾成出現在改寫句」，改寫常把兩句併成一句，用這個比較不會被長句稀釋
        scored = sorted(((len(g & h) / len(g), j) for j, h in enumerate(bn)), reverse=True)
        if not scored or scored[0][0] < 0.15:
            lost_sents.append(s)
            continue
        # 原句常被拆成兩句：分數最高的兩句一起看（第二句也要有一定重疊）
        top = [scored[0][1]] + [j for sc, j in scored[1:2] if sc >= 0.08]
        t = "".join(sn[j] for j in sorted(top))
        # 11/19 晚上修：以前配對時把分數最高的兩句接在一起比，鄰句本來就有的「可能、應該」會被當成新加的，
        # 原句的程度詞挪到別句也會被當成不見了，誤報很多（第七輪 46 則提醒幾乎都是這種）。
        # 現在除了配對的句子，還要整篇的次數真的變了才提醒：整篇變少才算不見、整篇變多才算多了。
        no, nn = has_any(s, NEG, NEG_FALSE), has_any(t, NEG, NEG_FALSE)
        no = [w for w in no if neg_count(new_clean, w) < neg_count(orig, w)]
        if no and not nn:
            res["warn"].append(f"否定詞不見了，確認意思沒有反過來：「{s[:40]}」→「{t[:40]}」")
        ho, hn = has_any(s, HEDGE, HEDGE_FALSE), has_any(t, HEDGE, HEDGE_FALSE)
        # 同一組的程度詞互相替換不算變（還沒→尚未；雙重保留「可能……或許」留一個也不算）
        gn = {HEDGE_GROUP.get(h, h) for h in hn} | {g for g, ws in GROUP_WORDS.items() if any(w in t for w in ws)}
        lost = [h for h in ho if HEDGE_GROUP.get(h, h) not in gn
                and group_count(new_clean, HEDGE_GROUP.get(h, h)) < group_count(orig, HEDGE_GROUP.get(h, h))]
        if lost:
            res["warn"].append(f"程度詞「{'、'.join(lost)}」不見了，確定程度可能被拉高：「{s[:40]}」→「{t[:40]}」")
        # 多了：只看配對分數最高的那一句（不看接進來的鄰句），而且整篇的次數真的變多
        t1 = sn[scored[0][1]]
        g1 = {HEDGE_GROUP.get(h, h) for h in ho}
        gain = [h for h in has_any(t1, HEDGE, HEDGE_FALSE) if h not in ho and HEDGE_GROUP.get(h, h) not in g1
                and group_count(new_clean, HEDGE_GROUP.get(h, h)) > group_count(orig, HEDGE_GROUP.get(h, h))]
        if gain and not ho:
            res["warn"].append(f"多了程度詞「{'、'.join(gain)}」，確定程度可能被降低：「{s[:40]}」→「{t1[:40]}」")
    if lost_sents:
        res["info"].append(f"原稿有 {len(lost_sents)} 句在改寫稿裡找不到對應（被刪或整句改寫），例如：" + "／".join(x[:24] for x in lost_sents[:3]))
    res["lost_sentences"] = len(lost_sents)
    res["n_sentences"] = len([s for s in so if len(bigrams(s)) >= 4])
    res["placeholders"] = len(PLACEHOLDER.findall(new))
    return res


def report(res):
    lines = ["# 事實保真檢查\n"]
    if res["missing"]:
        lines.append("## 原稿有、改寫稿沒有（一定要確認）\n")
        lines += [f"- {k}：" + "、".join(v[:12]) for k, v in res["missing"].items()]
    if res["added"]:
        lines.append("\n## 改寫稿多出來的（確認不是編的）\n")
        lines += [f"- {k}：" + "、".join(v[:12]) for k, v in res["added"].items()]
    if res["warn"]:
        lines.append("\n## 意思或確定程度可能變了（看一眼）\n")
        lines += ["- " + w for w in res["warn"][:20]]
    if res["info"]:
        lines.append("\n## 參考\n")
        lines += ["- " + w for w in res["info"][:12]]
    if res["placeholders"]:
        lines.append(f"\n改寫稿留了 {res['placeholders']} 處「需作者補充」。")
    if not (res["missing"] or res["added"] or res["warn"]):
        lines.append("數字、名稱、原話都在，沒有多出來的，否定與程度詞也沒看到變化。")
    return "\n".join(lines)


def read(p):
    if p.endswith(".docx"):
        import zipfile
        x = zipfile.ZipFile(p).read("word/document.xml").decode("utf-8")
        return re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", x))
    return open(p, encoding="utf-8").read()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    r = check(read(sys.argv[1]), read(sys.argv[2]))
    print(json.dumps(r, ensure_ascii=False, indent=1) if "--json" in sys.argv else report(r))
    sys.exit(1 if (r["missing"] or r["added"]) else 0)

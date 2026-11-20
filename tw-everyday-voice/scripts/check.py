"""拿台灣碩論／教師論文的「人寫基準」檢查一份中文稿子。
用法：python check.py 稿子.txt|.md|.docx [--kind abstract|body|casual]
  casual＝口語模式（作業、心得、貼文），對照 2012–2021 台灣部落格與論壇，見 casual() 的說明。
只看驗證過、能區分人寫與 AI 稿的核心項目（見 SKILL.md 與 分析/驗證結果）：
  1. 人寫學術文字幾乎不用的詞句（出現率 < 5%），連同所在句子
  2. 核心特徵：否定與限定詞、冒號、頓號、分號、引號、全形括號、破折號、短句比例偏高；
     書面連接、句長、段長、子句長偏低
  3. 問題數合計（保留的人寫片段中位數 1，AI 稿中位數 9；3 個以上就要改）
  基準有 p75／p25 時，另外標「接近上限／下限」，不計分。
只列問題，不改稿。"""
import sys, os, re, json, argparse, zipfile
sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import features as F

CORE_HI = ["否定與限定詞合計", "p:冒號", "p:頓號", "p:分號", "p:引號", "p:全形括號", "p:破折號", "短句比例(<15字)", "p:粗體星號"]
CORE_LO = ["常見書面連接合計", "句長平均", "段落平均字數", "子句平均長"]
RARE_OK = set(F.AI_WORDS) | {"值得注意的是", "值得一提的是", "綜上所述", "總而言之", "總的來說", "換句話說", "也就是說",
                             "換言之", "由此可見", "筆者", "真的", "不用", "不到", "全部", "破折號", "驚嘆號", "粗體星號"}
# 「不是X而是Y」11/17 拿掉：舊正規式不允許中間有逗號，漏掉最常見的「不是 X，而是 Y」，算出人寫 0% 是錯的；
# 照 build_phrases.py 的寫法，人寫論文正文 5.6%、口語 6.4% 的片段有用，不算罕用，改由句型與用詞那一節顯示。
NAMES = {"否定與限定詞合計": "否定與限定詞（沒有、不是、不能、只有……）", "常見書面連接合計": "書面連接（因此、而、並、透過……）",
         "p:冒號": "冒號", "p:頓號": "頓號", "p:分號": "分號", "p:引號": "引號「」", "p:全形括號": "全形括號",
         "p:破折號": "破折號", "p:粗體星號": "粗體 **", "短句比例(<15字)": "短句（不到 15 字）比例",
         "句長平均": "平均句長（字）", "段落平均字數": "平均段長（字）", "子句平均長": "平均子句長（字）"}
PATS = {"否定與限定詞合計": "|".join(F.NEG[:9]), "p:冒號": "：", "p:頓號": "、", "p:分號": "；", "p:引號": "「",
        "p:全形括號": "（", "p:破折號": "——|—", "p:粗體星號": r"\*\*"}

def read_text(p):
    if p.lower().endswith(".docx"):
        with zipfile.ZipFile(p) as z:
            x = z.read("word/document.xml").decode("utf8")
        x = re.sub(r"</w:p>", "\n", x)
        return re.sub(r"<[^>]+>", "", x)
    return open(p, encoding="utf-8").read()

def pattern_for(key):
    k = key[2:]
    if key.startswith("w:"):
        return re.escape(k)
    if key.startswith("p:"):
        return F.PUNCT.get(k)
    if key.startswith("s:"):
        return F.PATTERNS.get(k)

CASUAL_HI = ["否定與限定詞合計", "p:頓號", "p:分號", "p:冒號", "p:全形括號", "p:引號"]
CASUAL_INFO = [("語氣詞合計", "語氣詞（啊、吧、啦、喔、呢、嗎……）"), ("w:我", "「我」"),
               ("口語連接合計", "口語連接（因為、所以、不過、但是、雖然、然後、就是、其實）"),
               ("p:驚嘆號", "驚嘆號"), ("句長平均", "平均句長（字）"), ("句長變異係數", "句子長短變化（變異係數，越小越平均）"),
               ("段落平均字數", "平均段長（字）")]
SPOKEN_CONN = ["因為", "所以", "不過", "但是", "雖然", "然後", "就是", "其實"]


def rank(v, x):
    """x 高於大約幾 % 的人寫文章（用基準裡每 5% 一格的分位數 q 估）；基準沒有 q 時回傳 None。"""
    q = v.get("q")
    if not q:
        return None
    return 5 * sum(1 for y in q if y < x)


def phrase_section(t, reg, num):
    """句型與用詞：對照 norms_phrases.json（build_phrases.py 用全部人寫語料算的出現比例）。不計分。
    reg：casual＝人寫口語、body＝學術正文、abstract＝學術摘要。"""
    p = os.path.join(HERE, "norms_phrases.json")
    if not os.path.exists(p):
        return
    import phrases as P
    J = json.load(open(p, encoding="utf-8"))
    items, meta = J["items"], J["meta"]
    who = {"casual": "人寫口語文", "body": "人寫論文正文", "abstract": "人寫論文摘要"}[reg]
    hs = P.hits(t)
    rare, few, common = [], [], []
    for i in hs:
        cat, label, _ = P.LEXICON[i]
        if cat not in P.AI_CATS and cat != "中國用語":
            continue
        if reg != "casual" and label in RARE_OK:
            continue  # 學術模式第 1 節已經處理
        r = items[i][reg]
        (rare if r < 0.01 else few if r < 0.05 else common).append((i, r))
    print(f"\n## {num}. 句型與用詞（跟{who}比，不計分）\n")
    if not (rare or few or common):
        print("沒有命中常見的 AI 句型、套語或中國用語。")
    for mark, group in [("⚠ 幾乎沒人用", rare), ("△ 少用", few)]:
        for i, r in sorted(group, key=lambda x: x[1]):
            cat, label, _ = P.LEXICON[i]
            alt = f"；台灣說法：{P.TW_ALT[label]}" if label in P.TW_ALT else ""
            if label in getattr(P, "TW_CONTEXT", {}):
                alt += f"（{P.TW_CONTEXT[label]}）"
            ex = P.example(t, i)
            sp = items[i].get("spoken")
            spk = f"（真人說話 {sp:.1%}）" if sp is not None and reg == "casual" else ""
            print(f"- {mark}「{label}」（{cat}）：{who}只有 {r:.1%} 用過{spk}{alt}")
            for s in ex[:2]:
                print(f"    · {s}")
    if common:
        print("\n人寫也常用、不必為了去 AI 味刪掉的：" + "、".join(f"「{P.LEXICON[i][1]}」（{r:.0%}）" for i, r in common))
    v = meta.get("validation_casual" if reg == "casual" else "validation_body", {})
    if rare and v:
        vwho = "人寫口語文" if reg == "casual" else "人寫論文正文片段"
        print(f"\n這份有 {len(rare)} 項「幾乎沒人用」。保留的{vwho}同時有 2 項以上的只有 {v['human_ge2']:.0%}，"
              f"過去的 Claude 稿 {v['ai_ge2']:.0%}（其中「工作筆記腔」是從這批稿子找出來的、「助理口吻」是從 ChatGPT 回答找出來的，"
              "在找出它們的那批稿子上命中率會偏高）。不計分；看到 2 項以上就改。")
    if reg == "casual":
        miss = [(P.LEXICON[i][1], items[i]["casual"]) for i in range(len(items))
                if P.LEXICON[i][0] == "人寫口語常用" and i not in hs and items[i]["casual"] >= 0.2]
        if miss:
            print("\n人寫口語常用、這份沒用到的說法（參考）：" + "、".join(f"{w}（{r:.0%}）" for w, r in sorted(miss, key=lambda x: -x[1])[:6]))


def show_hits(k, sents, top):
    hits = [s for s in sents if re.search(PATS[k], s)]
    for s in sorted(hits, key=lambda s: -len(re.findall(PATS[k], s)))[:top]:
        print(f"    · {s[:90]}")


EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿\U0001F000-\U0001F2FF]")


def format_section(t, num):
    """照 speak-human-tw 的格式與殘留規則檢查（不計分）。有印出東西才回傳 True。"""
    cj = len(re.findall(f"[{F.CJK}]", t))
    out = []
    dash = len(re.findall(r"——|—", t))
    if dash > max(1, cj // 400):
        out.append(f"破折號 {dash} 個（{cj} 字）：說人話建議每 300–500 字最多 1 個，多的改逗號、句號或冒號。")
    bold = len(re.findall(r"\*\*[^*\n]+\*\*", t))
    if bold:
        out.append(f"粗體 {bold} 處：一段最多 2–3 個詞；貼到純文字平台會露出星號。")
    em = EMOJI.findall(t)
    if len(em) > 1:
        out.append(f"表情符號 {len(em)} 個：一則貼文最多 1 個，不要當列表符號。")
    half = re.findall(f"[{F.CJK}][,;:!?]|[{F.CJK}]\\((?=[{F.CJK}])", t)
    if half:
        out.append(f"半形標點夾在中文裡 {len(half)} 處（例如「{half[0]}」）：中文句子用全形「，。：；！？（）」。")
    md = [l for l in t.split("\n") if re.match(r"\s*(#{1,6}\s|[-*]\s|\d+\.\s)", l)]
    if md:
        out.append(f"Markdown 標題或條列 {len(md)} 行（例如「{md[0].strip()[:20]}」）：要貼到 FB、IG、LINE 這類純文字平台時改成一般段落。")
    resid = re.findall(r"utm_source=|turn0search|citeturn|以下是(?:修改|改寫|調整)後|希望(?:這|以上)?(?:對你|對您)有(?:所)?幫助|如果需要我|你可以直接複製", t)
    if resid:
        out.append("AI 工具或對話殘留：" + "、".join(sorted(set(resid))) + "，發布前刪掉。")
    hold = re.findall(r"\[(?:在這裡|此處|請)?插入[^\]]*\]|（此處填入[^）]*）|XX公司|ＸＸ", t)
    if hold:
        out.append("模板佔位文字沒填：" + "、".join(hold[:3]) + "。")
    if not out:
        return False
    print(f"\n## {num}. 格式與殘留（照說人話的規則，不計分）\n")
    for o in out:
        print("- " + o)
    return True


SPOKEN_WORDS = ["所以", "因為", "但是", "其實", "就是", "然後"]


def spoken_line(t, n, kind):
    """真人說話（議會、立法院、會議逐字稿）跟日常說話文字的口語連接，每千字次數，跟這份並排（參考）。"""
    p = os.path.join(HERE, "norms_spoken.json")
    if not os.path.exists(p):
        return
    R = json.load(open(p, encoding="utf-8"))["rates"]
    src = {}
    for k, v in R.items():
        if "・" in k:
            src.setdefault(k.split("・")[0], []).append(v)
    if not src:
        return
    sp = {w: sum(sum(v[w] for v in vs) / len(vs) for vs in src.values()) / len(src) / 10 for w in SPOKEN_WORDS}
    wr = {w: R.get("日常說話文字", {}).get(w, 0) / 10 for w in SPOKEN_WORDS}
    me = {w: (t.count(w) * 1000 / max(1, n)) for w in SPOKEN_WORDS}
    print("\n真人說話時常用的連接（每千字，參考）：")
    print("| 詞 | " + " | ".join(SPOKEN_WORDS) + " |\n|---|" + "---|" * len(SPOKEN_WORDS))
    print("| 真人說話（議會、立法院、會議逐字稿） | " + " | ".join(f"{sp[w]:.1f}" for w in SPOKEN_WORDS) + " |")
    print("| 日常說話文字 | " + " | ".join(f"{wr[w]:.1f}" for w in SPOKEN_WORDS) + " |")
    print("| 這份 | " + " | ".join(f"{me[w]:.1f}" for w in SPOKEN_WORDS) + " |")
    print("寫成文字時，真人用得比說話時少，大約是說話的一半以下；完全沒用到時，可以看看哪裡本來就該用「因為」「所以」「但是」接起來。不要為了數字硬加。")


CASUAL_LABEL = {
    "casual": ("norms_casual.json", "人寫口語文", "2012–2021 台灣部落格與論壇，部落格文章為主"),
    "speech": ("norms_speech.json", "人寫日常說話", "2012–2021 台灣部落格與論壇裡比較像平常說話的文章，已去掉業配、圖說、條列、店家資訊"),
}


def formal_section(t, f):
    """解說腔（ChatGPT 型）四項：無人稱、書面連接偏多、「如果」偏多、「可以／能夠」偏多（build_formal.py 的門檻）。
    回傳中了幾項；沒有基準檔時回傳 None。印在核心項目底下。"""
    p = os.path.join(HERE, "norms_formal.json")
    if not os.path.exists(p):
        return None
    th = json.load(open(p, encoding="utf-8"))["threshold"]
    n = max(1, f.get("cjk_chars", len(re.findall(f"[{F.CJK}]", t))))
    if n < 150:  # 短稿沒有「我」、沒有語氣詞很正常，一個「如果」就超標，不算解說腔
        return None
    ruguo = t.count("如果") * 1000 / n
    rows = [("無人稱（沒有「我」也沒有語氣詞）", f.get("w:我", 0) == 0 and f.get("語氣詞合計", 0) == 0, "我 0、語氣詞 0" if f.get("w:我", 0) == 0 and f.get("語氣詞合計", 0) == 0 else "有"),
            ("書面連接（因此、而、並、此外、然而……）", f.get("常見書面連接合計", 0) > th["書面"], f"{f.get('常見書面連接合計', 0):.1f}（上限 {th['書面']:.1f}）"),
            ("「如果」", ruguo > th["如果"], f"{ruguo:.1f}（上限 {th['如果']:.1f}）"),
            ("「可以／能夠」", f.get("s:可以/能夠", 0) > th["可以"], f"{f.get('s:可以/能夠', 0):.1f}（上限 {th['可以']:.1f}）")]
    k = sum(1 for _, hit, _ in rows if hit)
    print(f"\n解說腔（ChatGPT 型，每千字）：中了 {k} 項" + ("，要改" if k >= 3 else "，接近" if k == 2 else ""))
    print("\n| 項目 | 這份 | 中了嗎 |\n|---|---|---|")
    for name, hit, shown in rows:
        print(f"| {name} | {shown} | {'⚠' if hit else ''} |")
    if k >= 2:
        print("\n解說腔是太正式、像在回答問題：沒有「我」、一直「如果……可以……」、句句用「此外、因此」接。"
              "改法：用作者自己的口氣講，把「如果您……可以……」改成作者實際怎麼做，連接詞換成「因為、所以、不過、但是」。")
    return k


def stock_section(t):
    """心得腔（現代模型型）九項（structure.STOCK）：中 2 項以上要改。印在核心項目底下，回傳中了幾項。"""
    import structure as ST
    hits = ST.stock(t)
    p = os.path.join(HERE, "norms_stock.json")
    V = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
    print(f"\n心得腔（現代模型型）：中了 {len(hits)} 項" + ("，要改" if len(hits) >= 2 else "，順手看一下" if hits else ""))
    if hits:
        rate = (V or {}).get("groups", {}).get("人寫 B（沒看過）", {}).get("item", {})
        print("\n| 項目 | 這份的句子 | 台灣人寫有這樣寫的 | 改法 |\n|---|---|---|---|")
        for name, ev, fix in hits:
            r = rate.get(name)
            print(f"| {name} | {ev[:60]} | {f'{r:.1%}' if r is not None else ''} | {fix} |")
    if len(hits) >= 2:
        print("\n心得腔是現在的模型寫心得、遊記、貼文的樣子：照時間排好，最後用「讓我學到、很值得、希望下次」收尾，中間放一句「那一刻」或「這時才發現」。"
              "標點和用詞都很乾淨，所以清單腔、解說腔都量不到。改法是把收尾那幾句刪到停在最後一件具體的事，頓悟句直接講那件事；"
              "作者真的有的感受和打算要留，寫成具體的事。")
    return len(hits)


# 11/20 晚上：排除「如果想讓它……」這種講使用者想做什麼的句子（作者自己打的安裝說明被誤判）。人寫誤標 3.0% → 2.9%，過去 Claude 稿 35.3% 不變
EXPLAIN_RX = re.compile(r"主要(是|就是|在)|是想|(?<!如果)(?<!要是)(?<!假如)想要?讓(?![它他她你我])|希望讓|目的(是|在)|是為了|用來|就改|後來就|所以就|於是就|改成|改用|改為|換成|換用")


def explain_section(t):
    """說明理由腔（11/20 加）：一直交代「主要是想、是想讓、是為了、用來」和「後來就改成、換成」。
    台灣人寫日常文章 250 字以上，2 處以上而且每千字 2 處以上的只有 2.4%（沒用來訂規則的 3,983 篇）；
    過去的 Claude 稿 35%，Claude 寫的 README 每千字 4.5 處。回傳有沒有超標。"""
    hits = [(m.start(), m.group(0)) for m in EXPLAIN_RX.finditer(t)]
    n = max(1, len(re.findall(f"[{F.CJK}]", t)))
    short_text = n < 150  # 11/20：一百多字的短文，「主要是用來」兩處就被判要改。短文一兩處是口氣，不算超標
    over = len(hits) >= 2 and len(hits) * 1000 / n >= 2.0 and not short_text
    print(f"\n說明理由腔：{len(hits)} 處（每千字 {len(hits) * 1000 / n:.1f}，台灣人寫平均 0.3）" + ("，要改" if over else "，不到 150 字，一兩處不算" if short_text and len(hits) >= 2 else ""))
    if hits and over:
        for pos, w in hits:
            a = max(0, pos - 18)
            print(f"- 「{w}」：……{t[a:pos + 14].strip()}……")
        print("\n台灣人寫文章很少交代自己為什麼這樣做、想達到什麼、後來改成什麼。改法：直接講做了什麼、結果怎樣；"
              "理由真的重要才留一個，「主要是想讓」「後來就改成」拿掉，換成那件事本身（例如「後來就改成用數字比」→「後來用數字比」）。")
    return over



def clause_section(t):
    """簡寫腔（11/20 晚上加）：逗號、句號之間 15 個漢字以上的長子句太少。真人會把一件事一口氣講完整，
    AI 被要求「寫自然」或去 AI 味改寫時，會把每一段都切短、把話講省。門檻與驗證在 norms_clause.json。回傳有沒有低於門檻。"""
    p = os.path.join(HERE, "norms_clause.json")
    if not os.path.exists(p):
        return False
    N = json.load(open(p, encoding="utf-8")); th = N["norms"]["p10"]; L = N["norms"]["long"]
    parts = [c.strip() for c in re.split(r"[，。！？；：、,!?;:\n…~～]+", t) if re.search(f"[{F.CJK}]", c)]
    lens = [len(re.findall(f"[{F.CJK}]", c)) for c in parts]
    if len(lens) < 8:
        return False
    r = sum(1 for x in lens if x >= L) / len(lens)
    low = r < th
    print(f"\n簡寫腔：長子句（{L} 字以上）佔 {r:.0%}，台灣人寫中位數 {N['norms']['p50']:.0%}，低於 {th:.0%} 算太簡寫" + ("，要改" if low else ""))
    if low:
        sents = [s for s in re.split(r"(?<=[。！？])|\n", t) if len(re.findall(f"[{F.CJK}]", s)) >= 12]

        def chop(s):
            c = [len(re.findall(f"[{F.CJK}]", x)) for x in re.split(r"[，、；：,;:]+", s) if re.search(f"[{F.CJK}]", x)]
            return (len(c), -max(c)) if c else (0, 0)
        for s in sorted(sents, key=chop, reverse=True)[:3]:
            print(f"- 切很碎的句子：{s.strip()[:70]}")
        print("\n每一段都講得很短、把話講省，是 AI 被要求「寫自然」或去 AI 味時的樣子（現代稿要求寫自然的長子句中位數 12%，一般寫法 19%）。"
              "改法：把同一件事講完整，誰、在哪、做了什麼、結果放在同一個子句（「錯的人少了」→「這題寫錯的人少了」），"
              "動詞、受詞、「把」、「的時候」不要為了精簡省掉。不要只刪逗號湊數字。")
    return low


def structure_section(t, num, who="人寫口語文", key="人寫口語"):
    """整篇結構（structure.py）：開頭帽子、總結或展望收尾、首先其次、編號清單，跟台灣人寫與 AI 的比例並排。不計分。"""
    p = os.path.join(HERE, "norms_structure.json")
    if not os.path.exists(p):
        return False
    import structure as ST
    N = json.load(open(p, encoding="utf-8"))
    f = ST.feats(t)
    h = N.get(key) or N.get("人寫口語", {})
    ai = {k: v for k, v in N.items() if not k.startswith("人寫")}
    print(f"\n## {num}. 整篇結構（跟台灣{who}和 AI 比，不計分）\n")
    found = False
    for k in ("開頭帽子", "總結收尾", "展望收尾", "首先其次", "第一第二"):
        if f.get(k) and k in h:
            found = True
            ais = "、".join(f"{g} {v[k]:.0%}" for g, v in ai.items() if k in v)
            print(f"- 有「{k}」：台灣{who}只有 {h[k]:.1%} 這樣寫（{ais}）。")
    for k, name in (("編號清單行", "編號或符號清單"), ("小標題行", "小標題")):
        v = h.get(k)
        if v and f.get(k, 0) > v["p90"] and f.get(k, 0) > 0:
            found = True
            print(f"- {name}每千字 {f[k]:.1f} 行，高於九成台灣{who}（第 90 百分位 {v['p90']:.1f}）。")
    if not found:
        print("開頭、結尾、清單都在台灣人寫的常見範圍。")
    else:
        print("\n人寫的開頭多半直接從事情講起，結尾停在最後一件具體的事或一句感想；清單能改成句子就改。")
    return True


def specificity_section(t, num, who="人寫口語文", key="人寫口語"):
    """具體細節密度（specificity.py，CKIP 專有名詞辨識）：要有 tw-voice-nlp 環境；沒有就略過。不計分。
    細節偏少時，列成要作者補的問題，不替作者編。"""
    import subprocess, tempfile
    py = os.environ.get("TW_VOICE_NLP_PY", os.path.expanduser(r"~\.local\share\tw-voice-nlp\Scripts\python.exe"))
    p = os.path.join(HERE, "norms_specificity.json")
    if not (os.path.exists(py) and os.path.exists(p)):
        return False
    if len(re.findall(f"[{F.CJK}]", t)) < 300:  # 太短的稿子每千字密度不穩，也不值得等模型載入
        return False
    N = json.load(open(p, encoding="utf-8")).get(key)
    if not N:
        return False
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(t[:3000])
        tmp = f.name
    try:
        r = subprocess.run([py, "-W", "ignore", os.path.join(HERE, "specificity.py"), tmp], capture_output=True, text=True,
                           encoding="utf-8", timeout=300, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        x = json.loads(r.stdout[r.stdout.find("{"):])
    except Exception:
        return False
    finally:
        os.unlink(tmp)
    print(f"\n## {num}. 具體細節（每千字幾個人名、地名、店名、數量、時間；跟台灣{who}比，不計分）\n")
    print(f"| 項目 | 這份 | {who}中位數 | {who}第 25 百分位 |\n|---|---|---|---|")
    low = []
    for k in ("專名", "數量", "時間", "合計"):
        v = N[k]
        print(f"| {k} | {x[k]:.1f} | {v['p50']:.1f} | {v['p25']:.1f} |")
        if k != "合計" and x[k] < v["p25"]:
            low.append(k)
    if len(low) >= 2 or x["合計"] < N["合計"]["p25"]:
        ask = {"專名": "在哪裡、跟誰、哪家店或哪個系統", "數量": "幾個人、多少錢、花了多久、第幾次", "時間": "哪一天、幾月、早上還是晚上、過了多久"}
        print(f"\n細節偏少（{'、'.join(low) or '合計'}低於四分之三的{who}）。台灣真人每千字約有 3 個時間、10 個左右的人名地名店名；"
              "AI 稿常常一個時間都沒有（ChatGPT 與 Claude 稿的時間中位數都是 0）。這些只能作者補，不能編。"
              "交稿時在最後列出要問作者的問題，例如：" + "；".join(ask[k] for k in (low or ["專名", "數量", "時間"]) if k in ask) + "。")
    return True


def casual(a, t, n, kind="casual"):
    """口語模式（casual＝部落格文章基準；speech＝日常說話基準）。
    計分只看驗證過的 6 項：超過人寫 p90 算一個問題，2 個以上就該修。
    p75–p90 之間標「接近上限」，不計分；口語感、句子節奏、句型用詞、同主題參考、格式殘留都只當線索。驗證數字讀基準檔的 meta。"""
    fn, who, desc = CASUAL_LABEL[kind]
    allN = json.load(open(os.path.join(HERE, fn), encoding="utf-8"))
    N = allN["norms"]
    val = allN.get("meta", {}).get("validation", {})
    f = F.feats(t)
    f["口語連接合計"] = sum(t.count(w) for w in SPOKEN_CONN) * 1000 / max(1, n)
    sents = [s.strip() for s in re.split(r"(?<=[。！？；])|\n", t) if len(re.findall(f"[{F.CJK}]", s)) >= 4]
    print(f"# 檢查結果：{os.path.basename(a.path)}（{n} 個漢字，對照{who} {allN['n']:,} 篇：{desc}）\n")
    if n < 150:
        print(f"這份只有 {n} 個漢字，每千字比例很不穩（一個冒號就是每千字好幾次），下面的數字只當參考；"
              "單一項目只出現 1 次的不算超標，解說腔也不算。重點看第 3 節的句型與用詞，以及讀稿時看的事。\n")
    print("## 1. 核心項目（AI 稿最常超標的地方）\n")
    print("| 項目 | 這份 | 人寫中位數 | 上限（九成人寫在這以下） | 判斷 |\n|---|---|---|---|---|")
    problems, flagged, near = 0, [], []
    for k in CASUAL_HI:
        v, x = N[k], f.get(k, 0)
        r = rank(v, x)
        once = round(x * n / 1000) < 2  # 整份只出現 1 次：短稿裡比例會被放大，不算超標
        if x > v["p90"] and x > 0 and once:
            mark = "△ 只出現 1 次，不算"
        elif x > v["p90"] and x > 0:
            mark = f"⚠ 超過上限（高於約 {r}% 人寫）" if r is not None else "⚠ 超過上限"
            problems += 1; flagged.append(k)
        elif "p75" in v and x > v["p75"] and x > 0:
            mark = f"△ 接近上限（高於約 {r}% 人寫）"
            near.append(k)
        else:
            mark = ""
        print(f"| {NAMES[k]} | {x:.1f} | {v['p50']:.1f} | {v['p90']:.1f} | {mark} |")
    for k in flagged:
        print(f"\n{NAMES[k]}（超過上限）出現最多的句子：")
        show_hits(k, sents, 4)
    for k in near:
        print(f"\n{NAMES[k]}（接近上限）出現最多的句子：")
        show_hits(k, sents, 2)
    if near:
        print(f"\n接近上限不算問題，{who}也常有一兩項。", end="")
        if val:
            print(f"但{who}同時有 3 項以上超過或接近上限的只有 {val['human_over_near3']:.0%}，"
                  f"過去的 AI 稿是 {val['ai_over_near3']:.0%}。這份是 {problems + len(near)} 項。")
        else:
            print()
    formal = formal_section(t, f)
    stock_k = stock_section(t)
    expl = explain_section(t)
    short = clause_section(t)

    print("\n## 2. 參考：口語感與句子節奏（不計分，只是線索，不要為了數字硬改）\n")
    print(f"| 項目 | 這份 | {who}中位數 | 這份在{who}中的位置 |\n|---|---|---|---|")
    for k, name in CASUAL_INFO:
        if k not in N:
            continue
        if k.startswith("句長") and k not in f:
            print(f"| {name} | — | {N[k]['p50']:.1f} | 句號、問號、驚嘆號、換行切出來不到 3 句，不算 |")
            continue
        v, x = N[k], f.get(k, 0)
        r = rank(v, x)
        if x == 0 and v["present"] < 1:
            pos = f"沒有用到（{v['present']:.0%} 的{who}有用）"
        elif r is None:
            pos = ""
        elif r == 0:
            pos = "在人寫最低的 5% 以內"
        elif r >= 95:
            pos = "在人寫最高的 5% 以內"
        else:
            pos = f"高於約 {r}% 人寫"
        print(f"| {name} | {x:.2f} | {v['p50']:.2f} | {pos} |" if k == "句長變異係數" else f"| {name} | {x:.1f} | {v['p50']:.1f} | {pos} |")
    hints = []
    r = rank(N.get("句長變異係數", {}), f.get("句長變異係數", 0))
    if r is not None and "句長變異係數" in f and r <= 10:
        lens = [len(re.findall(f"[{F.CJK}A-Za-z0-9]", s)) for s in F.sentences(t)]
        share = "95% 以上" if r == 0 else f"約 {100 - r}%"
        hints.append(f"句子長短太平均：{who}有 {share} 比這份更有長短變化。各句字數依序是 "
                     + "、".join(str(x) for x in lens[:20]) + ("……" if len(lens) > 20 else "")
                     + "。人寫的長短變化來自內容本身，例如一句短短的反應、一段一口氣講完的經過；照內容去調，不要為了數字硬拆或硬併。")
    r = rank(N.get("w:我", {}), f.get("w:我", 0))
    if r is not None and f.get("w:我", 0) > 0 and r >= 90:
        hints.append(f"「我」偏多：高於約 {r}% {who}。上下文看得出是誰在做事時，可以省掉主詞「我」。")
    for h in hints:
        print("\n- " + h)
    spoken_line(t, n, kind)
    phrase_section(t, "casual", 3)
    num = 4
    import phrases as _P
    _pp = os.path.join(HERE, "norms_phrases.json")
    _J = json.load(open(_pp, encoding="utf-8"))["items"] if os.path.exists(_pp) else None
    rare_n = sum(1 for i in _P.hits(t) if _P.LEXICON[i][0] in _P.AI_CATS and _J[i]["casual"] < 0.01) if _J else 0
    if getattr(a, "topic", None):
        import topic
        topic.report(a.topic.split(","), t, num=num)
        num += 1
    if structure_section(t, num, who, "人寫日常說話" if kind == "speech" else "人寫口語"):
        num += 1
    if specificity_section(t, num, who, "人寫日常說話" if kind == "speech" else "人寫口語"):
        num += 1
    if format_section(t, num):
        num += 1
    ftxt = f"{formal} 項" if formal is not None else "沒算（不到 150 字，太短算不準）"
    print(f"\n## {num}. 結論：清單腔 {problems} 項、解說腔 {ftxt}、心得腔 {stock_k} 項、幾乎沒人用的說法 {rare_n} 項\n")
    need = problems >= 2 or (formal is not None and formal >= 3)
    # 11/19 修：以前只看兩種腔的分數，稿子有好幾項「幾乎沒人用」的套語還是寫「常見範圍、小修就好」，跟第 3 節矛盾
    # 11/19 晚上加心得腔：現在的模型寫的心得、貼文，前兩種腔都量不到（第七輪 10 段全部判「不用改」）
    if need:
        print("要改。" + (f"另外心得腔中了 {stock_k} 項，收尾和頓悟句也要一起改（第 1 節）。" if stock_k >= 2 else ""))
    elif stock_k >= 2:
        print(f"要改。清單腔、解說腔沒超標，但心得腔中了 {stock_k} 項（第 1 節），照表上的改法改。")
    elif expl:
        print("要改。三種腔的分數沒超標，但說明理由腔超標（第 1 節），把交代理由、目的、改法的句子改成直接講那件事。")
    elif short:
        print("要改。三種腔的分數沒超標，但簡寫腔低於門檻（第 1 節），把切碎、講省的句子講完整。")
    elif rare_n >= 2:
        print(f"要改。三種腔的分數沒超標，但有 {rare_n} 項台灣人幾乎不用的套語或句型（第 3 節），照第 3 節改。")
    else:
        print("清單腔、解說腔、心得腔都在台灣人寫的常見範圍，" + ("但解說腔接近上限，順手看一下。" if formal == 2 else "照上面的線索小修就好。")
              + ("心得腔中的那 1 項也看一下。" if stock_k == 1 else ""))
        print("就算判「常見範圍」，流程裡「沒有內容的客套和框架」那一串（空洞的總結、號召、空泛的自我評價）看到還是要刪。")
    if val:
        print(f"\n清單腔（Claude 型）2 項以上就該修：保留的{who}問題數中位數 {val['human_median']}，過去的 Claude 稿 {val['ai_median']}；"
              f"Claude 稿 {val['ai_flag2']:.0%} 會被標出，{who} {val['human_flag2']:.0%}。")
    fp = os.path.join(HERE, "norms_formal.json")
    if os.path.exists(fp):
        v = json.load(open(fp, encoding="utf-8"))["validation"]
        print(f"解說腔（ChatGPT 型）3 項以上就該修：ChatGPT 回答 {v['gpt_ge3']:.0%} 會被標出，保留的台灣人寫口語文 {v['human_ge3']:.0%}。"
              "兩種腔分開算，是因為清單腔抓不到 ChatGPT（它幾乎不用清單標點和否定詞），解說腔也抓不到 Claude。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--kind", default=None, choices=["abstract", "body", "casual", "speech"],
                    help="abstract／body＝學術；casual＝作業、心得、報告說明（部落格文章基準）；speech＝貼文、給朋友看的心得（日常說話基準）。"
                         "不填就依長度判斷 abstract／body")
    ap.add_argument("--topic", default=None, help="口語模式才用：主題關鍵字，用逗號分隔，例如 玉山,登山；會列出語料裡同主題真人文章常提到的東西與常用說法")
    a = ap.parse_args()
    # 「（需作者補充：……）」「〔需查證來源〕」是留給作者的佔位，不是正文，量之前拿掉（佔位裡的冒號、括號會灌高清單腔）
    raw = re.sub(r"（需作者(補充|確認)[^）]*）|〔需查證[^〕]*〕|（此處缺來源[^）]*）", "", read_text(a.path))
    if a.kind in ("casual", "speech"):
        t = re.sub(r"[ \t]+", " ", raw)
        return casual(a, t, len(re.findall(f"[{F.CJK}]", t)), a.kind)
    allN = json.load(open(os.path.join(HERE, "norms.json"), encoding="utf-8"))
    t = re.sub(r"[ \t]+", " ", raw)
    n = len(re.findall(f"[{F.CJK}]", t))
    kind = a.kind or ("abstract" if n < 1200 else "body")
    N = allN[kind]["norms"]
    f = F.feats(t)
    sents = [s.strip() for s in re.split(r"(?<=[。！？；])|\n", t) if len(re.findall(f"[{F.CJK}]", s)) >= 4]
    problems = 0
    print(f"# 檢查結果：{os.path.basename(a.path)}（{n} 個漢字，對照人寫{'摘要' if kind == 'abstract' else '正文'} "
          f"{allN[kind]['n']:,} {'份' if kind == 'abstract' else '段'}）\n")

    print("## 1. 人寫學術文字幾乎不用的詞句\n")
    found = False
    for k, v in sorted(N.items(), key=lambda kv: kv[1]["present"]):
        if k[:2] in ("w:", "p:", "s:") and k[2:] in RARE_OK and v["present"] < 0.05 and f.get(k, 0) > 0:
            pat = pattern_for(k)
            hits = [s for s in sents if pat and re.search(pat, s)]
            print(f"- 「{k[2:]}」：人寫只有 {v['present']:.0%} 用過，這份 {len(hits)} 句")
            for s in hits[:4]:
                print(f"    · {s[:90]}")
            problems += 1; found = True
    if not found:
        print("沒有。")
    print("\n## 2. 核心特徵\n")
    print("| 項目 | 這份 | 人寫中位數 | 人寫正常範圍 | 判斷 |\n|---|---|---|---|---|")
    flagged = []
    for k in CORE_HI + CORE_LO:
        if k not in N or k not in f:
            continue
        v, x = N[k], f[k]
        once = (k.startswith("p:") or k == "否定與限定詞合計") and round(x * n / 1000) < 2  # 整份只出現 1 次不算
        bad = (k in CORE_HI and x > v["p95"] and x > 0 and not once) or (k in CORE_LO and x < v["p10"])
        rng = f"≤ {v['p95']:.1f}" if k in CORE_HI else f"≥ {v['p10']:.1f}"
        mark = '⚠ 偏高' if bad and k in CORE_HI else ('⚠ 偏低' if bad else '')
        # 接近上限／下限：基準有 p75、p25 時才顯示（重算後的學術基準才有），不計分
        if not bad and k in CORE_HI and "p75" in v and x > v["p75"] and x > 0:
            mark = "△ 接近上限"
        if not bad and k in CORE_LO and "p25" in v and x < v["p25"]:
            mark = "△ 接近下限"
        print(f"| {NAMES[k]} | {x:.1f} | {v['p50']:.1f} | {rng} | {mark} |")
        if bad:
            problems += 1; flagged.append(k)
    for k in flagged:
        if k in PATS:
            hits = [s for s in sents if re.search(PATS[k], s)]
            print(f"\n{NAMES[k]} 出現最多的句子：")
            for s in sorted(hits, key=lambda s: -len(re.findall(PATS[k], s)))[:4]:
                print(f"    · {s[:90]}")
    if "句長平均" in flagged or "短句比例(<15字)" in flagged:
        short = [s for s in sents if len(re.findall(f"[{F.CJK}A-Za-z0-9]", s)) < 15]
        print("\n可以併回前後句的短句：")
        for s in short[:6]:
            print(f"    · {s[:60]}")
    phrase_section(t, "abstract" if kind == "abstract" else "body", 3)
    num = 5 if format_section(t, 4) else 4
    print(f"\n## {num}. 問題數：{problems}\n")
    print("保留的人寫論文片段中位數是 1，過去的 Claude 稿是 7。3 個以上就該修：Claude 稿 91% 會被標出，人寫片段 20%"
          "（資訊、管理、經濟、法律類大多 4–11%；文學、哲學、史學、宗教類 30–80%，這類論文數字只當參考）。")

if __name__ == "__main__":
    main()

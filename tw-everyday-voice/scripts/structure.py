"""整篇結構特徵（說人話的「時代大帽子」「罐頭收尾」「硬切三段」等規則，用資料驗證）。
每篇算：
  開頭帽子：前兩句（最多 100 字，第一句常是標題）有「在這個……的時代、隨著……的發展、近年來、現今」這類開場
  總結收尾：最後兩句有「總之、總而言之、總的來說、綜上所述、整體來說、總結、簡單來說」
  展望收尾：最後兩句有「未來、期待、希望、讓我們、一起、相信、持續、繼續」，而且是正面或號召語氣（含驚嘆號或「吧」不算）
  問句收尾：最後一句以問號結尾
  首先其次：同時有「首先」與「其次／再者／最後」
  第一第二：同時有「第一」與「第二」
  編號清單：行首是 1. 2. 一、 (1) ① 或 ●★-* 這類符號的行數
  小標題：短行（≤ 15 字）以冒號結尾或 # 開頭的行數
  段落長度變化：各段字數的變異係數
函式 feats(text) 給 check.py 與驗證用。"""
import re

CJK = "一-鿿"
HAT = re.compile(r"(在(這個|現今|當今|如今|現代|數位|資訊|快速|瞬息萬變)[^，。！？]{0,14}(時代|社會|世界|環境)|隨著[^，。！？]{1,24}(發展|普及|進步|興起|變遷|演進|成長)|近年來|近幾年來|現今|當今社會|如今)")
SUMUP = re.compile(r"(總之|總而言之|總的來說|綜上所述|整體來說|整體而言|總結來說|總結而言|總結一下|簡單來說|一言以蔽之)")
OUTLOOK = re.compile(r"(未來|期待|期許|希望|讓我們|一起|相信|持續|繼續|邁向|迎接|展望)")
FIRSTLY = re.compile(r"首先")
SECONDLY = re.compile(r"(其次|再者|最後)")
ORD1, ORD2 = re.compile(r"第一[，、：:]?"), re.compile(r"第二[，、：:]?")
LISTLINE = re.compile(r"^\s*(\d{1,2}[.、)）]|[（(]\d{1,2}[)）]|[一二三四五六七八九十]{1,2}[、.]|[①-⑳]|[●★☆◆◇■□▶►•\-*＊])")
HEADING = re.compile(r"^\s*(#{1,6}\s|[^。！？\n]{1,15}[：:]\s*$)")


def sentences(t):
    return [s.strip() for s in re.split(r"(?<=[。！？!?])|\n+", t) if len(re.findall(f"[{CJK}]", s)) >= 3]


def feats(t):
    t = t.strip()
    ss = sentences(t)
    first = "".join(ss[:2])[:100] if ss else ""  # 前兩句：第一句常是標題
    tail = "".join(ss[-2:]) if ss else ""
    last = ss[-1] if ss else ""
    paras = [p for p in re.split(r"\n\s*\n|\n", t) if len(re.findall(f"[{CJK}]", p)) >= 10]
    lens = [len(re.findall(f"[{CJK}]", p)) for p in paras]
    cv = 0.0
    if len(lens) >= 3:
        m = sum(lens) / len(lens)
        cv = (sum((x - m) ** 2 for x in lens) / len(lens)) ** 0.5 / max(1, m)
    lines = t.split("\n")
    n = max(1, len(re.findall(f"[{CJK}]", t)))
    return {
        "開頭帽子": bool(HAT.search(first)),
        "總結收尾": bool(SUMUP.search(tail)),
        "展望收尾": bool(OUTLOOK.search(tail)) and not re.search(r"[吧啦喔呢]", tail),
        "問句收尾": last.endswith(("？", "?")),
        "首先其次": bool(FIRSTLY.search(t) and SECONDLY.search(t)),
        "第一第二": bool(ORD1.search(t) and ORD2.search(t)),
        "編號清單行": sum(1 for l in lines if LISTLINE.match(l)) * 1000 / n,
        "小標題行": sum(1 for l in lines if HEADING.match(l)) * 1000 / n,
        "段落數": len(paras),
        "段長變異係數": round(cv, 3),
    }


# ── 心得腔（現代模型型）──────────────────────────────────────────────
# 11/19 晚上加。第七輪盲評發現：現在的 Claude（Opus、Sonnet、Haiku）寫的心得、遊記、貼文，清單腔和解說腔都抓不到，
# 程式判「不用改」，空洞的總結收尾就留下來了。用 46 段現代模型日常稿（評測/現代稿 的 dev）對照台灣人寫的口語文
# （驗證用的 20%，長度 250–800 字、去掉延伸閱讀這類尾巴）找出下面九項（11/20 下午改成十項）；中 2 項以上就要改。
# 另外 24 段現代稿（test）和另一批人寫文章只用來驗證，沒有用來挑項目。數字在 norms_stock.json。
JUNK = re.compile(r"https?://|延伸閱讀|相關文章|文章來源|轉載|粉絲團|粉絲專頁|FB|IG|instagram|地址|電話|營業時間|部落格|訂閱|按讚|分享給|留言|版權|Copyright|標籤|tag", re.I)


def body(t):
    """去掉文章最後的尾巴（延伸閱讀、店家資訊、粉專連結、太短的行），收尾看的是正文最後兩句。"""
    # 有尾巴的字（電話、留言、部落格）但很長的行是正文，不能丟：第八輪改寫者發現一段講「打電話」的收尾段整段被丟掉
    ls = t.strip().split("\n")
    while ls and ((JUNK.search(ls[-1]) and len(re.findall(f"[{CJK}]", ls[-1])) <= 30) or len(re.findall(f"[{CJK}]", ls[-1])) < 6):
        ls.pop()
    return "\n".join(ls)


def _tail(t, k=2):
    return "".join(sentences(body(t))[-k:])


def _even_paras(t):
    f = feats(t)
    return 3 <= f["段落數"] <= 6 and f["段長變異係數"] < 0.35


# (名稱, 在哪裡找, 正規式或函式, 改法)
STOCK = [
    ("總結收尾", "收尾", SUMUP, "刪掉這句，文章停在最後一件具體的事。"),
    ("心得收尾（讓我學到、收穫、值得、成長）", "收尾",
     re.compile(r"讓我(學到|明白|體會|了解|理解|知道|發現|意識到|更加|更|重新|看見|懂得|感受到)|學到(了|最|很多)|收穫|值得|意義|成長|難忘|這段(經驗|經歷|時間|日子|旅程)|一路走來|回想起來|回頭看"),
     "刪掉。作者真的學到一件具體的事，就直接寫那件事（學到什麼、哪裡用得上）。"),
    ("展望收尾（下次、希望、未來、期待）", "收尾", re.compile(r"下次|下一次|希望|未來|以後(我|會|要|也|還|一定|再)|期待|繼續|之後(我|會|也|還)"),
     "沒有具體打算就刪；有的話寫成實際要做的事（下週要做什麼）。"),
    ("感謝或祝福收尾", "收尾", re.compile(r"謝謝|感謝|祝"), "貼文、信件可以留一句；心得、作業裡的感謝收尾多半刪掉。"),
    ("「那一刻、那個當下」", "全文", re.compile(r"那一刻|那個當下|那一瞬間|那瞬間"), "直接講那時候發生的事，或改成「那時候」。"),
    ("「才發現、才明白」的頓悟句", "全文", re.compile(r"(?<![他她人家闆媽爸學師方哥姐弟妹])才(真正|真的)?(發現|明白|理解|知道|體會|意識到)"), "直接講發現的那件事，不用鋪「做了才發現」。"),
    ("「原本以為……沒想到」", "全文", re.compile(r"(原本|本來|原先)(以為|覺得|想說)[^。！？]{0,40}(沒想到|結果|才發現|後來發現)"), "直接講結果；前後反差是真的才留。"),
    # 11/20 下午放寬：以前要「一開始、後來、最後」三個都有，README 那種「一開始只是覺得……後來我……」漏掉。
    # 只看一開始＋後來：台灣人寫 1.0%，現代稿 16%、盲評新題 AI 稿 33%（三個都有時人寫 0.3%、現代稿 9%）。
    ("照「一開始……後來……」講成一個過程", "全文", lambda t: bool(re.search(r"一開始|剛開始", t) and re.search(r"後來", t)),
     "不用照時間從頭講，直接講那件事現在怎樣、覺得哪裡怪；最有話講的那段多寫，其他一句帶過。"),
    # 11/20 下午加：開頭兩段就用「一開始、剛開始」：台灣人寫 0.8%，現代稿 27%、盲評新題 AI 稿 42%。
    ("開頭就講「一開始」", "全文", lambda t: bool(re.search(r"一開始|剛開始", "".join([p for p in t.split("\n") if p.strip() and not p.lstrip().startswith("#")][:2])[:200])),
     "第一句直接講事情本身或你覺得怎樣，不要從「一開始只是……」講起。"),
    ("段落一樣長（3–6 段，長度差不多）", "全文", _even_paras, "照內容分段：最有話講的那段可以很長，交代一句的可以很短，也可以併段。"),
]


def stock(t):
    """回傳中了哪些項目：[(名稱, 證據句或空字串, 改法)]。"""
    out = []
    tl, tb = _tail(t), body(t)
    for name, where, rx, fix in STOCK:
        if callable(rx) and not hasattr(rx, "search"):
            if rx(tb):
                out.append((name, "", fix))
            continue
        src = tl if where == "收尾" else tb
        m = rx.search(src)
        if m:
            ev = next((s for s in sentences(src) if rx.search(s)), m.group())
            out.append((name, ev, fix))
    return out


if __name__ == "__main__":
    import sys, json
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(feats(open(sys.argv[1], encoding="utf-8").read()), ensure_ascii=False, indent=1))

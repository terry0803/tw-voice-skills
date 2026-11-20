"""具體細節密度：用 CKIP Transformers（albert-tiny）的專有名詞辨識，數每千字有幾個具體細節。
  專名：人名、地名、機構、設施（店、車站）、產品、事件、作品（PERSON、GPE、LOC、ORG、FAC、PRODUCT、EVENT、WORK_OF_ART、NORP）
  數量：數字、數量、金額、百分比、序數（CARDINAL、QUANTITY、MONEY、PERCENT、ORDINAL）
  時間：日期、時間（DATE、TIME）
要用有 ckip-transformers 的 Python，用環境變數 TW_VOICE_NLP_PY 指定
用法：
  python specificity.py 稿子.txt                 → 印出這份的密度（check 報告用）
  python specificity.py --norms                  → 算人寫與 AI 各組的分布，寫 norms_specificity.json 與 分析/具體細節_人寫與AI.md"""
import os, sys, re, json, glob, random, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
CJK = re.compile("[一-鿿]")
KINDS = {"專名": {"PERSON", "GPE", "LOC", "ORG", "FAC", "PRODUCT", "EVENT", "WORK_OF_ART", "NORP"},
         "數量": {"CARDINAL", "QUANTITY", "MONEY", "PERCENT", "ORDINAL"},
         "時間": {"DATE", "TIME"}}
_NER = None


def ner():
    global _NER
    if _NER is None:
        import warnings
        warnings.filterwarnings("ignore")
        # 模型已經下載到本機的 Hugging Face 快取時，不再連網檢查版本
        os.environ.setdefault("HF_HOME", os.path.expanduser(r"~\.cache\huggingface"))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        from ckip_transformers.nlp import CkipNerChunker
        _NER = CkipNerChunker(model="albert-tiny")
    return _NER


def pieces(t, size=400):
    """依句號切成不超過 size 字的片段（模型一次吃的長度有限）。"""
    out, buf = [], ""
    for s in re.split(r"(?<=[。！？!?\n])", t):
        if len(buf) + len(s) > size and buf:
            out.append(buf)
            buf = ""
        buf += s
    if buf.strip():
        out.append(buf)
    return [p for p in out if p.strip()]


def feats_many(texts, batch=64):
    """多篇一起算（快很多）。回傳每篇 {專名, 數量, 時間, 合計}（每千個漢字）與實體清單。"""
    segs, owner = [], []
    for i, t in enumerate(texts):
        for p in pieces(t):
            segs.append(p)
            owner.append(i)
    res = ner()(segs, batch_size=batch, show_progress=False) if segs else []
    out = [dict(專名=0, 數量=0, 時間=0, ents=[]) for _ in texts]
    for i, ents in zip(owner, res):
        for e in ents:
            for k, s in KINDS.items():
                if e.ner in s:
                    out[i][k] += 1
                    out[i]["ents"].append((e.word, e.ner))
    for i, t in enumerate(texts):
        n = max(1, len(CJK.findall(t)))
        for k in KINDS:
            out[i][k] = out[i][k] * 1000 / n
        out[i]["合計"] = sum(out[i][k] for k in KINDS)
    return out


def quant(xs):
    s = sorted(xs)
    if not s:
        return {}
    q = lambda p: s[min(len(s) - 1, int(p * len(s)))]
    return dict(p10=q(.1), p25=q(.25), p50=q(.5), p75=q(.75), p90=q(.9), mean=sum(s) / len(s), n=len(s),
                q=[q(i / 20) for i in range(1, 20)])


def norms():
    import corpus, build_ngrams as BN
    import features as F
    t0 = time.time()
    docs = json.load(open(os.path.join(corpus.CAS, "clean", "docs.json"), encoding="utf-8"))
    test = [d for d in docs if BN.is_test(d[0])]
    random.seed(21)
    pick = random.sample([d for d in test if d[1] == "pixnet"], 1200) + random.sample([d for d in test if d[1] != "pixnet"], min(800, sum(1 for d in test if d[1] != "pixnet")))
    cut = lambda t: t[:1500]
    sets = {"人寫口語": [cut(corpus.casual(d[0])) for d in pick]}
    sets["人寫日常說話"] = [cut(corpus.casual(d[0])) for d in pick if d[2]]
    hc3 = [json.loads(l) for l in open(os.path.join(corpus.ROOT, "AI對照稿", "HC3", "hc3_tw.jsonl"), encoding="utf-8")]
    sets["HC3 ChatGPT"] = [cut(r["text"]) for r in random.sample([r for r in hc3 if r["cjk"] >= 300], 800)]
    mine = []
    for p in sorted(glob.glob(os.path.join(corpus.ROOT, "AI對照稿", "既有AI文件", "*.txt"))):
        t = open(p, encoding="utf-8").read()
        po = F.prose_only(t)
        mine.append(cut(po if len(CJK.findall(po)) > 600 else t))
    sets["過去 AI 稿"] = mine
    demo = os.path.join(corpus.ROOT, "分析", "示範")
    sets["示範稿（AI 原稿）"] = [cut(open(os.path.join(demo, f), encoding="utf-8").read()) for f in
                            ("skill對比/原稿.txt", "範本2_實習心得/原稿.txt", "口語/改前.txt") if os.path.exists(os.path.join(demo, f))]
    res = {}
    for k, texts in sets.items():
        fs = feats_many(texts)
        res[k] = {f: quant([x[f] for x in fs]) for f in ("專名", "數量", "時間", "合計")}
        print(f"{k}：{len(texts)} 篇，合計中位數 {res[k]['合計']['p50']:.1f}（{time.time() - t0:.0f} 秒）", flush=True)
    json.dump(res, open(os.path.join(HERE, "norms_specificity.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    lines = ["# 具體細節密度：人寫與 AI（CKIP albert-tiny 專有名詞辨識，每千個漢字）\n",
             "每篇取前 1,500 字。數字是中位數（第 25–75 百分位）。\n",
             "| 組 | 篇數 | 專名 | 數量 | 時間 | 合計 |", "|---|---|---|---|---|---|"]
    for k, v in res.items():
        lines.append(f"| {k} | {v['合計']['n']} | " + " | ".join(f"{v[f]['p50']:.1f}（{v[f]['p25']:.1f}–{v[f]['p75']:.1f}）" for f in ("專名", "數量", "時間", "合計")) + " |")
    open(os.path.join(corpus.ROOT, "分析", "具體細節_人寫與AI.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1] == "--norms":
        norms()
    else:
        t = open(sys.argv[1], encoding="utf-8").read()
        f = feats_many([t])[0]
        print(json.dumps({k: round(v, 2) if isinstance(v, float) else v for k, v in f.items()}, ensure_ascii=False, indent=1))

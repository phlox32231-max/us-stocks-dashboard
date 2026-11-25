#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diagnose.html 의 데이터 스냅샷(data/diagnose.json)을 만든다.

시세·재무: Nasdaq API(info/summary/company-profile/news) · Yahoo Finance(chart/quoteSummary)
계산 규칙(투자매력 점수, 적정가 밴드, 매매 신호)은 diagnose.html 안에 그대로 공개돼 있고
이 스크립트가 그 규칙을 계산한다. 값이 없으면 지어내지 않고 None(=화면 '-')으로 둔다.

사용:  python3 scripts/build_diagnose.py [--refresh]
  --refresh  캐시(.cache-diag)를 무시하고 새로 받는다.
"""
import json, os, sys, math, statistics, subprocess, time, urllib.request, datetime, concurrent.futures

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(os.path.dirname(os.path.dirname(ROOT)), ".cache-diag")  # 저장소 밖 캐시
OUT = os.path.join(ROOT, "data", "diagnose.json")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
KST = datetime.timezone(datetime.timedelta(hours=9))
REFRESH = "--refresh" in sys.argv

# ── 진단 대상 종목(손으로 관리하는 목록) ──────────────────────────────
# ko: 한국어 이름 / flag: 본사 국가 / note: 왕초보용 한 줄 설명 / group: 적정가 비교 업종
TICKERS = [
    dict(t="NRSN", ko="뉴로센스 테라퓨틱스", flag="🇮🇱", country="이스라엘", group="biotech", held=True,
         avg=4259, note="루게릭병(ALS) 신약 PrimeC를 만드는 임상 단계 바이오 회사",
         news="11/25 보도: 협력사 뉴로라이트가 뉴로센스 2b상 ALS 임상에서 뇌기능 바이오마커로 ‘통계적으로 유의한 치료 효과’를 확인했다고 발표 — 오늘 급등의 배경으로 보여요(추정). / 11/18 주총(12월 29일)에서 추가 액면병합 권한 안건 / 10/14 나스닥 상장폐지 결정에 이의신청, 11/10 청문회"),
    dict(t="NVDA", ko="엔비디아", flag="🇺🇸", country="미국", group="semis",
         note="AI 칩(GPU) 세계 1위 — AI 데이터센터의 두뇌를 만드는 회사",
         news="회사 고유 악재보다 오늘 반도체 매도세(Barchart ‘칩메이커 급락’)가 컸어요. 11/25 ‘160달러 아래는 사도 된다’는 투자 칼럼도 나왔어요."),
    dict(t="MU", ko="마이크론", flag="🇺🇸", country="미국", group="semis",
         note="메모리 반도체 3대장 — HBM·d램·낸드를 만드는 회사",
         news="12월 실적 발표를 앞두고 있어요. 11/25 ‘2027년 말 마이크론 주가는?’ 전망 기사와 테퍼의 AI주 매수 보도가 나왔어요."),
    dict(t="AMD", ko="AMD", flag="🇺🇸", country="미국", group="semis",
         note="엔비디아를 쫓는 CPU·AI 가속기 회사",
         news="11/25 ‘고점 회복까지 57% 더 올라야 한다’는 분석과 ‘2027년 전에 사라’는 칼럼이 나왔어요. 오늘은 반도체 매도세에 같이 밀렸어요."),
    dict(t="SNDK", ko="샌디스크", flag="🇺🇸", country="미국", group="semis",
         note="낸드 플래시 메모리 회사(웨스턴디지털에서 분사)",
         news="11/24 ‘샌디스크 주가가 급락한 이유’, ‘마이크론 vs 샌디스크’ 비교 기사가 나왔어요. 오늘도 메모리 약세에 밀렸어요."),
    dict(t="DELL", ko="델 테크놀로지스", flag="🇺🇸", country="미국", group="hardware",
         note="AI 서버·PC를 파는 컴퓨터 회사",
         news="11/24 회계 3분기 매출 549억 달러로 사상 최대를 발표했어요. 발표 뒤 차익 실현 매물이 나오는 모습이에요."),
    dict(t="CRWV", ko="코어위브", flag="🇺🇸", country="미국", group="aicloud",
         note="AI 학습·추론용 GPU를 빌려주는 클라우드 회사",
         news="11/24 ‘엔비디아 흔들림이 코어위브에 얼마나 위험한가’ 기사가 나왔어요. 오늘 AI 인프라주가 함께 밀렸어요."),
    dict(t="IREN", ko="아이렌", flag="🇦🇺", country="호주", group="aicloud",
         note="비트코인 채굴장을 AI 데이터센터로 바꾸는 회사",
         news="회사 고유 뉴스는 없고, AI·반도체 매도세 기사만 나왔어요. 재료 없이 움직이는 날은 변동이 크게 나와요."),
    dict(t="EMBC", ko="엠벡타", flag="🇺🇸", country="미국", group="medtech",
         note="100년 된 인슐린 주사기·당뇨 관리용품 회사(BD에서 분사)",
         news="11/24 회계 4분기 실적에서 순이익이 늘었다고 발표했어요. 그날 헬스케어 급등 명단(+40%)에 올랐어요."),
    dict(t="ALTG", ko="알타 이큅먼트", flag="🇺🇸", country="미국", group="industrial",
         note="북미 산업장비(지게차 등) 딜러 — 팔고 빌려주고 수리하는 회사",
         news="11/23 Jackson Group Peterbilt를 2억 7,250만 달러에 인수하고, 3억 3,840만 달러 PIPE(신주 발행) 조달을 결정했어요. 인수 기대와 지분 희석 우려가 섞여 있어요."),
    dict(t="JAGX", ko="재규어 헬스", flag="🇺🇸", country="미국", group="biotech",
         note="식물에서 뽑은 위장질환 처방약을 만드는 회사",
         news="11/24 1:25 액면병합이 발효된 첫날 급등했어요. 11/16 3분기 실적과 2027년 중반 신약 허가(NDA) 제출 계획을 밝혔어요."),
    dict(t="BENF", ko="베네피션트", flag="🇺🇸", country="미국", group="finance",
         note="대체투자(사모펀드 지분)를 쪼개 파는 금융회사",
         news="11/17 회계 2분기 실적, 11/24 HCLP 관련 소송 제기 보도가 나왔어요. 나스닥 요건 미준수 표시가 붙어 있어요."),
    dict(t="LVWR", ko="라이브와이어", flag="🇺🇸", country="미국", group="auto",
         note="할리데이비슨의 전기 오토바이 브랜드",
         news="7월 이후 회사 고유 뉴스가 없어요. 재료 없이 거래량만 늘면 오래가기 어려워요."),
    dict(t="ONFO", ko="온폴리오 홀딩스", flag="🇺🇸", country="미국", group="software",
         note="돈을 버는 온라인 사업체를 사서 굴리는 회사",
         news="11/19 나스닥 상장폐지 통지를 받고 이의신청할 계획이라고 밝혔어요. 11/6 최대 1:250 액면병합 권한도 승인했어요."),
    dict(t="TNYA", ko="테나야 테라퓨틱스", flag="🇺🇸", country="미국", group="biotech",
         note="심장 유전자 치료를 연구하는 임상 단계 바이오",
         news="11/4 3분기 실적에서 손실이 예상보다 작았어요. 9/14 심장 유전자 치료 TN-401이 FDA 희귀질환 신속 심사(RMAT) 지정을 받았어요."),
    dict(t="IBIO", ko="아이바이오", flag="🇺🇸", country="미국", group="biotech",
         note="비만·심장 항체 신약을 만드는 임상 단계 바이오",
         news="11/20 나스닥 최소주가(1달러) 미달 통지를 받았어요. 11/12 비만 치료제 1분기 데이터 기대를 밝혔어요."),
    dict(t="ALDX", ko="알데이라 테라퓨틱스", flag="🇺🇸", country="미국", group="biotech",
         note="안구건조증·면역질환 신약 회사",
         news="11/17 나스닥 최소주가 미달 통지, 11/9 ADX-2191의 FDA 검토 관할 이전을 요청했어요."),
    dict(t="GLXG", ko="갤럭시 페이롤", flag="🇭🇰", country="홍콩", group="services",
         note="홍콩에서 급여·인사 업무를 대행하는 회사(영령 버진아일랜드 지주사)",
         news="회사 고유 뉴스가 없어요. 오늘 거래량이 평소의 수십 배로 터진 것이 특징이에요."),
    dict(t="SMXT", ko="솔라맥스 테크놀로지", flag="🇺🇸", country="미국", group="solar",
         note="캘리포니아 태양광 설치 회사(중국 사업 비중이 큼)",
         news="회사 고유 뉴스는 없어요. 나스닥 요건 미준수 표시가 있고, 하루 변동이 큰 초소형주예요."),
    dict(t="BDRX", ko="바이오덱사", flag="🇬🇧", country="영국", group="biotech",
         note="영국 바이오 — 희귀질환·항암 신약을 개발하는 회사",
         news="10/13 3상(ERapa) 환자 100명 등록을 마쳤어요. 9/16 200만 달러 워런트 행사 계약으로 주가가 25% 빠진 이력이 있고, 11/1 목표가가 73달러로 올라갔어요."),
]

# 적정가 비교에 쓰는 같은 업종 대표 종목
PEERS = {
    "semis": ["NVDA", "MU", "AMD", "SNDK", "AVGO", "INTC", "TXN", "QCOM"],
    "hardware": ["DELL", "HPQ", "ANET", "SMCI", "STX", "WDC"],
    "aicloud": ["CRWV", "IREN", "APLD", "CORZ"],
    "biotech": ["NRSN", "JAGX", "TNYA", "IBIO", "ALDX", "BDRX", "AMGN", "REGN", "MRNA", "VRTX"],
    "medtech": ["EMBC", "MDT", "BDX", "ISRG"],
    "finance": ["BENF", "SOFI", "HOOD", "IBKR", "COIN"],
    "industrial": ["ALTG", "CAT", "DE"],
    "auto": ["LVWR", "TSLA", "RIVN", "LCID"],
    "software": ["ONFO", "ORCL", "CRM", "NOW", "SNOW"],
    "services": ["GLXG", "ADP", "PAYX"],
    "staples": ["PLAG", "KHC", "CAG"],
    "solar": ["SMXT", "FSLR", "ENPH"],
}
GROUP_KO = {"semis": "반도체", "hardware": "컴퓨터·장비", "aicloud": "AI 데이터센터", "biotech": "바이오",
            "medtech": "의료기기", "finance": "금융", "industrial": "산업재", "auto": "자동차",
            "software": "소프트웨어·인터넷", "services": "사업서비스", "staples": "식품·생활", "solar": "태양광"}
IDX = [("^IXIC", "나스닥"), ("^GSPC", "S&P500"), ("^DJI", "다우"), ("^RUT", "러셀2000"),
       ("^SOX", "필라델피아 반도체"), ("^VIX", "VIX"), ("KRW=X", "원/달러")]


# ── 수집 ───────────────────────────────────────────────────────────────
def jget(url, opener=None, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                                               "Accept-Language": "en-US,en;q=0.9"})
    op = opener.open if opener else urllib.request.urlopen
    with op(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def curl_json(url, jar):
    out = subprocess.run(["curl", "-s", "-m", "25", "-b", jar, "-c", jar, "-A", UA, url],
                         capture_output=True, text=True).stdout
    try:
        return json.loads(out)
    except Exception:
        return None


def yahoo_crumb():
    jar = os.path.join(CACHE, "yahoo_cookies.txt")
    subprocess.run(["curl", "-s", "-m", "20", "-c", jar, "-A", UA, "https://fc.yahoo.com", "-o", "/dev/null"])
    crumb = subprocess.run(["curl", "-s", "-m", "20", "-b", jar, "-c", jar, "-A", UA,
                            "https://query1.finance.yahoo.com/v1/test/getcrumb"],
                           capture_output=True, text=True).stdout.strip()
    return jar, crumb


def fetch_one(t, full, jar, crumb):
    path = os.path.join(CACHE, t.replace("^", "_") + ".json")
    if os.path.exists(path) and not REFRESH:
        try:
            return json.load(open(path))
        except Exception:
            pass
    out = {}
    if full and not (t.startswith("^") or t == "KRW=X"):
        for k, u in (("info", "https://api.nasdaq.com/api/quote/%s/info?assetclass=stocks" % t),
                     ("summary", "https://api.nasdaq.com/api/quote/%s/summary?assetclass=stocks" % t),
                     ("profile", "https://api.nasdaq.com/api/company/%s/company-profile?assetclass=stocks" % t),
                     ("news", "https://api.nasdaq.com/api/news/topic/articlebysymbol?q=%s%%7Cstocks&offset=0&limit=8&fallback=true" % t)):
            try:
                out[k] = jget(u)
            except Exception as e:
                out[k + "_err"] = str(e)
    elif full:
        for k, u in (("chart", "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=1d&interval=1d" % t),):
            try:
                out[k] = jget(u)
            except Exception as e:
                out[k + "_err"] = str(e)
        with open(path, "w") as fh:
            json.dump(out, fh)
        return out
    try:
        out["chart"] = jget("https://query1.finance.yahoo.com/v8/finance/chart/%s?range=1y&interval=1d" % t)
    except Exception as e:
        out["chart_err"] = str(e)
    try:
        out["intra"] = jget("https://query1.finance.yahoo.com/v8/finance/chart/%s?range=1d&interval=1m&includePrePost=true" % t)
    except Exception as e:
        out["intra_err"] = str(e)
    with open(path, "w") as fh:
        json.dump(out, fh)
    return out


def fetch_fund(t, jar):
    """Yahoo quoteSummary(재무). 크럼이 만료되면 한 번 새로 받아 재시도한다."""
    mods = "financialData,defaultKeyStatistics,summaryDetail,price"
    for attempt in range(3):
        crumb, _ = yahoo_crumb() if attempt else (fetch_fund.crumb, None)
        if not crumb:
            continue
        data = curl_json("https://query1.finance.yahoo.com/v10/finance/quoteSummary/%s?modules=%s&crumb=%s"
                         % (t, mods, crumb), jar)
        res = ((data or {}).get("quoteSummary") or {}).get("result")
        if res:
            return data
        time.sleep(1.0)
    return None


fetch_fund.crumb = None


def num(o, *path):
    """{'raw':x} 형태에서 숫자만 뽑는다. 없으면 None."""
    for p in path:
        if o is None:
            return None
        if isinstance(o, dict) and p in o:
            o = o[p]
        else:
            return None
    if isinstance(o, dict):
        o = o.get("raw")
    try:
        if o is None or isinstance(o, bool):
            return None
        v = float(o)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def money(s):
    """'$2.2999' -> 2.2999"""
    if not s:
        return None
    s = str(s).replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except Exception:
        return None


def rng(s):
    """'$2.8799/$1.8101' or '1.05 - 24.80' -> (lo, hi)"""
    if not s:
        return (None, None)
    txt = str(s).replace("$", " ").replace(",", " ")
    parts = [p for p in txt.replace("-", " ").replace("/", " ").split() if p.strip()]
    vals = []
    for p in parts:
        try:
            vals.append(float(p))
        except Exception:
            pass
    if len(vals) >= 2:
        return (min(vals), max(vals))
    return (None, None)


def fmt_x(v):
    """'18,155배' 같은 숫자를 읽기 좋게. 100배 이상은 그렇게 표시한다."""
    if v is None:
        return "-"
    if v >= 100:
        return "100배 이상"
    if v >= 10:
        return "%d배" % round(v)
    return "%.1f배" % v


def pct(a, b):
    if a is None or not b:
        return None
    return (a / b - 1.0) * 100.0


# ── 계산 ───────────────────────────────────────────────────────────────
def intraday_stats(intra):
    """장중 흐름: 5분봉으로 (1) 상승봉 거래량 비중 (2) 시간대별 구간 요약 (3) 스파크라인 점을 만든다."""
    try:
        r = intra["chart"]["result"][0]
        ts, q = r["timestamp"], r["indicators"]["quote"][0]
    except Exception:
        return None
    bars = []
    up = down = 0.0
    prev_c = None
    for i, t in enumerate(ts):
        c, v = q["close"][i], q["volume"][i]
        if c is None:
            continue
        et = datetime.datetime.fromtimestamp(t, datetime.timezone(datetime.timedelta(hours=-5)))
        mins = et.hour * 60 + et.minute
        bars.append((mins, et, c, v or 0))
        if prev_c is not None and v:
            if c > prev_c:
                up += v
            elif c < prev_c:
                down += v
        prev_c = c
    if not bars:
        return None

    reg = [b for b in bars if b[0] >= 570]
    use = reg if len(reg) >= 8 else bars
    # 스파크라인(최대 60점)
    pts = [[int(b[1].timestamp()), round(b[2], 4)] for b in use]
    step = max(1, len(pts) // 60)
    spark = pts[::step]
    if spark[-1] != pts[-1]:
        spark.append(pts[-1])

    # 시간대별 구간: 지금까지의 장 시간을 3~5개로 나눈다
    total_vol = sum(b[3] for b in use) or 1
    nseg = max(2, min(5, len(use) // 6 + 1))
    seg = []
    if use:
        per = max(1, math.ceil(len(use) / nseg))
        for k in range(0, len(use), per):
            chunk = use[k:k + per]
            if not chunk:
                continue
            vol = sum(b[3] for b in chunk)
            a, b_ = chunk[0][1], chunk[-1][1]
            seg.append({"label": "%02d:%02d–%02d:%02d" % (a.hour, a.minute, b_.hour, b_.minute),
                        "volShare": round(vol / total_vol * 100, 1),
                        "chg": round((chunk[-1][2] / chunk[0][2] - 1) * 100, 2) if chunk[0][2] else None})
    # 매수 우열은 1분봉의 잔떨림을 줄이려고 5분 단위로 묶어서 계산한다
    b5 = {}
    for b in use:
        k = b[0] // 5
        if k not in b5:
            b5[k] = [b[1], b[2], 0.0]      # 시작시각, 시작가, 거래량
        b5[k][2] += b[3]
        b5[k].append(b[2])                 # 마지막 종가 추적용
    closes5 = [[v[1], v[-1], v[2]] for _, v in sorted(b5.items())]
    up = down = 0.0
    for i in range(1, len(closes5)):
        prev_c, c, vol = closes5[i - 1][1], closes5[i][1], closes5[i][2]
        if c > prev_c:
            up += vol
        elif c < prev_c:
            down += vol
    pre_vol = sum(b[3] for b in bars if b[0] < 570)
    tot = up + down
    return {"upShare": round(up / tot * 100, 1) if tot else None,
            "spark": spark, "seg": seg,
            "preVol": pre_vol or None, "lastEt": "%02d:%02d" % (bars[-1][1].hour, bars[-1][1].minute)}


def build_ticker(meta, raw, peers_ps, peers_pe):
    t = meta["t"]
    info = (raw.get("info") or {}).get("data") or {}
    summ = ((raw.get("summary") or {}).get("data") or {}).get("summaryData") or {}
    prof = ((raw.get("profile") or {}).get("data") or {})
    fund = ((raw.get("fund") or {}).get("quoteSummary") or {}).get("result") or [{}]
    fund = fund[0] if fund else {}
    fd, ks, sd = fund.get("financialData", {}) or {}, fund.get("defaultKeyStatistics", {}) or {}, fund.get("summaryDetail", {}) or {}

    pd_ = info.get("primaryData") or {}
    price = money(pd_.get("lastSalePrice")) or num(sd, "regularMarketPrice") or num(fund.get("price"), "regularMarketPrice")
    if price is None:
        try:
            price = raw["chart"]["chart"]["result"][0]["meta"]["regularMarketPrice"]
        except Exception:
            price = None
    prev = num(summ.get("PreviousClose"), "value") if isinstance(summ.get("PreviousClose"), dict) else money((summ.get("PreviousClose") or {}).get("value"))
    prev = money((summ.get("PreviousClose") or {}).get("value")) or num(sd, "previousClose")
    chg = money(pd_.get("netChange")) or num(sd, "regularMarketChange")
    # Nasdaq은 '-0.81%'(퍼센트) 문자열, Yahoo는 -0.0081(비율) 숫자를 준다 — 섞으면 -81%가 된다
    chg_pct = None
    if pd_.get("percentageChange"):
        chg_pct = money(str(pd_["percentageChange"]).replace("%", "").strip())
    if chg_pct is None:
        y = num(sd, "regularMarketChangePercent")
        chg_pct = y * 100 if (y is not None and abs(y) < 1) else y
    dlo, dhi = rng((summ.get("TodayHighLow") or {}).get("value"))
    if dlo is None:
        dlo, dhi = num(sd, "dayLow"), num(sd, "dayHigh")
    wlo, whi = rng((summ.get("FiftTwoWeekHighLow") or {}).get("value"))
    if wlo is None:
        wlo, whi = num(sd, "fiftyTwoWeekLow"), num(sd, "fiftyTwoWeekHigh")
    mcap = money((summ.get("MarketCap") or {}).get("value")) or num(sd, "marketCap") or num(ks, "enterpriseValue")
    vol = money((summ.get("ShareVolume") or {}).get("value")) or num(sd, "volume") or num(pd_, "volume")
    target_1y = money((summ.get("OneYrTarget") or {}).get("value"))
    sector = (summ.get("Sector") or {}).get("value")
    industry = (summ.get("Industry") or {}).get("value")
    region = (prof.get("Region") or {}).get("value")
    desc_en = (prof.get("CompanyDescription") or {}).get("value") or ""
    notes = [n.get("headline") for n in (info.get("notifications") or []) if n.get("headline")]

    # 일봉: 평균 거래량·변동성·이동평균
    closes, vols, dates = [], [], []
    try:
        r = raw["chart"]["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        for i, c in enumerate(q["close"]):
            if c is not None:
                closes.append(c)
                vols.append(q["volume"][i] or 0)
                dates.append(r["timestamp"][i])
    except Exception:
        pass
    avg_vol = round(statistics.mean(vols[-64:-1])) if len(vols) >= 20 else None
    if vol is not None and sd.get("averageVolume"):
        avg_vol = num(sd, "averageVolume") or avg_vol
    # 장중이면 아직 하루가 안 끝났으므로 '지금 속도로 환산한 하루 거래량'으로 평소와 비교한다
    elapsed_min = None
    try:
        m_ = raw["intra"]["chart"]["result"][0]["meta"]
        t_ = m_.get("regularMarketTime")
        if t_:
            et = datetime.datetime.fromtimestamp(t_, datetime.timezone(datetime.timedelta(hours=-5)))
            mins = et.hour * 60 + et.minute
            if 570 <= mins <= 960:
                elapsed_min = max(5, min(390, mins - 570))
    except Exception:
        elapsed_min = None
    vol_ratio_raw = round(vol / avg_vol, 2) if (vol and avg_vol) else None
    if vol and avg_vol and elapsed_min and elapsed_min < 385:
        vol_ratio = round((vol / elapsed_min) / (avg_vol / 390), 2)
    else:
        vol_ratio = vol_ratio_raw
    rets = [closes[i] / closes[i - 1] - 1 for i in range(max(1, len(closes) - 21), len(closes)) if closes[i - 1]]
    vol20 = round(statistics.pstdev(rets) * 100, 2) if len(rets) >= 5 else None
    ma20 = round(statistics.mean(closes[-20:]), 4) if len(closes) >= 20 else None
    ma50 = round(statistics.mean(closes[-50:]), 4) if len(closes) >= 50 else None
    ret5 = round(pct(closes[-1], closes[-6]) or 0, 2) if len(closes) >= 6 else None
    ret1m = round(pct(closes[-1], closes[-22]) or 0, 2) if len(closes) >= 22 else None
    ret3m = round(pct(closes[-1], closes[-64]) or 0, 2) if len(closes) >= 64 else None

    flow = intraday_stats(raw.get("intra") or {})
    bid_sz, ask_sz = money(pd_.get("bidSize")), money(pd_.get("askSize"))

    # 재무
    ps = num(ks, "priceToSalesTrailing12Months") or num(sd, "priceToSalesTrailing12Months")
    if ps is not None and ps <= 0:
        ps = None
    pe = num(sd, "trailingPE") or num(ks, "trailingPE")
    if pe is not None and pe <= 0:
        pe = None
    fpe = num(sd, "forwardPE") or num(ks, "forwardPE")
    if fpe is not None and fpe <= 0:
        fpe = None
    rev_growth = num(fd, "revenueGrowth")
    gross_m = num(fd, "grossMargins")
    profit_m = num(fd, "profitMargins")
    cash = num(fd, "totalCash")
    debt = num(fd, "totalDebt")
    fcf = num(fd, "freeCashflow")
    roe = num(fd, "returnOnEquity")
    tgt_mean = num(fd, "targetMeanPrice") or target_1y
    n_analyst = num(fd, "numberOfAnalystOpinions")
    rec_mean = num(fd, "recommendationMean")
    beta = num(sd, "beta") or num(ks, "beta")

    # 목표가 이상치(액면병합 뒤 목표가가 그대로 남은 경우) 제외
    tgt_upside = None
    if tgt_mean and price and 0.3 <= tgt_mean / price <= 5:
        tgt_upside = round((tgt_mean / price - 1) * 100, 1)

    risks, risk_keys = [], []
    if any("OUT OF COMPLIANCE" in (n or "") for n in notes):
        risks.append("나스닥이 ‘요건 미준수(OUT OF COMPLIANCE)’로 표시한 종목이에요. 최소주가·시총 요건을 못 맞춰 상장폐지 심사를 받을 수 있어요.")
        risk_keys.append("compliance")
    if price is not None and price < 1:
        risks.append("주가가 $1 아래예요. 나스닥은 30거래일 연속 $1 미만이면 상장폐지 절차를 시작해요.")
        risk_keys.append("sub1")
    if mcap is not None and mcap < 3e8:
        risks.append("시가총액이 약 $%.0fM(약 %s억 원)뿐인 초소형주예요. 하루에 ±30%%도 흔하고, 팔고 싶을 때 못 파는 경우도 있어요."
                     % (mcap / 1e6, format(round(mcap * FX / 1e8), ",")))
        risk_keys.append("micro")
    if (fcf is not None and fcf < 0) or (profit_m is not None and profit_m <= 0 and not ps):
        risks.append("돈을 벌지 못하고 현금을 쓰는 단계예요. 신주를 찍어 자금을 조달하면 기존 주주 지분이 희석(가치 희석)될 수 있어요.")
        risk_keys.append("burn")
    if debt is not None and cash is not None and cash > 0 and debt / cash > 3:
        risks.append("빚이 현금의 %.1f배예요. 금리가 높을 때 이자 부담이 커져요." % (debt / cash))
        risk_keys.append("debt")
    news_rows = (((raw.get("news") or {}).get("data") or {}).get("rows") or [])[:6]
    titles = " ".join((n.get("title") or "").lower() for n in news_rows)
    if "reverse stock split" in titles or "reverse share split" in titles:
        risks.append("최근 뉴스에 액면병합(reverse split) 이야기가 있어요. 주식 수를 줄여 주가를 올려 보이는 것으로, 보통 희석·주가 부진의 흔적이에요.")
        risk_keys.append("split")
    if "delisting" in titles:
        risks.append("최근 뉴스에 상장폐지(delisting) 관련 내용이 있어요.")
        risk_keys.append("delist")
    if "offering" in titles or "pipe" in titles or "warrant" in titles:
        risks.append("최근 뉴스에 신주 발행·유상증자(PIPE·워런트) 관련 내용이 있어요. 주식 수가 늘면 주당 가치가 희석돼요.")
        risk_keys.append("dilute")
    if vol_ratio and vol_ratio >= 3:
        risks.append("오늘 거래량이 평소의 %s 속도로 터지고 있어요. 급등 직후에는 되돌림(차익 실현 매물)이 자주 나와요." % fmt_x(vol_ratio))
        risk_keys.append("volspike")
    if whi and price and price < whi * 0.4:
        risks.append("52주 최고가($%s)보다 %.0f%% 낮아요. 고점에 산 사람은 아직 손실 구간이에요." % (f"{whi:,.2f}", (price / whi - 1) * 100))
        risk_keys.append("drawdown")

    # 위험 요소를 2~3줄로 채운다(지어내지 않고 계산된 사실만)
    if len(risks) < 2 and vol20:
        risks.append("하루 평균 변동폭이 %.1f%%예요. 지수보다 크게 흔들리는 종목이라 하루 손실도 크게 날 수 있어요." % vol20)
    if len(risks) < 3 and whi and price and price < whi * 0.75:
        risks.append("52주 최고가보다 %.0f%% 낮은 자리예요. 반등이 나와도 고점 회복까지는 오래 걸릴 수 있어요." % ((price / whi - 1) * 100))
    if len(risks) < 3 and ma20 and price:
        risks.append("20일 평균가(%.2f달러)보다 낮은 자리라 단기 추세는 아래를 향하고 있어요." % ma20 if price < ma20 else "단기 급등 뒤라 되돌림이 나올 수 있어요.")
    if len(risks) < 2:
        risks.append("오늘 미국 증시 전체가 크게 흔들리는 날이에요. 종목 자체 문제가 아니어도 같이 빠질 수 있어요.")

    # ── 투자매력 점수 ────────────────────────────────────────────────
    parts = []   # (label, pts, max, 근거문)
    def add(label, pts, mx, why):
        if pts is not None:
            parts.append(dict(label=label, pts=round(pts, 1), max=mx, why=why))

    if cash and debt is not None:
        r_ = debt / cash if cash else None
        pts = 10 if r_ <= 0.5 else 6 if r_ <= 1.5 else 3 if r_ <= 3 else 0
        add("현금 대비 빚", pts, 10, "빚이 현금의 %.2f배" % r_)
    if profit_m is not None:
        add("이익 여부", 10 if profit_m > 0.1 else 6 if profit_m > 0 else 2, 10,
            "순이익률 %.1f%%" % (profit_m * 100))
    if fcf is not None:
        add("현금 흐름(FCF)", 10 if fcf > 0 else 3, 10, "FCF %s" % ("+" if fcf > 0 else "") + "$%.1fM" % (fcf / 1e6))
    if rev_growth is not None:
        g = rev_growth * 100
        add("매출 성장률", 15 if g >= 30 else 11 if g >= 10 else 7 if g >= 0 else 3, 15, "전년 대비 %+.1f%%" % g)
    if tgt_upside is not None:
        add("목표가 여력", 10 if tgt_upside >= 50 else 7 if tgt_upside >= 20 else 4 if tgt_upside >= 0 else 1, 10,
            "애널리스트 평균 목표가 대비 %+.0f%%" % tgt_upside)
    if vol_ratio is not None:
        add("거래량 배수", 10 if vol_ratio >= 3 else 7 if vol_ratio >= 1.5 else 5 if vol_ratio >= 0.7 else 2, 10,
            ("평소의 %s" % fmt_x(vol_ratio)) + (" (개장 %d분 기준 환산)" % elapsed_min if elapsed_min and elapsed_min < 385 else ""))
    if flow and flow.get("upShare") is not None:
        u = flow["upShare"]
        add("장중 매수 우열", 8 if u >= 60 else 6 if u >= 50 else 4 if u >= 40 else 2, 8, "상승 봉 거래량 %.0f%%" % u)
    if dlo is not None and dhi is not None and dhi > dlo and price is not None:
        pos = (price - dlo) / (dhi - dlo)
        add("오늘 가격 위치", 7 if pos >= 0.7 else 5 if pos >= 0.4 else 2, 7, "당일 범위의 %.0f%% 지점" % (pos * 100))
    if vol20 is not None:
        add("변동성(위험)", 8 if vol20 <= 3 else 5 if vol20 <= 6 else 3 if vol20 <= 10 else 0, 8, "하루 변동 %.1f%%" % vol20)
    if mcap is not None:
        add("시총 규모", 6 if mcap >= 1e10 else 5 if mcap >= 1e9 else 3 if mcap >= 3e8 else 1, 6, "$%s" % f"{mcap/1e9:,.1f}B" if mcap >= 1e9 else "$%.0fM" % (mcap / 1e6))
    n_bad = len([k for k in risk_keys if k in ("compliance", "sub1", "delist", "split", "dilute", "burn")])
    add("상장요건·희석 위험", 6 if n_bad == 0 else 3 if n_bad == 1 else 0, 6, "위험 신호 %d개" % n_bad)

    got = sum(p["pts"] for p in parts)
    mx = sum(p["max"] for p in parts) or 1
    score = round(got / mx * 100)
    score_missing = mx < 99.5   # 만점 합계 100점

    # ── 적정주가 밴드 ────────────────────────────────────────────────
    group = meta.get("group")
    peer_ps = peers_ps.get(group) or {}
    peer_pe = peers_pe.get(group) or {}
    val = None
    if pe and peer_pe.get("median"):
        fair = price * (peer_pe["median"] / pe)
        method, basis = "PER", "%s 업종 %d곳의 평균 PER %.1f배 vs 이 회사 %.1f배 (이익 대비 가격)" % (
            GROUP_KO.get(group, group), peer_pe["n"], peer_pe["median"], pe)
    elif ps and peer_ps.get("median") and ps > 0:
        fair = price * (peer_ps["median"] / ps)
        method, basis = "PSR", "%s 업종 %d곳의 평균 PSR %.1f배 vs 이 회사 %.1f배 (매출 대비 가격, 적자라 이익이 없어 매출로 비교)" % (
            GROUP_KO.get(group, group), peer_ps["n"], peer_ps["median"], ps)
    elif tgt_upside is not None and tgt_mean:
        fair = tgt_mean
        method, basis = "목표가", "애널리스트 %s명의 12개월 평균 목표가 $%s" % (
            int(n_analyst) if n_analyst else "-", f"{tgt_mean:,.2f}")
    else:
        fair = None
    if fair and price and 0.2 <= fair / price <= 6:
        lo, hi = fair * 0.75, fair * 1.25
        ax_lo, ax_hi = min(lo, price) * 0.92, max(hi, price) * 1.08
        f = lambda v: max(0.0, min(1.0, (v - ax_lo) / (ax_hi - ax_lo)))
        label = "저평가 쪽" if price < lo else "적정 범위" if price <= hi else "고평가 쪽"
        val = dict(method=method, basis=basis, fair=round(fair, 2), low=round(lo, 2), high=round(hi, 2),
                   axisLow=round(ax_lo, 2), axisHigh=round(ax_hi, 2),
                   pricePos=round(f(price), 3), bandLo=round(f(lo), 3), bandHi=round(f(hi), 3),
                   label=label, gap=round((fair / price - 1) * 100, 1))
    else:
        val = dict(method=None, basis="근거 데이터가 없어 적정가를 계산하지 않았어요(매출·이익·목표가가 없거나, 목표가가 현재가와 너무 동떨어져 있을 때).", fair=None)

    # ── 매매 신호 ────────────────────────────────────────────────────
    day_pos = (price - dlo) / (dhi - dlo) if (dlo is not None and dhi and dhi > dlo and price) else None
    above20 = (price > ma20) if (price and ma20) else None
    buy_share = flow.get("upShare") if flow else None
    n_bad = len([k for k in risk_keys if k in ("compliance", "sub1", "delist", "split", "dilute", "burn")])
    why = []
    chase = ret5 is not None and ret5 > 25     # 5일간 25% 넘게 오른 종목은 추격 매수 금지
    if score < 35 and n_bad >= 2 and (above20 is False or (day_pos is not None and day_pos < 0.35)):
        sig = "매도"
        why = ["투자매력 점수 %d점으로 낮고, 위험 신호가 %d개예요(%s)." % (score, n_bad, ", ".join(
            {"compliance": "나스닥 요건 미준수", "sub1": "$1 미만", "delist": "상장폐지 통지", "split": "액면병합",
             "dilute": "신주 발행", "burn": "현금 소진"}[k] for k in risk_keys if k in ("compliance", "sub1", "delist", "split", "dilute", "burn"))),
            "20일선(%.2f달러) 아래에서 움직이고 있어요." % ma20 if above20 is False and ma20 else "오늘 가격이 당일 범위 아래쪽에 있어요.",
            "보유 중이라면 한 번에 다 팔기보다 나눠서 파는(분할) 쪽이 안전해요."]
    elif score >= 65 and (day_pos or 0) >= 0.55 and (buy_share or 0) >= 55 and n_bad <= 1 and above20 and not chase:
        sig = "매수"
        why = ["투자매력 점수 %d점으로 높은 편이고 위험 신호가 %d개예요." % (score, n_bad),
               "오늘 가격이 당일 범위의 %.0f%% 지점(위쪽)이고, 장중 상승 거래량이 %.0f%%로 매수세가 더 강해요." % (day_pos * 100, buy_share),
               "다만 신호는 ‘검토’일 뿐이에요 — 살 때는 손절가를 먼저 정하고 소액으로 시작하세요."]
    elif chase and score >= 60 and above20:
        sig = "관망"
        why = ["투자매력 점수는 %d점으로 좋은 편이에요." % score,
               "그런데 최근 5일간 %+.0f%%나 올라 이미 많이 오른 자리예요(추격 매수 금지)." % ret5,
               "이렇게 급하게 오른 뒤 따라 사면 되돌림에 걸리기 쉬워요 — 눌림이 올 때까지 기다리세요."]
    elif score >= 50 and above20 is True and n_bad <= 1:
        sig = "보유"
        why = ["투자매력 점수 %d점, 위험 신호 %d개로 버틸 만한 상태예요." % (score, n_bad),
               "20일선(%.2f달러) 위에서 움직여 추세가 살아 있어요." % ma20 if ma20 else "추세가 무너지지 않았어요.",
               "새로 사기보다는 가진 사람이 들고 가며 손절선만 지키는 구간이에요."]
    else:
        sig = "관망"
        detail = []
        if score < 50:
            detail.append("투자매력 점수 %d점으로 낮은 편이에요." % score)
        if n_bad >= 2:
            detail.append("위험 신호가 %d개(%s)라 지금 사면 위험이 커요." % (n_bad, ", ".join(
                {"compliance": "나스닥 요건 미준수", "sub1": "$1 미만", "delist": "상장폐지 통지", "split": "액면병합",
                 "dilute": "신주 발행", "burn": "현금 소진"}[k] for k in risk_keys if k in ("compliance", "sub1", "delist", "split", "dilute", "burn"))))
        if above20 is False and ma20:
            detail.append("20일선(%.2f달러) 아래라 추세가 약해요." % ma20)
        if day_pos is not None and day_pos < 0.45:
            detail.append("오늘 가격이 당일 범위의 %.0f%% 지점이라 힘이 빠진 모습이에요." % (day_pos * 100))
        extras = []
        if vol20:
            extras.append("하루 변동폭이 평균 %.1f%%로 커서 짧게 대응하기 어려운 자리예요." % vol20)
        if vol_ratio:
            extras.append("거래량은 평소의 %s 수준이에요." % fmt_x(vol_ratio))
        if wlo and whi and price and whi > wlo:
            extras.append("52주 범위(%.2f~%.2f달러)의 %.0f%% 지점에 있어요." % (wlo, whi, (price - wlo) / (whi - wlo) * 100))
        if ma20 and price:
            extras.append("20일 평균가(%.2f달러)보다 %+.0f%% 위치예요." % (ma20, (price / ma20 - 1) * 100))
        extras.append("점수·추세·거래량이 서로 다른 방향이라 확신이 약한 자리예요.")
        while len(detail) < 3 and extras:
            detail.append(extras.pop(0))
        why = detail[:3]
    if sig == "보유" and not meta.get("held"):
        sig = "관망"
        why = ["투자매력 점수 %d점에 위험 신호 %d개로 상태는 나쁘지 않아요." % (score, n_bad),
               "가진 사람이라면 들고 갈 만한 자리지만, 지금 새로 사기엔 가격이 이미 올라와 있어요." if (day_pos or 0) >= 0.6 else "가진 사람이라면 들고 갈 만한 자리예요.",
               "새로 산다면 손절가를 먼저 정하고 소액으로만 시작하세요."]
    light = {"매수": "🟢", "보유": "🟡", "관망": "🟡", "매도": "🔴"}[sig]

    news = [dict(title=n.get("title"), src=n.get("publisher"), date=n.get("created"),
                 url="https://www.nasdaq.com" + (n.get("url") or "")) for n in news_rows[:3]]

    return dict(
        ticker=t, name=meta["ko"], flag=meta["flag"], country=meta["country"],
        oneLine=meta["note"], held=bool(meta.get("held")), avgCostKrw=meta.get("avg"),
        group=GROUP_KO.get(group, group), sector=sector, industry=industry, region=region,
        price=price, change=chg, pct=round(chg_pct, 2) if chg_pct is not None else None,
        krw=round(price * FX) if price else None,
        prevClose=prev, dayLow=dlo, dayHigh=dhi, w52Low=wlo, w52High=whi,
        vol=vol, avgVol=avg_vol, volRatio=vol_ratio, volRatioRaw=vol_ratio_raw,
        elapsedMin=elapsed_min, marketCap=mcap,
        ps=round(ps, 2) if ps else None, pe=round(pe, 1) if pe else None, fpe=round(fpe, 1) if fpe else None,
        revGrowth=round(rev_growth * 100, 1) if rev_growth is not None else None,
        grossMargin=round(gross_m * 100, 1) if gross_m is not None else None,
        profitMargin=round(profit_m * 100, 1) if profit_m is not None else None,
        cash=cash, debt=debt, fcf=fcf, roe=round(roe * 100, 1) if roe is not None else None,
        targetMean=tgt_mean if tgt_upside is not None else None, targetUpside=tgt_upside,
        analysts=int(n_analyst) if n_analyst else None, recMean=round(rec_mean, 1) if rec_mean else None,
        beta=round(beta, 2) if beta else None,
        ma20=ma20, ma50=ma50, vol20=vol20, ret5=ret5, ret1m=ret1m, ret3m=ret3m,
        bidSize=bid_sz, askSize=ask_sz,
        flow=flow, score=dict(total=score, parts=parts, missing=bool(score_missing), coverage=round(mx)),
        signal=sig, light=light, signalWhy=why,
        valuation=val, risks=risks[:3], riskKeys=risk_keys,
        news=news, newsKo=meta.get("news"), descEn=desc_en[:400])


def main():
    os.makedirs(CACHE, exist_ok=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    jar, crumb = yahoo_crumb()
    fetch_fund.crumb = crumb
    print("crumb:", crumb)

    all_peer = sorted({p for g in PEERS.values() for p in g})
    full = [m["t"] for m in TICKERS]
    tasks = [(t, True) for t in full] + [(t, False) for t in all_peer if t not in full] + [(t, True) for t, _ in IDX]
    raws = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch_one, t, f, jar, crumb): t for t, f in tasks}
        for fu in concurrent.futures.as_completed(futs):
            t = futs[fu]
            try:
                raws[t] = fu.result()
            except Exception as e:
                print("FAIL", t, e)
                raws[t] = {}
    print("fetched", len(raws))

    # 재무(quoteSummary)는 쿠키 경합을 피하려고 순차로 받는다
    need = [t for t, f in tasks if t != "KRW=X" and not t.startswith("^")]
    for i, t in enumerate(need):
        raw = raws.setdefault(t, {})
        res = ((raw.get("fund") or {}).get("quoteSummary") or {}).get("result") if raw.get("fund") else None
        if res and not REFRESH:
            continue
        got = fetch_fund(t, jar)
        if got:
            raw["fund"] = got
            path = os.path.join(CACHE, t.replace("^", "_") + ".json")
            try:
                with open(path, "w") as fh:
                    json.dump(raw, fh)
            except Exception:
                pass
        if i % 10 == 0:
            print("  fund", i, "/", len(need))

    # 환율
    kr = (raws.get("KRW=X") or {}).get("chart", {}).get("chart", {}).get("result")
    fx = kr[0]["meta"].get("regularMarketPrice") if kr else None
    global FX
    FX = fx or 1342.5

    # 업종 평균 PSR / PER
    def med(vals):
        vals = [v for v in vals if v]
        return dict(median=round(statistics.median(vals), 2), n=len(vals)) if len(vals) >= 2 else {}
    peers_ps, peers_pe = {}, {}
    for g, members in PEERS.items():
        pss, pes = [], []
        for m in members:
            if m in full:
                continue
            raw = raws.get(m) or {}
            res = ((raw.get("fund") or {}).get("quoteSummary") or {}).get("result") or [{}]
            res = res[0] if res else {}
            v = num(res.get("defaultKeyStatistics", {}), "priceToSalesTrailing12Months") or num(res.get("summaryDetail", {}), "priceToSalesTrailing12Months")
            if v and v > 0:
                pss.append(v)
            p = num(res.get("summaryDetail", {}), "trailingPE")
            if p and p > 0:
                pes.append(p)
        peers_ps[g], peers_pe[g] = med(pss), med(pes)

    out_t = [build_ticker(m, raws.get(m["t"]) or {}, peers_ps, peers_pe) for m in TICKERS]

    # 지수·환율 스냅샷
    idx = []
    for sym, ko in IDX:
        r = (raws.get(sym) or {}).get("chart", {}).get("chart", {}).get("result")
        if not r:
            continue
        m = r[0]["meta"]
        p, pc = m.get("regularMarketPrice"), m.get("chartPreviousClose")
        idx.append(dict(name=ko, value=p, pct=round((p / pc - 1) * 100, 2) if p and pc else None))
    fx_row = dict(name="원/달러", value=round(fx, 2) if fx else None, pct=None)
    # 시장 상태
    mstat = ((raws.get("NRSN") or {}).get("info") or {}).get("data", {}).get("marketStatus")
    last_ts = ((raws.get("NRSN") or {}).get("info") or {}).get("data", {}).get("primaryData", {}).get("lastTradeTimestamp")

    movers = sorted([t for t in out_t if t["pct"] is not None], key=lambda x: -x["pct"])[:3]

    now = datetime.datetime.now(KST)
    data = dict(
        generatedAt=now.strftime("%Y-%m-%d %H:%M"),
        generatedAtIso=now.isoformat(timespec="seconds"),
        marketStatus=mstat, lastTradeEt=last_ts, fx=round(fx, 2) if fx else None,
        indices=idx, movers=[dict(t=t["ticker"], name=t["name"], pct=t["pct"], price=t["price"]) for t in movers],
        tickers=out_t,
        sources=dict(quote="Nasdaq API (api.nasdaq.com) · Yahoo Finance chart",
                     fundamentals="Yahoo Finance quoteSummary · Nasdaq summary",
                     news="Nasdaq news feed",
                     note="GitHub Pages는 정적 호스팅이라 브라우저에서 증권 API를 직접 부르면 CORS로 막힙니다. 그래서 이 파일은 스크립트가 미리 받아 둔 스냅샷입니다."),
        rules=dict(
            scoreMax=100,
            weights="재무 건전성 30 + 성장성 25 + 수급·거래 25 + 변동성·위험 20",
        ),
    )
    with open(OUT, "w") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print("wrote", OUT, os.path.getsize(OUT), "bytes")
    for t in out_t[:5]:
        print(t["ticker"], t["price"], t["pct"], "score", t["score"]["total"], t["signal"], "val", (t["valuation"] or {}).get("label"))


if __name__ == "__main__":
    main()

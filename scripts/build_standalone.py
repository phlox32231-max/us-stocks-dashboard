#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diagnose.html + data/diagnose.json → 데이터가 안에 든 HTML 한 장으로 만든다.

폰에서 파일 하나만 열어도(인터넷·서버 없이) 진단·계산기·관심종목이 모두 동작한다.
사용:  python3 scripts/build_standalone.py [출력경로]
기본 출력: /workspace/attachments/YYYY-MM-DD/종목-진단-대시보드.html
"""
import json, os, re, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "diagnose.html")
DATA = os.path.join(ROOT, "data", "diagnose.json")


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        "/workspace/attachments", datetime.date.today().isoformat(), "종목-진단-대시보드.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    html = open(SRC, encoding="utf-8").read()
    data = json.load(open(DATA, encoding="utf-8"))
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # </script> 로 스크립트가 끊기지 않게 '<' 를 이스케이프한다(JSON에서는 \u003c 와 < 가 같은 값)
    payload = payload.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")

    # 파일 하나로 열면 index.html 이 없으니 돌아가기 링크를 안내 문구로 바꾼다
    html = html.replace('<a class="back" href="index.html">← 급등주 리포트</a>',
                        '<span class="back" style="color:var(--tx3)">파일로 받은 버전</span>')

    tag = '<script id="diag-data" type="application/json">%s</script>\n<script>' % payload
    assert html.count("<script>") == 1, "스크립트 블록이 하나여야 합니다"
    html = html.replace("<script>", tag, 1)

    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("wrote", out, os.path.getsize(out), "bytes")


if __name__ == "__main__":
    main()

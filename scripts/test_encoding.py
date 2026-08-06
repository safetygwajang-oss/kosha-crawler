"""네이버 카페 한글 인코딩 4가지 방식 동시 테스트

각 방식으로 다른 제목의 테스트 글을 올려서 카페에서 눈으로 비교.
"""
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlencode

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import requests
from kosha_crawler.config import settings
from kosha_crawler.naver_auth import NaverTokenManager

TEST_TEXT = "실내 인테리어 공사 10대 안전수칙"


def method_A_utf8_quote_string_body(token: str) -> str:
    """방식 A: quote(UTF-8) + 문자열 body + .encode('utf-8')"""
    subject = quote(f"[A-UTF8문자열] {TEST_TEXT}")
    content = quote(f"본문: {TEST_TEXT}")
    body = f"subject={subject}&content={content}"
    r = requests.post(
        settings.cafe_article_api,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=body.encode("utf-8"),
        timeout=60,
    )
    return f"A: {r.status_code} {r.text[:200]}"


def method_B_euckr_quote_string_body(token: str) -> str:
    """방식 B: quote(EUC-KR) + 문자열 body + .encode('ascii')"""
    subject = quote(f"[B-EUCKR문자열] {TEST_TEXT}", encoding="euc-kr")
    content = quote(f"본문: {TEST_TEXT}", encoding="euc-kr")
    body = f"subject={subject}&content={content}"
    r = requests.post(
        settings.cafe_article_api,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=body.encode("ascii"),
        timeout=60,
    )
    return f"B: {r.status_code} {r.text[:200]}"


def method_C_euckr_quote_charset_header(token: str) -> str:
    """방식 C: quote(EUC-KR) + Content-Type에 charset=euc-kr 명시"""
    subject = quote(f"[C-EUCKR헤더] {TEST_TEXT}", encoding="euc-kr")
    content = quote(f"본문: {TEST_TEXT}", encoding="euc-kr")
    body = f"subject={subject}&content={content}"
    r = requests.post(
        settings.cafe_article_api,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded; charset=euc-kr",
        },
        data=body.encode("ascii"),
        timeout=60,
    )
    return f"C: {r.status_code} {r.text[:200]}"


def method_D_double_quote_utf8(token: str) -> str:
    """방식 D: quote(quote(text)) 이중 인코딩 (사용자 힌트)"""
    subject = quote(quote(f"[D-이중인코딩] {TEST_TEXT}", safe=''), safe='')
    content = quote(quote(f"본문: {TEST_TEXT}", safe=''), safe='')
    body = f"subject={subject}&content={content}"
    r = requests.post(
        settings.cafe_article_api,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=body.encode("utf-8"),
        timeout=60,
    )
    return f"D: {r.status_code} {r.text[:200]}"


def main():
    tm = NaverTokenManager()
    token = tm.get_token()

    methods = [
        ("A (UTF-8 문자열body)", method_A_utf8_quote_string_body),
        ("B (EUC-KR 문자열body)", method_B_euckr_quote_string_body),
        ("C (EUC-KR charset헤더)", method_C_euckr_quote_charset_header),
        ("D (UTF-8 이중인코딩)", method_D_double_quote_utf8),
    ]

    print("="*70)
    print("네이버 카페 한글 인코딩 4가지 방식 테스트")
    print("="*70)
    print("카페에서 어떤 접두어 글이 정상 한글로 표시되는지 눈으로 확인하세요:")
    print("  [A-UTF8문자열] / [B-EUCKR문자열] / [C-EUCKR헤더] / [D-이중인코딩]")
    print("="*70)

    for name, fn in methods:
        try:
            result = fn(token)
            print(f"\n[{name}]\n{result}")
        except Exception as e:
            print(f"\n[{name}]\nERROR: {e}")
        # 연속 등록 차단 회피
        print("  ...30초 대기")
        time.sleep(30)

    print("\n" + "="*70)
    print("완료! 카페에 가서 4개 글의 제목/본문을 눈으로 확인 후 알려주세요.")
    print("="*70)


if __name__ == "__main__":
    main()

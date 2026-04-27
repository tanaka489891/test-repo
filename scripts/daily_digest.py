#!/usr/bin/env python3
"""
脊柱管狭窄症 デイリーダイジェスト
毎朝 9:45 に cron で実行し、daily_digest/YYYY-MM-DD.md を生成する。
依存: ddgs requests beautifulsoup4
"""

import re
import sys
import textwrap
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── 設定 ──────────────────────────────────────────────────────────────────────
QUERY           = "脊柱管狭窄症"
MAX_RESULTS     = 15
FETCH_DETAIL    = True   # 各 URL の本文を追加取得するか
DETAIL_CHARS    = 400    # 本文の最大取得文字数
OUTPUT_DIR      = Path(__file__).parent.parent / "daily_digest"
REQUEST_TIMEOUT = 10
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
    "Accept-Encoding": "gzip, deflate, br",
}

# Google News RSS（APIキー不要・制限緩め）
GNEWS_URL = (
    "https://news.google.com/rss/search"
    "?q={query}&hl=ja&gl=JP&ceid=JP:ja"
)

# ── 重要度スコアリング用キーワード ────────────────────────────────────────────
PRIORITY_KEYWORDS = [
    "治療", "手術", "薬", "リハビリ", "最新", "研究", "ガイドライン",
    "原因", "症状", "診断", "予防", "保存療法", "内視鏡", "MRI",
    "ブロック注射", "神経", "腰痛", "間欠性跛行",
]
# ─────────────────────────────────────────────────────────────────────────────


# ── 検索ソース ─────────────────────────────────────────────────────────────────

def _search_google_news(query: str, max_results: int) -> list[dict]:
    """Google News RSS から記事を取得する。"""
    import urllib.parse
    url = GNEWS_URL.format(query=urllib.parse.quote(query))
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
        resp.raise_for_status()
    except Exception as e:
        print(f"[警告] Google News RSS 取得失敗: {e}", file=sys.stderr)
        return []

    articles = []
    try:
        root = ET.fromstring(resp.content)
        for item in root.iter("item"):
            title_el  = item.find("title")
            link_el   = item.find("link")
            date_el   = item.find("pubDate")
            source_el = item.find("source")

            title  = title_el.text  if title_el  is not None else ""
            url_   = link_el.text   if link_el   is not None else ""
            date_  = date_el.text   if date_el   is not None else ""
            source = source_el.text if source_el is not None else ""

            # "記事タイトル - 媒体名" 形式を分離
            if " - " in (title or ""):
                parts = title.rsplit(" - ", 1)
                title  = parts[0].strip()
                source = source or parts[1].strip()

            # pubDate (RFC 2822) を ISO 形式に変換
            if date_:
                try:
                    dt = parsedate_to_datetime(date_)
                    date_ = dt.astimezone(timezone.utc).isoformat()
                except Exception:
                    pass

            articles.append({
                "title":  title,
                "url":    url_,
                "body":   "",
                "date":   date_,
                "source": source,
                "type":   "news",
            })
            if len(articles) >= max_results:
                break
    except ET.ParseError as e:
        print(f"[警告] RSS 解析エラー: {e}", file=sys.stderr)

    return articles


def _search_ddgs(query: str, max_results: int) -> list[dict]:
    """DuckDuckGo（ddgs）でフォールバック検索。"""
    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            print("[警告] ddgs パッケージが見つかりません。pip install ddgs", file=sys.stderr)
            return []

    articles = []
    try:
        time.sleep(2)  # レートリミット回避
        with DDGS() as ddg:
            results = list(ddg.text(query, max_results=max_results, region="jp-jp"))
            for item in results:
                articles.append({
                    "title":  item.get("title", ""),
                    "url":    item.get("href", ""),
                    "body":   item.get("body", ""),
                    "date":   "",
                    "source": "",
                    "type":   "web",
                })
    except Exception as e:
        print(f"[警告] DuckDuckGo 検索エラー: {e}", file=sys.stderr)

    return articles


def search_articles(query: str, max_results: int) -> list[dict]:
    """Google News RSS → 不足分を DuckDuckGo で補完。"""
    articles = _search_google_news(query, max_results)
    print(f"  Google News RSS: {len(articles)} 件", file=sys.stderr)

    if len(articles) < max_results:
        remain = max_results - len(articles)
        seen   = {a["url"] for a in articles}
        extras = _search_ddgs(query, remain)
        for a in extras:
            if a["url"] not in seen:
                articles.append(a)
                seen.add(a["url"])
        print(f"  DuckDuckGo 補完: +{len(articles) - (max_results - remain)} 件",
              file=sys.stderr)

    return articles


# ── 本文取得 ──────────────────────────────────────────────────────────────────

def fetch_excerpt(url: str, max_chars: int) -> str:
    """URL の本文冒頭を返す。失敗時は空文字。"""
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT,
                            headers=HEADERS, allow_redirects=True)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        return text[:max_chars].rstrip()
    except Exception:
        return ""


# ── スコアリング & ランキング ─────────────────────────────────────────────────

def score_article(article: dict) -> int:
    text = (article.get("title", "") + " " + article.get("body", ""))
    score = sum(1 for kw in PRIORITY_KEYWORDS if kw in text)
    if article.get("type") == "news":
        score += 2
    if article.get("date"):
        score += 1
    return score


def rank_articles(articles: list[dict]) -> list[dict]:
    return sorted(articles, key=score_article, reverse=True)


# ── Markdown 生成 ─────────────────────────────────────────────────────────────

def _format_date(date_str: str) -> str:
    if not date_str:
        return "日付不明"
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y年%m月%d日")
    except ValueError:
        return date_str


def format_article(rank: int, article: dict, excerpt: str) -> str:
    title  = article.get("title", "（タイトルなし）")
    url    = article.get("url", "")
    source = article.get("source", "")
    body   = excerpt or article.get("body", "")

    meta_parts = []
    if source:
        meta_parts.append(f"📰 {source}")
    meta_parts.append(f"🗓 {_format_date(article.get('date', ''))}")
    meta = "　".join(meta_parts)

    wrapped = textwrap.fill(body, width=80) if body else "（本文取得なし）"

    return (
        f"### {rank}. {title}\n\n"
        f"{meta}\n\n"
        f"{wrapped}\n\n"
        f"🔗 {url}\n"
    )


def build_digest(articles: list[dict]) -> str:
    today = date.today().strftime("%Y年%m月%d日")
    now   = datetime.now().strftime("%H:%M")
    lines = [
        "# 脊柱管狭窄症 デイリーダイジェスト",
        "",
        f"**{today}  {now} 時点**　|　取得件数: {len(articles)} 件",
        "",
        "---",
        "",
    ]

    for i, article in enumerate(articles, start=1):
        excerpt = ""
        if FETCH_DETAIL and article.get("url"):
            print(f"  [{i}/{len(articles)}] 本文取得: {article['url'][:60]}…",
                  file=sys.stderr)
            excerpt = fetch_excerpt(article["url"], DETAIL_CHARS)

        lines.append(format_article(i, article, excerpt))
        lines.append("---")
        lines.append("")

    lines += [
        f"*自動生成 by daily_digest.py　クエリ: `{QUERY}`*",
    ]
    return "\n".join(lines)


# ── エントリポイント ──────────────────────────────────────────────────────────

def main() -> None:
    today_str   = date.today().strftime("%Y-%m-%d")
    output_path = OUTPUT_DIR / f"{today_str}.md"

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 記事を検索中: {QUERY}",
          file=sys.stderr)
    articles = search_articles(QUERY, MAX_RESULTS)
    print(f"  合計: {len(articles)} 件", file=sys.stderr)

    if not articles:
        print("[エラー] 記事が取得できませんでした。", file=sys.stderr)
        sys.exit(1)

    ranked = rank_articles(articles)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] ダイジェスト生成中…",
          file=sys.stderr)
    digest = build_digest(ranked)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(digest, encoding="utf-8")
    print(f"[完了] {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()

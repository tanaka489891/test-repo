#!/usr/bin/env python3
"""
脊柱管狭窄症 デイリーダイジェスト
毎朝 9:45 に cron で実行し、daily_digest/YYYY-MM-DD.md を生成する。
依存: duckduckgo-search requests beautifulsoup4
"""

import os
import re
import sys
import textwrap
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

# ── 設定 ──────────────────────────────────────────────────────────────────────
QUERY        = "脊柱管狭窄症"
MAX_RESULTS  = 15          # DDG から取得する件数
FETCH_DETAIL = True        # 各 URL の本文を取得して概要を抽出するか
DETAIL_CHARS = 400         # 本文から抜き出す文字数
OUTPUT_DIR   = Path(__file__).parent.parent / "daily_digest"
REQUEST_TIMEOUT = 10       # 各 URL の取得タイムアウト（秒）
UA = (
    "Mozilla/5.0 (compatible; DailyDigestBot/1.0; "
    "+https://489891.com/)"
)
# ── 優先キーワード（スコアリング用） ──────────────────────────────────────────
PRIORITY_KEYWORDS = [
    "治療", "手術", "薬", "リハビリ", "最新", "研究", "ガイドライン",
    "原因", "症状", "診断", "予防", "保存療法", "内視鏡", "MRI",
]
# ─────────────────────────────────────────────────────────────────────────────


def search_articles(query: str, max_results: int) -> list[dict]:
    """DuckDuckGo でニュース＋通常検索して結果をまとめる。"""
    articles = []
    with DDGS() as ddg:
        # ニュース検索（最新記事を優先）
        try:
            news = list(ddg.news(query, max_results=max_results, region="jp-jp"))
            for item in news:
                articles.append(
                    {
                        "title": item.get("title", ""),
                        "url":   item.get("url", ""),
                        "body":  item.get("body", ""),
                        "date":  item.get("date", ""),
                        "source": item.get("source", ""),
                        "type":  "news",
                    }
                )
        except Exception as e:
            print(f"[警告] ニュース検索エラー: {e}", file=sys.stderr)

        # 通常検索（ニュースで足りない場合に補完）
        if len(articles) < max_results:
            try:
                remain = max_results - len(articles)
                results = list(ddg.text(query, max_results=remain, region="jp-jp"))
                seen = {a["url"] for a in articles}
                for item in results:
                    if item.get("href", "") not in seen:
                        articles.append(
                            {
                                "title":  item.get("title", ""),
                                "url":    item.get("href", ""),
                                "body":   item.get("body", ""),
                                "date":   "",
                                "source": "",
                                "type":   "web",
                            }
                        )
            except Exception as e:
                print(f"[警告] 通常検索エラー: {e}", file=sys.stderr)

    return articles


def fetch_excerpt(url: str, max_chars: int) -> str:
    """URL にアクセスして本文テキストの冒頭を返す。失敗時は空文字。"""
    try:
        resp = requests.get(
            url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": UA}
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # script / style を除去
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        return text[:max_chars].rstrip()
    except Exception:
        return ""


def score_article(article: dict) -> int:
    """優先キーワードの出現数でスコアリング（大きいほど重要）。"""
    text = (article.get("title", "") + " " + article.get("body", "")).lower()
    score = sum(1 for kw in PRIORITY_KEYWORDS if kw in text)
    # ニュース記事は加点
    if article.get("type") == "news":
        score += 2
    # 日付あり記事は加点
    if article.get("date"):
        score += 1
    return score


def rank_articles(articles: list[dict]) -> list[dict]:
    """スコア降順でソート。同スコアはニュース優先。"""
    return sorted(articles, key=score_article, reverse=True)


def format_article(rank: int, article: dict, excerpt: str) -> str:
    """1件分の Markdown を組み立てる。"""
    title  = article.get("title", "（タイトルなし）")
    url    = article.get("url", "")
    date_  = article.get("date", "")
    source = article.get("source", "")
    body   = excerpt or article.get("body", "")

    meta_parts = []
    if source:
        meta_parts.append(f"📰 {source}")
    if date_:
        # ISO 形式を読みやすく変換
        try:
            dt = datetime.fromisoformat(date_.replace("Z", "+00:00"))
            meta_parts.append(f"🗓 {dt.strftime('%Y年%m月%d日')}")
        except ValueError:
            meta_parts.append(f"🗓 {date_}")
    meta = "　".join(meta_parts) if meta_parts else "日付不明"

    # 本文を折り返し
    wrapped_body = textwrap.fill(body, width=80) if body else "（本文取得なし）"

    return (
        f"### {rank}. {title}\n\n"
        f"{meta}\n\n"
        f"{wrapped_body}\n\n"
        f"🔗 {url}\n"
    )


def build_digest(articles: list[dict]) -> str:
    """Markdown 全体を組み立てる。"""
    today = date.today().strftime("%Y年%m月%d日")
    now   = datetime.now().strftime("%H:%M")
    lines = [
        f"# 脊柱管狭窄症 デイリーダイジェスト",
        f"",
        f"**{today}  {now} 時点**　|　取得件数: {len(articles)} 件",
        f"",
        "---",
        "",
    ]

    for i, article in enumerate(articles, start=1):
        excerpt = ""
        if FETCH_DETAIL and article.get("url"):
            print(f"  [{i}/{len(articles)}] 本文取得中: {article['url'][:60]}…",
                  file=sys.stderr)
            excerpt = fetch_excerpt(article["url"], DETAIL_CHARS)

        lines.append(format_article(i, article, excerpt))
        lines.append("---")
        lines.append("")

    lines += [
        "---",
        f"*自動生成 by daily_digest.py　クエリ: `{QUERY}`*",
    ]
    return "\n".join(lines)


def main() -> None:
    today_str = date.today().strftime("%Y-%m-%d")
    output_path = OUTPUT_DIR / f"{today_str}.md"

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 記事を検索中: {QUERY}",
          file=sys.stderr)
    articles = search_articles(QUERY, MAX_RESULTS)
    print(f"  取得: {len(articles)} 件", file=sys.stderr)

    if not articles:
        print("[警告] 記事が取得できませんでした。", file=sys.stderr)
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

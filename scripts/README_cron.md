# デイリーダイジェスト セットアップ手順

## 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

## 2. 動作確認

```bash
python scripts/daily_digest.py
# → daily_digest/YYYY-MM-DD.md が生成される
```

## 3. cron 設定（毎朝 9:45 に自動実行）

```bash
crontab -e
```

以下の1行を追加（パスは環境に合わせて変更してください）:

```
45 9 * * * cd /home/user/test-repo && python scripts/daily_digest.py >> /tmp/digest.log 2>&1
```

| フィールド | 値 | 意味 |
|---|---|---|
| 分 | 45 | 45分 |
| 時 | 9 | 9時 |
| 日/月/曜日 | * | 毎日 |

## 4. 出力ファイル

`daily_digest/YYYY-MM-DD.md` に重要度順で保存されます。

## カスタマイズ

`scripts/daily_digest.py` 冒頭の設定変数で調整できます:

| 変数 | デフォルト | 説明 |
|---|---|---|
| `MAX_RESULTS` | 15 | 取得する記事数 |
| `FETCH_DETAIL` | True | 各URLの本文を追加取得するか |
| `DETAIL_CHARS` | 400 | 本文から抜き出す文字数 |
| `PRIORITY_KEYWORDS` | 治療/手術/薬… | 重要度スコアリングに使うキーワード |

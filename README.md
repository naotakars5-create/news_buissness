# ☀️ ちば営業朝刊

**「千葉で働く営業マンへ。毎朝3分、今日の商談で使える地元ネタ・営業心理・トーク例が届く。」**

千葉県内で働く20〜30代の営業マン全般（保険・不動産・人材・金融・車・住宅・IT・メーカー・商社・法人・ルート・新人・飛び込み 等）向けに、**平日毎朝7:30**にLINEで配信する有料ニュースレターサービスです。特定業種に偏らず、千葉の情報を「営業で使える形」に変換して届けます。

配信は **LINE Flex Message（3枚カード）** が標準で、**プレーンテキストにフォールバック**します。原稿は「営業で使える朝のインサイト」として次の構成（本文 900〜1,400字）です。

| セクション | 内容 |
| --- | --- |
| 今日のテーマ | その日の千葉トピックを一言で |
| ① 今日の千葉トピック | 千葉県内の街・店・交通・イベント・企業の動きなど（独自要約） |
| ② 営業マンが見るべき理由 | そのネタが商談でなぜ効くか |
| ③ 刺さりやすい営業・業界 | 誰に刺さるかを具体的に明記 |
| ④ 商談での使い方 | いつ・どう切り出すか |
| ⑤ そのまま使える営業トーク | 今日すぐ声に出せる一言（毎回1つ以上） |
| ⑥ 切り返し例 | よくある断り文句への返し（毎回1つ） |
| ⑦ 今日の営業心理・行動経済学 | 損失回避・社会的証明など理論を1つ、かみ砕いて |
| ⑧ 今日のアクション | 今日すぐやれる具体行動 |
| ⑨ 出典 | ソース名とURL（記事本文は転載しない・URLは必ず保持） |

**カード構成（3枚カルーセル・色分け）**：①千葉ネタ＝青 ／ ②営業トーク＋切り返し＝緑 ／ ③心理＋アクション＝オレンジ。各カードに「📎 出典を見る」ボタン付き。

> 補助金・助成金・公募・入札・調達・委託・プロポーザル等の行政調達ネタは扱いません（収集時に自動除外）。

---

## 特徴 / 設計方針

- **管理画面（Streamlit）** で原稿を作成・保存・確認し、**人が承認してから配信**します（いきなり完全自動配信はしません）。
- **AI（Claude）** で原稿のたたき台を自動生成 → 人が編集して仕上げます。
- **配信対象は支払い済みユーザーのみ。** CSV / Google Sheets で購読者を管理し、Stripe で支払い状況を判定できます。
- **毎朝7:30の自動配信** は GitHub Actions（または Cloud Run）で実行。**「承認済み(approved)」の原稿だけ**が送られるので、承認し忘れた日は安全にスキップされます。
- **本番運用前提**：エラーはログに残し、**配信失敗者を1人ずつ記録**します。

---

## ディレクトリ構成

```
news_buissness/
├── app.py                       # 管理画面（Streamlit）
├── requirements.txt
├── .env.example                 # 環境変数サンプル（.env にコピーして使う）
├── chiba_asakan/                # 本体パッケージ
│   ├── config.py                # 環境変数・パスの一元管理
│   ├── logging_config.py        # ロギング（ファイル＋コンソール）
│   ├── models.py                # 原稿モデル / LINEメッセージ整形
│   ├── storage.py               # 原稿の保存・読込（JSON）
│   ├── subscribers.py           # 購読者の読込（CSV / Google Sheets）
│   ├── stripe_filter.py         # Stripe で支払い済み判定
│   ├── line_client.py           # LINE Messaging API（push送信）
│   ├── ai_writer.py             # Claude で原稿たたき台生成
│   └── delivery.py              # 配信オーケストレーション＋失敗者記録
├── scripts/
│   └── send_morning.py          # 自動配信スクリプト（cron / Actions / Cloud Run）
├── data/
│   ├── subscribers.example.csv  # 購読者CSVのサンプル
│   ├── drafts/                  # 原稿（YYYY-MM-DD.json / 承認済みは approved=true）
│   └── delivery_logs/           # 配信結果ログ（成功・失敗者）
├── logs/                        # アプリログ
└── .github/workflows/
    └── morning_delivery.yml     # 毎朝7:30の自動配信
```

---

## セットアップ手順

### 1. Python と依存パッケージ

Python 3.10 以上を推奨します。

```bash
# 仮想環境（任意だが推奨）
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 依存インストール
pip install -r requirements.txt
```

> Google Sheets を使わない場合、`gspread` / `google-auth` はインストールしなくても CSV 運用で動きます。

### 2. 環境変数（.env）

`.env.example` を `.env` にコピーして各キーを設定します。

```bash
cp .env.example .env
```

| 変数 | 説明 | 取得先 |
| --- | --- | --- |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE 配信用トークン | LINE Developers → Messaging API チャネル → チャネルアクセストークン（長期） |
| `ANTHROPIC_API_KEY` | AI原稿生成のキー | <https://console.anthropic.com> → API Keys |
| `STRIPE_API_KEY` | Stripe シークレットキー | Stripe ダッシュボード → 開発者 → APIキー（`sk_...`） |
| `REQUIRE_STRIPE_PAID` | `true` でStripeをライブ照会／`false` でCSVの`paid`列で判定 | — |
| `AI_MODEL` | 使うモデル（既定 `claude-opus-4-8`、コスト優先なら `claude-sonnet-4-6`） | — |
| `SUBSCRIBER_SOURCE` | `csv` または `google_sheets` | — |

> **秘密情報の管理:** APIキー類は必ず `.env` に置き、コミットしないでください（`.gitignore` 済み）。

### 3. 購読者リストの用意

`data/subscribers.example.csv` を参考に `data/subscribers.csv` を作成します。

```csv
line_user_id,name,stripe_customer_id,paid,active,note
Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx,山田太郎,cus_XXXXXXXX,true,true,
```

| 列 | 意味 |
| --- | --- |
| `line_user_id` | LINEユーザーID（`U` から始まる33文字・必須） |
| `name` | 表示名（任意） |
| `stripe_customer_id` | Stripe顧客ID（`REQUIRE_STRIPE_PAID=true` のとき照会に使用） |
| `paid` | 支払い済みフラグ（`REQUIRE_STRIPE_PAID=false` のときの判定に使用） |
| `active` | 配信ON/OFF（`false` で配信対象外＝退会・一時停止） |
| `note` | 備考（任意） |

> **LINEユーザーIDの取得**：ユーザーが公式アカウントを友だち追加し、Webhook で受け取った `userId`（`U...`）を使います。MVPでは手動でCSVに追記する運用を想定しています（取得方法は下記）。

#### 自分の userId を取得する（`LINE_TEST_USER_ID` のセット）

「テスト配信」で自分のLINEに送るには、自分の userId（`U` から始まる文字列）が必要です。同梱の簡易 Webhook サーバで取得できます。

1. `.env` に `LINE_CHANNEL_ACCESS_TOKEN` を設定（任意で `LINE_CHANNEL_SECRET` も。あると署名検証されます）。
2. Webhook 受信サーバを起動（標準ライブラリのみ・追加インストール不要）:
   ```bash
   python -m scripts.line_webhook        # 既定 0.0.0.0:8000 /callback で待受
   ```
3. ローカルを公開URLにする（どちらか）:
   ```bash
   ngrok http 8000                       # → https://xxxx.ngrok-free.app が発行される
   # または: cloudflared tunnel --url http://localhost:8000
   ```
4. **LINE Developers コンソール → 対象の Messaging API チャネル → Messaging API設定**:
   - **Webhook URL** に `https://xxxx.ngrok-free.app/callback`（公開URL + `/callback`）を設定し「検証」。
   - **Webhookの利用** を ON。
   - （任意）「応答メッセージ」「あいさつメッセージ」は OFF でも userId 取得には影響しません。
5. **自分のスマホのLINE** で、その公式アカウントを友だち追加し、何かメッセージを送信。
6. `line_webhook` のコンソールに userId が大きく表示されます:
   ```
   ================ LINE userId 取得 ================
     userId : Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
     内容   : message: テスト
     → .env に貼り付け:
        LINE_TEST_USER_ID=Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   =================================================
   ```
7. 表示された行を `.env` の `LINE_TEST_USER_ID` に貼り付け、`Ctrl+C` でサーバを停止。
8. 以降、管理画面「③ 原稿確認・承認 → 🧪 テスト配信」で自分のLINEに実送信して見た目を確認できます。

> このサーバは userId 取得のための一時的なツールです（本番のWebhook常時運用ではありません）。同じ要領で、購読者の userId も友だち追加時の `follow` イベントから取得できます。

#### Google Sheets で管理する場合（任意）

1. Google Cloud でサービスアカウントを作成し、JSONキーを `google_service_account.json` として配置。
2. 対象スプレッドシートを、そのサービスアカウントのメールアドレスに共有。
3. `.env` に `SUBSCRIBER_SOURCE=google_sheets`、`GOOGLE_SHEETS_ID`、`GOOGLE_SHEETS_WORKSHEET` を設定。
4. シート1行目を CSV と同じ見出し（`line_user_id, name, ...`）にする。

---

## 🧪 AI APIキーなしで「LINEテスト配信」する手順（最短）

AI（Anthropic / OpenAI）のキーが無くても、**LINEに自分宛のテスト配信**だけ先に成功させられます。
必要な `.env` 項目は **2つだけ**です。

```ini
LINE_CHANNEL_ACCESS_TOKEN=（LINE Developers のチャネルアクセストークン）
LINE_TEST_USER_ID=（自分の userId。取得方法は上記「自分の userId を取得する」参照）
```

> `LINE_CHANNEL_SECRET` はWebhook（userId取得）用です。**テスト配信だけなら未設定でOK**（エラーになりません）。
> `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` は **空欄のままでアプリは起動します**（OpenAIは本アプリでは使いません）。

手順:

1. `pip install -r requirements.txt`
2. `.env` に上記2項目を入力して保存
3. `streamlit run app.py`
4. 一番左の **「🧪 LINEテスト配信」タブ** を開く
   - 上部に `LINE_CHANNEL_ACCESS_TOKEN` と `LINE_TEST_USER_ID` が **🟢 設定済み** と出ていればOK（値そのものは表示されません）
5. **「📤 テストメッセージを送信」** を押す → 自分のLINEに次が届けば成功:
   ```
   【ちば営業朝刊】
   LINEテスト配信に成功しました。
   このメッセージが届いていれば、LINE配信設定は完了です。
   ```
6. 任意の文章を送りたいときは、同じタブの **「② 手動入力したテキストを送信」** に入力して送信。

**結果表示と失敗時のログ**
- 画面に **送信成功 / 失敗** が表示されます。
- 失敗した場合は、エラー内容が **`logs/line_test.log`** に記録されます（秘密情報は記録しません。userId も伏せ字）。
- うまくいかない時の例: トークンが誤り→`401`、userIdが誤り→`400`。`logs/line_test.log` の `response=` を確認してください。

> この段階では「① 原稿作成」のAI自動生成ボタンは無効化されています（キー設定後に有効化）。手動入力での原稿作成と本配信は利用できます。

---

## 使い方

### 管理画面を起動

```bash
streamlit run app.py
```

ブラウザで開いたら、サイドバーで各接続（LINE / AI / Stripe / 購読者）の状態を確認できます。

1. **① 原稿作成・編集**
   - 配信日を選び、4セクションを入力（または「🤖 AIで下書きを生成」でたたき台を作成 → 編集）。
   - 「💾 保存（下書き）」で保存、内容が揃ったら「✅ 保存して承認」。
   - 下部に LINE プレビューが表示されます。
2. **② 原稿確認・配信**
   - 原稿を選び、プレビューと**配信対象者数（支払い済み）**を確認。
   - 「🧪 ドライラン」で実送信せず対象者数だけ確認。
   - 内容を確認のチェックを入れ、**承認済み**の原稿を「📤 LINEで本番配信」。
3. **③ 配信ログ**
   - 過去の配信結果、**失敗者一覧**を確認。
4. **④ 購読者**
   - 読み込んだ購読者と支払い判定（配信対象か）を一覧表示。

### コマンドラインから配信（自動配信と同じ処理）

```bash
# 今日（Asia/Tokyo基準）の承認済み原稿を配信
python -m scripts.send_morning

# 日付指定 / ドライラン
python -m scripts.send_morning --date 2026-06-25 --dry-run

# 承認チェックを飛ばして強制配信（手動リカバリ用）
python -m scripts.send_morning --force
```

終了コード: `0`=正常（配信 or 対象なしスキップ）／`1`=設定不足・原稿不備／`2`=一部失敗者あり。

---

## 🪪 カード配信（LINE Flex Message）

配信は **Flex Message（3枚カルーセル）が標準**で、端末や送信に失敗した場合は **プレーンテキストに自動フォールバック**します（受信者は必ず内容を受け取れます）。

- カード1（青）: 今日の千葉トピック＋見るべき理由＋「刺さる」タグ
- カード2（緑）: 営業トーク＋切り返し例＋商談での使い方
- カード3（オレンジ）: 営業心理＋今日のアクション
- 各カードに「📎 出典を見る」ボタン（出典URLが無い場合はボタン非表示）

### 管理画面での確認・調整・配信（③ 原稿確認・承認 タブ）

- **プレビュー切替**：「🪪 カードプレビュー（3枚）」と「📄 テキスト表示」をタブで確認。
- **デザイン調整**：「🎨 カードのデザイン調整」で **3色（青・緑・オレンジ）** と **1カードの本文最大文字数** を変更でき、プレビュー・テスト配信・本配信に反映されます。
- **テスト配信（自分のLINEへ）**：送信形式を **「カード（Flex）」/「テキスト」** から選んで自分に送信。
- **本配信**：「📤 LINEで本配信（カード）」＝Flex標準。Flex送信に失敗した受信者だけ自動でテキストに切り替わります（配信ログの `mode` が `flex` / `text` / `flex→text` で分かります）。

### プレーンテキストとカードの切り替え方

| 場面 | 切り替え方 |
| --- | --- |
| テスト配信 | ③タブの「送信形式」ラジオで都度選択 |
| 本配信（管理画面） | 「本配信（カード）」ボタン＝Flex標準。失敗時のみテキストに自動フォールバック |
| 自動配信（GitHub Actions） | 既定でFlex。`send_morning.py` は内部で `use_flex=True`、失敗時テキスト |
| コードで強制テキスト | `deliver(cfg, m, use_flex=False)` |

> Flex JSONは `chiba_asakan/line_flex.py` で生成しています。色やカード構成を恒久的に変えたい場合はこのファイルの `DEFAULT_COLORS` / `build_carousel` を編集してください。

---

## 毎朝7:30の自動配信（Streamlitで承認 → GitHub Actionsで配信）

**役割分担**
- **Streamlit 管理画面**＝原稿の作成・確認・**承認**・LINEテスト配信（人が操作）。
- **GitHub Actions**＝毎朝7:30に**承認済み原稿だけ**を自動配信（無人）。
- Streamlit を常時起動して自動配信する設計にはしません。

**運用フロー**

```
前日or当日朝: Streamlitで原稿を手動作成（AIなしでOK）
  ↓ ③原稿確認・承認タブで「承認」（status=approved / approved=true）
  ↓ 承認済みJSON(data/drafts/<日付>.json)を git commit & push
翌朝7:30: GitHub Actions が承認済み原稿を自動配信
          （承認済みが無ければ「承認済み原稿なし」とログを残し配信しない）
```

### セットアップ（GitHub Actions）

`.github/workflows/morning_delivery.yml` が `30 22 * * 0-4`（UTC）= **JST平日7:30** に `scripts/send_morning.py` を実行します。

1. このリポジトリを GitHub に push。
2. **Settings → Secrets and variables → Actions** で登録。
   - **Secrets（必須）**: `LINE_CHANNEL_ACCESS_TOKEN`
   - **Secrets（自分宛てテストする場合）**: `LINE_TEST_USER_ID`
   - **Secrets（全購読者へ配信する場合）**: `SUBSCRIBERS_CSV`（購読者CSVの“中身”を貼り付け。個人情報をリポジトリに置かずに済む）／Stripe使用時 `STRIPE_API_KEY`／Sheets使用時 `GOOGLE_SERVICE_ACCOUNT_JSON`
   - **Variables（任意）**: `REQUIRE_STRIPE_PAID`, `SUBSCRIBER_SOURCE`, `GOOGLE_SHEETS_ID`, `GOOGLE_SHEETS_WORKSHEET`
3. **承認した原稿をリポジトリへ反映**：`data/drafts/*.json` は**コミット対象**です（`.gitignore` していません）。
   ```bash
   git add data/drafts/2026-06-27.json
   git commit -m "approve 2026-06-27"
   git push
   ```
4. **配信先の決まり方**（`morning_delivery.yml` が自動判定）:
   - 手動実行で「自分だけに配信」を選んだ → `LINE_TEST_USER_ID` のみ
   - `SUBSCRIBERS_CSV` を登録済み → 全購読者
   - どちらも無い → 自動的に `LINE_TEST_USER_ID`（自分）だけに配信（**まずはこれが安全**）
5. 承認済み原稿が無い日は配信されず、ログに **「承認済み原稿なし」** を残して正常終了します。

> **まず自分宛てで試す最短手順**：Secrets に `LINE_CHANNEL_ACCESS_TOKEN` と `LINE_TEST_USER_ID` だけ登録 → Streamlitで原稿を手動作成・承認 → `data/drafts/<日付>.json` を push → 翌朝7:30に自分のLINEへ届く（または Actions タブから手動実行で即テスト）。

> 手元での動作確認: `python -m scripts.send_morning --to-test-user --dry-run`（送信せず対象確認）／`python -m scripts.send_morning --to-test-user`（自分に実送信）。

> GitHub Actions の cron は数分ずれることがあります。厳密な時刻が必要なら Cloud Run（下記）を検討してください。

### 方法B: Cloud Run + Cloud Scheduler

1. コンテナ化（例：`python:3.12-slim` に `requirements.txt` を入れて `python -m scripts.send_morning` を実行）。
2. **Cloud Run Job** としてデプロイ。環境変数（`.env` の内容）を Cloud Run に設定。
3. **Cloud Scheduler** で `30 7 * * 1-5`、タイムゾーン `Asia/Tokyo` を指定して Job を起動。
4. 原稿・購読者は GCS や DB に置く運用に拡張するのがおすすめ（MVPはローカルJSON/CSV）。

---

## ログ・運用

- アプリログ: `logs/app.log`（5MB×5世代でローテーション）。
- 配信結果: `data/delivery_logs/<日付>_<時刻>.json`
  - `target_count`（配信対象）, `sent_count`（成功）, `failed_count`（失敗）
  - `results[]` に1人ずつの `status`（sent/failed）と `error`、HTTPステータスを記録。
  - **配信失敗者は WARNING でログにも残ります。**
- Stripe 照会エラー時は、その購読者を**安全側で配信対象外**にし、ログに記録します（誤配信防止）。

---

## よくある質問

**Q. まずは Stripe なしで始められますか？**
A. はい。`REQUIRE_STRIPE_PAID=false` にして、CSV の `paid` 列で手動管理すれば Stripe 連携なしで配信できます。

**Q. テスト配信したい。**
A. 管理画面の「🧪 ドライラン」か `python -m scripts.send_morning --dry-run` を使うと、実送信せず対象者数だけ確認できます。自分のLINEユーザーIDだけ `data/subscribers.csv` に入れて少人数で本番テストするのも有効です。

**Q. AIキーが無くても使えますか？**
A. はい。AIたたき台生成が使えないだけで、原稿を手入力すれば配信できます。

---

# 📰 ネタ収集・自動原稿生成（フェーズ2）

千葉の情報ソースを巡回 →（補助金等を）除外 → 営業向けに採点 → 高得点ネタから濃い原稿を自動生成、までを行います。

## 全体の流れ

```
情報ソース巡回 → 除外フィルター → スコアリング → 候補保存(data/source_items)
        → AIで原稿たたき台生成(status=draft) → 人が管理画面で確認・承認(approved)
        → 7:30 に承認済みだけ配信
```

## ネタ収集の使い方

### 管理画面から（手動）
1. `streamlit run app.py` →「② ネタ一覧」タブ。
2. **「🔄 情報ソースを巡回して取得」** を押すと、巡回・除外判定・採点・保存まで実行されます。
3. スコア順にネタが並びます。除外されたネタは「🚫 除外されたネタ」に理由つきで表示。
4. 出典URLは「開く」リンクから確認できます。
5. 使いたいネタを選んで **「使うネタを保存」** または **「選択ネタから原稿を生成」**。

### コマンドラインから
```bash
python -m scripts.collect_news                 # 今日ぶんを収集（除外・採点・保存まで）
python -m scripts.collect_news --date 2026-06-25
```
保存先: `data/source_items/<日付>.json`（id / title / url / published_at / summary / area / category / score / score_reason / excluded / exclude_reason / used_in_draft …）。

> 著作権配慮：取得するのはタイトル・URL・公開日・短い概要のみ。配信文は AI が独自の営業視点で書き換え、**出典URLを必ず保存**します。

## 情報ソースの追加・有効化

ソースは `chiba_asakan/sources/` にあります（`prtimes` / `prefecture` / `city_news` / `tourism` / `commerce`）。

- **PR TIMES** は既定で有効（公開RDFフィードを使い、千葉関連だけ抽出）。
- **県・市・観光・商業** のフィードURLは自治体都合で変わるため既定は未設定です。`.env` の `SOURCE_FEED_OVERRIDES`（JSON）でRSS/AtomのURLを設定すると有効化されます。

```bash
# .env 例（実際のフィードURLは各サイトで確認して設定）
ENABLED_SOURCES=prtimes,prefecture,city,tourism,commerce
SOURCE_FEED_OVERRIDES={"prefecture":"https://www.pref.chiba.lg.jp/.../rss.xml","city:千葉市":"https://www.city.chiba.jp/.../rss.xml","city:船橋市":"https://.../rss.xml","tourism":"https://.../rss.xml","commerce":"https://.../rss.xml"}
```

**新しいソースを足す**には `FeedSource` を継承して `feed_urls` を設定するだけです（RSS/Atom/RDF対応・標準ライブラリで解析）。HTML専用サイトは `collect()` を独自実装すれば追加できます。

## 除外フィルターの調整

`chiba_asakan/exclusion.py` にキーワードを定義しています。

- **ハード除外**（必ず除外）: 補助金・助成金・公募・入札・調達・電子調達・仕様書・プロポーザル・募集要項・企画提案・落札・業務委託 など。
- **ソフト除外**（許可語があれば残す）: 委託・契約・募集 など。
- **許可語**（イベント等として残す）: イベント・参加者募集・体験・フェア・オープン・リニューアル など。
- 「イベント参加者募集」のような一般イベントは**残し**、除外/保持の**理由を必ず記録**します（管理画面の「② ネタ一覧」で確認）。

追加で必ず除外したい語は `.env` の `EXCLUDE_KEYWORDS_EXTRA`（カンマ区切り）で足せます。
本格的に変えたい場合は `HARD_EXCLUDE / SOFT_EXCLUDE / ALLOW_KEYWORDS` を編集してください。

## ネタの採点（スコアリング）

`chiba_asakan/scoring.py` が 6 項目 ×0〜5 点で採点し、合計を `sales_score`（0〜30）として保存します。
合計 **20点以上**（`SCORE_THRESHOLD`）が原稿候補になります。

| 項目 | 内容 |
| --- | --- |
| 千葉県内性 / 営業で使える度 / 20〜30代に刺さる度 / 今日性・新しさ / 雑談に使いやすい度 / 提案につながる度 | 各 0〜5 |

- 既定は **heuristic（ルールベース）**：高速・無料・決定的。`score_reason` に根拠が残ります。
- `SCORING_MODE=ai` にすると Claude で採点（任意・APIコスト発生）。失敗時は自動で heuristic にフォールバック。

## 原稿の自動下書き生成

```bash
python -m scripts.generate_draft                       # 今日の候補から下書き生成（status=draft）
python -m scripts.generate_draft --length 1200 --psychology 損失回避
```
- 候補ネタ（score≥しきい値・除外なし）の上位から AI が 5 セクション原稿を生成。
- **承認はしません**（status=draft のまま）。既に承認済み/配信済みの日は上書きしません（`--force-overwrite` で可）。

## 毎朝の自動処理フロー

| 時刻(JST) | 処理 | スクリプト / ワークフロー |
| --- | --- | --- |
| 6:30 | ソース巡回・除外・採点・候補保存 | `scripts/collect_news.py`（`morning_pipeline.yml`） |
| 6:45 | 候補から原稿案を生成（`draft`、承認しない） | `scripts/generate_draft.py`（`morning_pipeline.yml`） |
| 7:30 | **承認済み(approved)のみ**配信／無ければ理由をログに残しスキップ | `scripts/send_morning.py`（`morning_delivery.yml`／既存・変更なし） |

GitHub Actions では、6:30/6:45 の生成物（`data/source_items` / `data/drafts`）を `morning_pipeline.yml` がリポジトリへ自動コミットします。
人は GitHub 上の差分か、ローカルで `git pull` 後に管理画面で確認し、**承認した原稿をコミット&プッシュ**します。

> 6:45→7:30 の間に人の承認が必要です。時間が取りにくい場合は「前日夜に翌日ぶんを生成・承認」する運用や、永続ストレージのある Cloud Run 運用を推奨します。

GitHub に登録する Variables（`vars`）に追加できる項目：
`SCORING_MODE`, `SCORE_THRESHOLD`, `DRAFT_LENGTH_DEFAULT`, `ENABLED_SOURCES`, `SOURCE_FEED_OVERRIDES`, `EXCLUDE_KEYWORDS_EXTRA`。

## 管理画面での承認・テスト配信・本配信

「③ 原稿確認・承認」タブで操作します。

1. 原稿を選ぶ → LINEプレビューを確認。
2. **「✅ この原稿を承認する」** で `approved` に（取り消しも可）。
3. **🧪 テスト配信**：`.env` の `LINE_TEST_USER_ID`（自分のLINE userId）に実送信して見た目を確認。
4. **📊 ドライラン**：実送信せず配信対象者数だけ確認。
5. **📤 本配信**：承認済み＆設定OK＆チェックを入れたうえで、支払い済みユーザーへ配信。

---

## テスト

```bash
pip install -r requirements.txt   # pytest を含む
python -m pytest -q
```

含まれるテスト（`tests/`）：
- ソース取得・フィード解析（`test_sources.py`）
- 除外フィルター／補助金・公募・入札の除外・一般イベントの保持（`test_exclusion.py`）
- スコアリング（`test_scoring.py`）
- 原稿生成・**出典URLが保存される**（`test_ai_writer.py`／AnthropicはフェイクでネットワークなしOK）
- **承認済み原稿のみ配信される**安全設計・ドライラン対象者（`test_delivery.py`）
- ネタ保存・候補抽出（`test_source_store.py`）

## .env に追加が必要な項目（フェーズ2）

| 変数 | 既定 | 説明 |
| --- | --- | --- |
| `ENABLED_SOURCES` | `prtimes,prefecture,city,tourism,commerce` | 有効にするソース |
| `SOURCE_FEED_OVERRIDES` | （空） | 各ソースのフィードURL（JSON）。県・市・観光・商業はここで設定して有効化 |
| `SCORE_THRESHOLD` | `20` | 原稿候補にする合計点のしきい値 |
| `SCORING_MODE` | `heuristic` | `heuristic` か `ai` |
| `DRAFT_LENGTH_DEFAULT` | `1000` | 自動生成の文字量（800/1000/1200） |
| `EXCLUDE_KEYWORDS_EXTRA` | （空） | 追加のハード除外語（カンマ区切り） |
| `LINE_TEST_USER_ID` | （空） | テスト配信の送信先（自分のLINE userId） |

---

## 今後の拡張案（フェーズ3以降）

- 購読者の DB 化（SQLite/Postgres）と Webhook での自動登録・退会
- Stripe Webhook で支払い状態をリアルタイム同期
- 配信失敗者の自動リトライ / 無効ユーザーの自動オフ
- HTML専用サイト向けスクレイパの追加、フィードURLの精度向上
- 原稿のバージョン管理・複数ライター対応・AI採点の本格運用

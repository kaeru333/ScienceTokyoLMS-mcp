# Science Tokyo LMS MCP

東京科学大学 (Science Tokyo) の LMS を操作する MCP (Model Context Protocol) サーバです．
講義資料のダウンロードや課題締切の確認などを，MCP クライアント (Claude 等) から
ツールとして呼び出せるようにします．

> [!WARNING]
> 本ツールは **個人の学修利用** を前提とします．大学システムへの自動アクセスは
> 利用規約に抵触する場合があります．利用前に Science Tokyo の規約を確認し，
> アクセス頻度を抑える (キャッシュ・低頻度アクセス) など節度ある運用をしてください．

## 対象と基盤

- **対象 LMS:** Science Tokyo LMS (`https://lms.s.isct.ac.jp/<年度>/`)
- **基盤:** **Moodle** (確認済み)．年度ごとにパスが分かれる (例: `/2025/`)．
- **方式:** Moodle **Web Services REST API** + モバイルトークン認証．
  ブラウザ巡回 (スクレイピング) ではなく公式 API を用いるため安定・高速．
- データ取得層 (`client/moodle_client.py`) は実装済みですが，**実トークンでの
  動作確認は未実施**です (下記 `science-tokyo-lms-login` で取得後に検証してください)．

## 認証方針 (MFA 必須前提)

Science Tokyo は SAML2 SSO (`isct.ex-tic.com` / MFA 必須) で保護されています．
そのためパスワードによるトークン発行は使えません．代わりに **Moodle モバイルアプリと
同じ launch フロー**を用います．

```bash
# 初回のみ: ブラウザが開くので SSO ログイン (MFA 含む) を完了する
# → モバイルトークンを取得し keyring に保存する
uv run science-tokyo-lms-login
```

取得したトークンは keyring (利用不可なら `.auth/wstoken`，いずれも .gitignore 済み) に
保存され，以降はブラウザ不要で Web Services API を呼び出します．トークンが失効したら
再度上記コマンドを実行してください．

## セットアップ

```bash
uv sync                              # 依存関係の同期
uv run playwright install chromium   # 使用するブラウザを取得 (chromium / firefox / webkit)
cp .env.example .env                 # 必要に応じて編集 (年度・ブラウザ等)
```

## 設定 (`.env`)

主な設定項目 (環境変数 `STLMS_*`，`.env` で指定可)．

| 変数 | 既定 | 説明 |
|---|---|---|
| `STLMS_LMS_BASE_URL` | `.../2025/` | Moodle のベース URL (年度ごとにパスが変わる) |
| `STLMS_BROWSER` | `chromium` | トークン取得に使うブラウザ (`chromium` / `firefox` / `webkit`) |
| `STLMS_TOKEN_BACKEND` | `auto` | トークン保存方式 (`auto` / `keyring` / `file`) |
| `STLMS_WSTOKEN` | (なし) | トークンを直接指定する場合 (最優先) |

> keyring (パスワードストア) が使えない環境では `STLMS_TOKEN_BACKEND=file` を指定すると，
> トークンを `.auth/wstoken` (.gitignore 済み，パーミッション 0600) に保存します．

## 起動

```bash
uv run science-tokyo-lms-mcp         # MCP サーバを stdio で起動
```

MCP クライアント (例: Claude Desktop / Claude Code) には以下のように登録します．

```json
{
  "mcpServers": {
    "science-tokyo-lms": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/ScienceTokyoLMS-mcp", "science-tokyo-lms-mcp"]
    }
  }
}
```

## 提供ツール

| ツール | 説明 |
|---|---|
| `list_courses` | 履修中コースの一覧 |
| `list_materials(course_id)` | 講義資料の一覧 |
| `download_material(course_id, material_id, dest_dir?)` | 講義資料のダウンロード |
| `list_assignments(course_id?)` | 課題と締切の一覧 |
| `get_upcoming_deadlines(days=7)` | 直近の課題を締切順に取得 |
| `list_announcements(course_id?)` | お知らせ・休講情報 (アナウンス) の一覧 |

> 課題の提出済み判定は別 API が必要なため，現状 `submitted` は常に `false` です
> (今後 `mod_assign_get_submission_status` で対応予定)．

## 主な Moodle Web Services 関数の対応

| ツール | Web Services 関数 |
|---|---|
| `list_courses` | `core_webservice_get_site_info` + `core_enrol_get_users_courses` |
| `list_materials` | `core_course_get_contents` |
| `list_assignments` | `mod_assign_get_assignments` |
| `list_announcements` | `mod_forum_get_forums_by_courses` + `mod_forum_get_forum_discussions` |

## ディレクトリ構成

```
src/science_tokyo_lms_mcp/
├── server.py              # FastMCP サーバ (エントリポイント)
├── login.py               # 初回トークン取得 CLI
├── config.py              # 設定 (環境変数 STLMS_*)
├── models.py              # データモデル
├── auth/
│   ├── session.py         # Playwright 永続セッション管理
│   └── token.py           # モバイルトークンの取得・保管 (keyring)
├── client/
│   ├── base.py            # LMSClient プロトコル
│   ├── moodle_client.py   # Moodle Web Services 実装 (既定)
│   └── playwright_client.py  # スクレイピング方式のフォールバック
└── tools/                 # MCP ツール (courses / materials / deadlines / announcements)
```

## 開発

```bash
uv run ruff format .      # フォーマット
uv run ruff check .       # Lint
uv run ty check           # 型チェック
uv run pytest             # テスト
```

## セキュリティ

- 認証情報・cookie・トークン・ダウンロード資料は **コミットしない** (`.gitignore` 済み)．
- パスワードはコード・設定に保持せず，SSO は永続プロファイルに，トークンは keyring に委ねます．
- リポジトリは **private 運用** を推奨します．

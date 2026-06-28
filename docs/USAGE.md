# Science Tokyo LMS MCP 使い方ガイド (研究室メンバー向け)

このドキュメントは，Science Tokyo LMS MCP サーバを **各自の PC に導入して使い始める**
ための手順をまとめたものです．技術的な内部仕様はリポジトリ直下の `README.md` を参照してください．

> [!IMPORTANT]
> **利用上の注意 (必ず読むこと)**
> 本ツールは **個人の学修利用** を前提とした補助ツールです．大学システムへの自動アクセスは
> 利用規約に抵触する場合があります．以下を守ってください．
> - 自分のアカウント・自分の履修科目に対してのみ使う．
> - 短時間に何度も叩かない (締切確認などは 1 日数回程度に留める)．
> - 取得した資料・トークン・cookie を **他人に渡さない / 公開リポジトリに上げない**．
> - 認証情報 (`.env`・`.auth/`) は **各自の環境にだけ** 置く．共有しない．

---

## 1. これは何か

LMS の操作を MCP (Model Context Protocol) ツールとして公開し，
**Claude (Claude Desktop / Claude Code) との会話から** 呼び出せるようにするサーバです．
たとえば次のようなことを自然言語で頼めます．

- 「履修中のコース一覧を見せて」
- 「今週締切の課題を締切順に並べて」
- 「○○ の講義資料を一覧して，最新回の PDF をダウンロードして」
- 「休講のお知らせが出ていないか確認して」

裏側では Moodle の **公式 Web Services REST API** を使うため，画面スクレイピングより
安定・高速です．

### できること (提供ツール)

| ツール | できること |
|---|---|
| `list_courses` | 履修中コースの一覧 |
| `list_materials(course_id)` | 指定コースの講義資料一覧 |
| `download_material(course_id, material_id, dest_dir?)` | 講義資料のダウンロード |
| `list_assignments(course_id?)` | 課題と締切の一覧 (コース省略で全コース横断) |
| `get_upcoming_deadlines(days=7)` | 直近の未提出課題を締切順に取得 |
| `list_announcements(course_id?)` | お知らせ・休講情報の一覧 |
| `submit_assignment_files(assignment_id, file_paths, confirm=False)` | 課題へのファイル提出 (2 段階: 既定はプレビュー) |

> 補足: 課題の提出済み判定は別 API が必要なため，現状 `get_upcoming_deadlines` は
> 「締切が近い課題」を出しますが，提出済みかどうかは正確に反映されないことがあります．

#### 課題のファイル提出 (`submit_assignment_files`)

ファイルを提出する際は，**2 段階**で安全に行います．

1. まず `confirm=False` (既定) で呼びます．この段階では Moodle へ**書き込みません**．
   課題の説明文・提出制約 (許可拡張子・最大サイズ・最大数)・各ファイルの検査結果が返ります．
2. Claude が提出予定ファイルを開いて中身を確認し，課題の説明文と照らして「このファイルで
   合っているか」を判断します．
3. 問題なければ `confirm=True` で同じ引数を渡して再度呼ぶと，実際に提出されます．

```
あなた: 「課題 123 にこのレポート ~/report.pdf を出して」
Claude: (submit_assignment_files(assignment_id="123", file_paths=["~/report.pdf"]) を実行)
        → 課題の説明・許可拡張子・ファイル検査結果を確認し，report.pdf の中身を開いて照合
Claude: 「課題の指示と内容が一致しています．提出してよいですか？」
あなた: 「お願い」
Claude: (confirm=True で再実行) → 提出完了
```

> **注意**
> - 採点提出は課題設定によっては**取り消せません**．まずはテスト用課題で試すと安心です．
> - 拡張子が許可リストと明確に異なるファイルは `confirm=True` でも提出を中止します．
> - 提出規約のある課題は，`confirm=True` の実行をもって規約に同意したものとして提出します．

---

## 2. 必要なもの (前提環境)

- **Python 3.13 以上**
- **uv** (Python パッケージ管理ツール) … [公式手順](https://docs.astral.sh/uv/) でインストール
- **Web ブラウザ** … 初回ログイン時に Playwright が自動で用意します (既定は Chromium)
- **Science Tokyo のアカウント** … SSO ログイン (MFA 含む) ができること

uv が入っているかは次で確認できます．

```bash
uv --version
```

---

## 3. セットアップ (初回のみ)

リポジトリを取得したディレクトリで，順番に実行します．

```bash
# 1) リポジトリを取得 (URL は研究室の共有先に置き換え)
git clone <リポジトリの URL> ScienceTokyoLMS-mcp
cd ScienceTokyoLMS-mcp

# 2) 依存関係をインストール
uv sync

# 3) トークン取得用のブラウザを用意 (chromium / firefox / webkit のいずれか)
uv run playwright install chromium

# 4) 設定ファイルを用意 (必要に応じて後で編集)
cp .env.example .env
```

> `.env` は **各自の環境専用** です．git 管理から外してあります (`.gitignore` 済み)．

---

## 4. 初回ログイン (トークン取得)

LMS は SAML2 SSO + MFA で保護されているため，パスワードでのトークン発行はできません．
代わりに **Moodle モバイルアプリと同じログインフロー** をブラウザで一度だけ実行します．

```bash
uv run science-tokyo-lms-login
```

- ブラウザが自動で開きます．Science Tokyo の **SSO ログイン (MFA 含む) を完了** してください．
- 成功すると `トークンを取得・保存しました．` と表示されます．
- 取得したトークンは **keyring (OS のパスワードストア)** に保存されます．
  以降はブラウザ不要で API を呼べます．

> [!TIP]
> 一度ログインするとブラウザのセッションが `.auth/profile/` に残るため，
> 次回のトークン取得は MFA の再入力なしで通ることがあります．

### keyring が使えない環境のとき

サーバ・WSL・一部の Linux など，OS のパスワードストアが無い環境では keyring 保存に失敗します．
その場合は `.env` に次を書いてからログインし直すと，トークンをファイル
(`.auth/wstoken`，パーミッション 0600，`.gitignore` 済み) に保存します．

```bash
STLMS_TOKEN_BACKEND=file
```

---

## 5. MCP クライアントへの登録

### 5-1. Claude Code (CLI) で使う

リポジトリのディレクトリで，次の 1 コマンドで登録できます (project スコープ推奨)．

```bash
claude mcp add science-tokyo-lms --scope project -- \
  uv run --directory /absolute/path/to/ScienceTokyoLMS-mcp science-tokyo-lms-mcp
```

`--directory` には **リポジトリの絶対パス** を指定してください．
登録後，`/mcp` で `science-tokyo-lms` が `Connected` になっていれば成功です．

> project スコープ (`.mcp.json`) にすると，リポジトリ配下の **サブディレクトリで作業していても**
> 親を遡って設定が読まれます．特定のフォルダだけで使いたいときは `--scope local` でも構いません．

### 5-2. Claude Desktop で使う

設定ファイル `claude_desktop_config.json` に次を追記します．

```json
{
  "mcpServers": {
    "science-tokyo-lms": {
      "command": "uv",
      "args": [
        "run", "--directory", "/absolute/path/to/ScienceTokyoLMS-mcp",
        "science-tokyo-lms-mcp"
      ]
    }
  }
}
```

設定ファイルの場所 (OS 別):

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

追記したら Claude Desktop を再起動してください．

### 5-3. Codex CLI で使う

OpenAI Codex CLI も MCP サーバに対応しています (比較的新しいバージョンが必要)．
設定は `~/.codex/config.toml` に書きます．次を追記してください．

```toml
[mcp_servers.science-tokyo-lms]
command = "uv"
args = ["run", "--directory", "/absolute/path/to/ScienceTokyoLMS-mcp", "science-tokyo-lms-mcp"]
```

`args` の `--directory` には **リポジトリの絶対パス** を指定してください．

CLI から追加する場合は次のコマンドでも登録できます (バージョンによっては未対応)．

```bash
codex mcp add science-tokyo-lms -- \
  uv run --directory /absolute/path/to/ScienceTokyoLMS-mcp science-tokyo-lms-mcp
```

登録状況は `codex mcp list`，削除は `codex mcp remove science-tokyo-lms` で確認・操作できます．
設定後に Codex を起動し直すと，会話からツールを呼べるようになります．

> [!NOTE]
> Codex 側で MCP サーバの起動がタイムアウトする場合は，初回の `uv sync` が完了しているか，
> `uv run science-tokyo-lms-mcp` が単体で起動するかを先に確認してください
> (依存の初回解決に時間がかかることがあります)．

---

## 6. 使ってみる (会話例)

登録できたら，Claude に普通の日本語で頼むだけです．Claude が必要なツールを選んで呼びます．

```
あなた: 履修中のコースを一覧して
Claude: (list_courses を実行) → コース名と course_id の一覧を表示

あなた: 今週締切の課題を締切が近い順に教えて
Claude: (get_upcoming_deadlines を実行) → 締切順の未提出課題リスト

あなた: コース 12345 の資料を一覧して，最新回の PDF を downloads に保存して
Claude: (list_materials → download_material を実行) → 保存先の絶対パスを表示

あなた: 休講のお知らせが出ていないか確認して
Claude: (list_announcements を実行) → 直近のお知らせ一覧
```

> ダウンロード先を指定しない場合は，既定で `downloads/` に保存されます
> (`.env` の `STLMS_DOWNLOAD_DIR` で変更可)．

---

## 7. 設定 (`.env`) の主な項目

環境変数 `STLMS_*` または `.env` で指定します．通常は既定のままで動きます．

| 変数 | 既定 | 説明 |
|---|---|---|
| `STLMS_LMS_BASE_URL` | `https://lms.s.isct.ac.jp/2025/` | Moodle のベース URL．**年度ごとにパスが変わる** |
| `STLMS_BROWSER` | `chromium` | トークン取得に使うブラウザ (`chromium` / `firefox` / `webkit`) |
| `STLMS_TOKEN_BACKEND` | `auto` | トークン保存方式 (`auto` / `keyring` / `file`) |
| `STLMS_DOWNLOAD_DIR` | `downloads` | 講義資料の保存先 |
| `STLMS_WSTOKEN` | (なし) | トークンを直接指定する場合 (最優先) |

### 年度が変わったら

新年度になったら `.env` の `STLMS_LMS_BASE_URL` の年度部分を書き換えてください．

```bash
STLMS_LMS_BASE_URL=https://lms.s.isct.ac.jp/2026/
```

URL を変えるとトークンの保存キーも変わるため，**新しい年度で一度ログインし直す** 必要があります．

---

## 8. トラブルシューティング

| 症状 | 対処 |
|---|---|
| ツール呼び出しで認証エラー / 空の結果 | トークン失効の可能性．`uv run science-tokyo-lms-login` で再取得する |
| `トークンを取得できませんでした` (タイムアウト) | 5 分以内に SSO + MFA を完了する．再実行で再試行 |
| keyring 保存に失敗する | `.env` に `STLMS_TOKEN_BACKEND=file` を設定して再ログイン |
| ブラウザが起動しない | `uv run playwright install chromium` を実行したか確認 |
| Claude から見えない / `Failed` 表示 | `--directory` の絶対パスを確認．Desktop は再起動．`uv run science-tokyo-lms-mcp` 単体で起動するか確認 |
| 別年度のコースが出てくる | `.env` の `STLMS_LMS_BASE_URL` の年度を確認し，必要なら再ログイン |

サーバが単体で起動するかの確認 (stdio で待ち受けます．`Ctrl+C` で終了):

```bash
uv run science-tokyo-lms-mcp
```

---

## 9. 研究室で共有するときの注意

- **共有してよいもの:** ソースコード一式 (リポジトリそのもの)．
- **共有してはいけないもの:** 以下は各自の環境にだけ置き，絶対に共有しない．
  - `.env` (個人設定)
  - `.auth/` (ブラウザセッション・保存トークン)
  - `downloads/` (取得した講義資料)
  - keyring に保存されたトークン
- 上記はいずれも `.gitignore` 済みですが，**zip で固めて配る・チャットに貼る** といった
  経路で漏れないよう注意してください．
- リポジトリは **private 運用** を推奨します．
- 各メンバーは「3. セットアップ」「4. 初回ログイン」を **自分のアカウントで** 実行してください．
  トークンの使い回しはしないこと．

---

## 10. よくある質問

**Q. パスワードはどこかに保存される?**
A. いいえ．パスワードはコード・設定に一切保持しません．SSO はブラウザの永続プロファイルに，
発行されたトークンは keyring (またはファイル) に委ねます．

**Q. MFA を毎回入力する必要がある?**
A. 初回ログイン以降はトークンで API を呼ぶためログイン不要です．トークン失効時のみ再ログインします．
セッションが残っていれば，再ログイン時も MFA を省ける場合があります．

**Q. 提出済みの課題が「締切が近い」に出てしまう**
A. 提出状況の判定は別 API が必要で，現状は未対応です (今後対応予定)．表示はあくまで目安としてください．

**Q. 開発・コントリビュートしたい**
A. `README.md` に開発手順 (ruff / ty / pytest) と内部構成があります．そちらを参照してください．

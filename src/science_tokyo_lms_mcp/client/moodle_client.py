"""Moodle Web Services REST API による LMS クライアント.

取得済みトークンを用いて ``webservice/rest/server.php`` を呼び出す．
ブラウザを介さずに HTTP のみで動作するため高速かつ安定している．
:class:`~science_tokyo_lms_mcp.client.base.LMSClient` プロトコルに適合する．
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx

from science_tokyo_lms_mcp.auth.token import load_token
from science_tokyo_lms_mcp.config import Settings, get_settings
from science_tokyo_lms_mcp.models import (
    Announcement,
    Assignment,
    Course,
    Material,
    MaterialKind,
    SubmissionConstraints,
)

_JST = ZoneInfo("Asia/Tokyo")
_TAG_RE = re.compile(r"<[^>]+>")
_ANNOUNCEMENT_PER_FORUM = 10

_KIND_BY_MODNAME = {
    "resource": MaterialKind.FILE,
    "folder": MaterialKind.FILE,
    "url": MaterialKind.URL,
    "page": MaterialKind.PAGE,
}


class MoodleAPIError(RuntimeError):
    """Moodle Web Services の呼び出しに失敗した場合に送出する."""


def flatten_params(params: dict[str, Any]) -> dict[str, str]:
    """ネストした引数を Moodle 形式 (``key[0][sub]=val``) に平坦化する.

    Args:
        params: ネストし得る引数の辞書．

    Returns:
        文字列値に変換した平坦な辞書．
    """
    flat: dict[str, str] = {}

    def add(key: str, value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                add(f"{key}[{k}]", v)
        elif isinstance(value, (list, tuple)):
            for i, v in enumerate(value):
                add(f"{key}[{i}]", v)
        elif isinstance(value, bool):
            flat[key] = "1" if value else "0"
        elif value is not None:
            flat[key] = str(value)

    for key, value in params.items():
        add(key, value)
    return flat


def append_token(url: str, token: str) -> str:
    """ファイル URL にトークンクエリを付与する.

    Args:
        url: 対象の URL．
        token: Web Services トークン．

    Returns:
        ``token=`` を付与した URL．
    """
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}token={token}"


def same_host(url: str, base_url: str) -> bool:
    """``url`` のホストが ``base_url`` のホストと一致するか判定する.

    トークンを付与してよい相手 (LMS 自身) かを確認するために用いる．
    外部サイトへのトークン送出を防ぐ目的なので，判定不能な場合は ``False`` とする．

    Args:
        url: 判定対象の URL．
        base_url: 基準となる LMS のベース URL．

    Returns:
        スキームとホスト (netloc) がともに一致すれば ``True``．
    """
    target = urlsplit(url)
    base = urlsplit(base_url)
    return bool(target.netloc) and target.netloc == base.netloc and target.scheme == base.scheme


def safe_filename(name: str) -> str:
    """保存用に安全なファイル名 (パス成分を除いた basename) を返す.

    外部由来の名前に絶対パスや ``..`` が含まれていても保存先ディレクトリの
    外へ脱出できないよう，パス区切りを取り除いた末尾要素のみを採用する．

    Args:
        name: 元のファイル名 (外部データ由来)．

    Returns:
        パス成分を含まない安全なファイル名．空になる場合は ``"download"``．
    """
    # Windows 形式の区切りも basename 化の対象にするため事前に正規化する．
    candidate = Path(name.replace("\\", "/")).name
    if candidate in ("", ".", ".."):
        return "download"
    return candidate


def _to_datetime(epoch: Any) -> datetime | None:
    """UNIX 秒を JST の datetime に変換する (0 や None は None)."""
    if not epoch:
        return None
    return datetime.fromtimestamp(int(epoch), tz=_JST)


def _strip_html(text: str | None) -> str | None:
    """簡易的に HTML タグを除去する."""
    if not text:
        return text
    return _TAG_RE.sub("", text).strip()


# Moodle のファイルタイプグループ名 (document 等) の近似展開表．
# Moodle 本体はサーバ側 MIME DB で判定するため完全網羅はできない．
# ここでは実用的な主要拡張子のみを対応づける (判定はベストエフォート)．
_FILETYPE_GROUPS: dict[str, tuple[str, ...]] = {
    "document": (".doc", ".docx", ".pdf", ".rtf", ".odt", ".txt"),
    "image": (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg"),
    "spreadsheet": (".xls", ".xlsx", ".csv", ".ods"),
    "presentation": (".ppt", ".pptx", ".odp"),
    "archive": (".zip", ".tar", ".gz", ".7z"),
    "video": (".mp4", ".mov", ".avi", ".mkv"),
    "audio": (".mp3", ".wav", ".m4a", ".flac"),
    "web_file": (".html", ".htm", ".css", ".js"),
}


def _parse_filetypes(raw: str) -> tuple[str, ...]:
    """提出可能拡張子の文字列 (filetypeslist) を拡張子タプルに正規化する.

    Moodle の filetypeslist は ``.pdf,.docx`` / ``pdf docx`` / ``document`` 等が
    混在しうる．ドット始まりに正規化し，グループ名は :data:`_FILETYPE_GROUPS`
    で近似展開する．空文字なら制限なし (空タプル) とみなす．

    Args:
        raw: filetypeslist の生の値．

    Returns:
        正規化した拡張子のタプル (小文字・ドット付き，順序保持で重複除去)．
    """
    if not raw or not raw.strip():
        return ()
    tokens = re.split(r"[\s,;]+", raw.strip().lower())
    exts: list[str] = []
    for tok in tokens:
        if not tok:
            continue
        if tok in _FILETYPE_GROUPS:
            exts.extend(_FILETYPE_GROUPS[tok])
        else:
            exts.append(tok if tok.startswith(".") else f".{tok}")
    seen: dict[str, None] = {}
    for ext in exts:
        seen.setdefault(ext, None)
    return tuple(seen)


def _parse_constraints(assignment: dict[str, Any]) -> SubmissionConstraints:
    """mod_assign_get_assignments の 1 課題から提出制約を抽出する.

    Args:
        assignment: ``assignments`` 配列の 1 要素．

    Returns:
        抽出した :class:`SubmissionConstraints`．
    """
    cfg: dict[tuple[str, str], str] = {}
    for c in assignment.get("configs", []):
        key = (c.get("subtype") or "", c.get("name") or "")
        cfg[key] = c.get("value") or ""

    filetypes_raw = cfg.get(("assignsubmission_file", "filetypeslist"), "")
    max_size = int(cfg.get(("assignsubmission_file", "maxsubmissionsizebytes"), "0") or "0")
    max_files = int(cfg.get(("assignsubmission_file", "maxfilesubmissions"), "1") or "1")
    enabled = cfg.get(("assignsubmission_file", "enabled"), "1") in ("1", "")

    return SubmissionConstraints(
        file_types=_parse_filetypes(filetypes_raw),
        file_types_raw=filetypes_raw,
        max_size_bytes=max_size,
        max_files=max_files,
        submission_drafts=str(assignment.get("submissiondrafts", "0")) == "1",
        require_statement=str(assignment.get("requiresubmissionstatement", "0")) == "1",
        file_plugin_enabled=enabled,
    )


def _raise_on_warnings(result: Any, where: str) -> None:
    """提出系 API の warnings 応答を検査し，問題があれば例外化する.

    ``mod_assign_save_submission`` 等は成功時に空配列を返し，失敗時は
    warnings 配列に内容を持つ．

    Args:
        result: API 応答 (成功時は空 list)．
        where: 呼び出し元の関数名 (エラーメッセージ用)．

    Raises:
        MoodleAPIError: warnings が存在する場合．
    """
    if isinstance(result, list) and result:
        msgs = "; ".join(
            f"{w.get('item', '')}:{w.get('message', '')}" for w in result if isinstance(w, dict)
        )
        raise MoodleAPIError(f"{where} で警告が返されました: {msgs}")


class MoodleClient:
    """Moodle Web Services を用いた LMS クライアント."""

    def __init__(self, settings: Settings | None = None, token: str | None = None) -> None:
        """クライアントを初期化する.

        Args:
            settings: 実行時設定．省略時は :func:`get_settings` を用いる．
            token: Web Services トークン．省略時は保存済みトークンを読み込む．
        """
        self.settings = settings or get_settings()
        self._token = token
        self._userid: int | None = None

    @property
    def token(self) -> str:
        """Web Services トークンを取得する (未取得なら例外)."""
        if self._token is None:
            self._token = load_token(self.settings)
        if not self._token:
            msg = "トークンが未取得です．`uv run science-tokyo-lms-login` を実行してください．"
            raise MoodleAPIError(msg)
        return self._token

    async def _call(self, wsfunction: str, **params: Any) -> Any:
        """Web Services 関数を呼び出して結果を返す.

        Args:
            wsfunction: 呼び出す関数名．
            **params: 関数引数．

        Returns:
            復号済みの JSON (dict / list)．

        Raises:
            MoodleAPIError: Moodle が例外を返した場合．
        """
        data = {
            "wstoken": self.token,
            "wsfunction": wsfunction,
            "moodlewsrestformat": "json",
        }
        data.update(flatten_params(params))
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_s) as client:
            resp = await client.post(self.settings.ws_endpoint, data=data)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("exception"):
            raise MoodleAPIError(f"{payload.get('errorcode')}: {payload.get('message')}")
        return payload

    async def _get_userid(self) -> int:
        """サイト情報からユーザ ID を取得する (キャッシュ)."""
        if self._userid is None:
            info = await self._call("core_webservice_get_site_info")
            self._userid = int(info["userid"])
        return self._userid

    async def list_courses(self) -> list[Course]:
        """履修中コースの一覧を取得する."""
        userid = await self._get_userid()
        raw = await self._call("core_enrol_get_users_courses", userid=userid)
        base = self.settings.lms_base_url.rstrip("/")
        return [
            Course(
                id=str(c["id"]),
                name=c.get("fullname") or c.get("shortname") or str(c["id"]),
                code=c.get("shortname"),
                url=f"{base}/course/view.php?id={c['id']}",
            )
            for c in raw
        ]

    async def list_materials(self, course_id: str) -> list[Material]:
        """指定コースの講義資料一覧を取得する."""
        sections = await self._call("core_course_get_contents", courseid=int(course_id))
        materials: list[Material] = []
        for section in sections:
            for module in section.get("modules", []):
                materials.extend(self._materials_from_module(course_id, module))
        return materials

    def _materials_from_module(self, course_id: str, module: dict[str, Any]) -> list[Material]:
        """1 モジュールから資料を抽出する."""
        kind = _KIND_BY_MODNAME.get(module.get("modname", ""), MaterialKind.OTHER)
        files = [c for c in module.get("contents", []) if c.get("type") == "file"]
        if files:
            return [
                Material(
                    id=f"{module['id']}-{i}",
                    course_id=course_id,
                    title=module.get("name") or content.get("filename") or "",
                    kind=kind,
                    filename=content.get("filename"),
                    url=content.get("fileurl"),
                    updated_at=_to_datetime(content.get("timemodified")),
                )
                for i, content in enumerate(files)
            ]
        url = module.get("url")
        if not url:
            # label (見出しテキスト) などダウンロード対象でないモジュールは除外する．
            return []
        return [
            Material(
                id=str(module["id"]),
                course_id=course_id,
                title=module.get("name") or "",
                kind=kind,
                url=url,
            )
        ]

    async def download_material(self, material: Material, dest_dir: Path) -> Path:
        """講義資料をダウンロードする.

        トークン漏洩を防ぐため，ダウンロードは LMS 内のファイル資料に限定する．
        外部リンク (URL 種別) や他ホストへはトークンを付与・送信しない．

        Raises:
            MoodleAPIError: URL がない，ファイル種別でない，または LMS 外ホストの場合．
        """
        if not material.url:
            raise MoodleAPIError("ダウンロード可能な URL がありません．")
        if material.kind is not MaterialKind.FILE:
            raise MoodleAPIError("ファイル種別の資料のみ DL できます (外部リンクは対象外)．")
        if not same_host(material.url, self.settings.lms_base_url):
            raise MoodleAPIError("LMS 内のファイルのみダウンロードできます (外部ホストは対象外)．")
        url = append_token(material.url, self.token)
        raw_name = material.filename or material.url.split("/")[-1].split("?")[0]
        filename = safe_filename(raw_name)
        dest = Path(dest_dir) / filename
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_s) as client:
            resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return dest

    async def list_assignments(self, course_id: str | None = None) -> list[Assignment]:
        """課題と締切の一覧を取得する.

        Note:
            提出済みかどうかの判定は別 API (mod_assign_get_submission_status) が
            必要なため，現状は ``submitted=False`` 固定とする (今後対応)．
        """
        courseids = [int(course_id)] if course_id else []
        raw = await self._call("mod_assign_get_assignments", courseids=courseids)
        base = self.settings.lms_base_url.rstrip("/")
        assignments: list[Assignment] = []
        for course in raw.get("courses", []):
            cid = str(course["id"])
            for a in course.get("assignments", []):
                assignments.append(
                    Assignment(
                        id=str(a["id"]),
                        course_id=cid,
                        title=a.get("name") or "",
                        due_at=_to_datetime(a.get("duedate")),
                        submitted=False,
                        url=f"{base}/mod/assign/view.php?id={a.get('cmid')}",
                    )
                )
        return assignments

    async def get_assignment_detail(
        self, assignment_id: str
    ) -> tuple[Assignment, SubmissionConstraints]:
        """指定課題の詳細 (説明文 intro) と提出制約を取得する.

        Args:
            assignment_id: 課題 (assignment) の ID．

        Returns:
            :class:`Assignment` (intro 付き) と :class:`SubmissionConstraints` の組．

        Raises:
            MoodleAPIError: 課題が見つからない場合．
        """
        raw = await self._call("mod_assign_get_assignments")
        base = self.settings.lms_base_url.rstrip("/")
        for course in raw.get("courses", []):
            cid = str(course["id"])
            for a in course.get("assignments", []):
                if str(a["id"]) != str(assignment_id):
                    continue
                assignment = Assignment(
                    id=str(a["id"]),
                    course_id=cid,
                    title=a.get("name") or "",
                    due_at=_to_datetime(a.get("duedate")),
                    submitted=False,
                    url=f"{base}/mod/assign/view.php?id={a.get('cmid')}",
                    intro=_strip_html(a.get("intro")),
                )
                return assignment, _parse_constraints(a)
        msg = f"課題が見つかりません: assignment_id={assignment_id}"
        raise MoodleAPIError(msg)

    async def _upload_to_draft(self, file_paths: list[Path], itemid: int = 0) -> int:
        """ファイル群をドラフト領域へアップロードし draft item id を返す.

        複数ファイルは 1 つ目で得た item id を 2 つ目以降に引き継ぎ，
        同一ドラフトへ集約する．

        Args:
            file_paths: アップロードするローカルファイル．
            itemid: 集約先の draft item id (0 なら新規)．

        Returns:
            確定した draft item id．

        Raises:
            MoodleAPIError: アップロードに失敗した場合．
        """
        upload_url = f"{self.settings.lms_base_url.rstrip('/')}/webservice/upload.php"
        current = itemid
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_s) as client:
            for path in file_paths:
                data = {"token": self.token, "itemid": str(current)}
                with path.open("rb") as fh:
                    files = {"file": (path.name, fh, "application/octet-stream")}
                    resp = await client.post(upload_url, data=data, files=files)
                resp.raise_for_status()
                payload = resp.json()
                # upload.php はエラー時に REST と異なる dict 形式を返す．
                if isinstance(payload, dict) and payload.get("error"):
                    raise MoodleAPIError(
                        f"アップロード失敗: {payload.get('error')} ({payload.get('errorcode')})"
                    )
                if not isinstance(payload, list) or not payload:
                    raise MoodleAPIError("アップロード応答が不正です．")
                current = int(payload[0]["itemid"])
        return current

    async def submit_assignment_files(self, assignment_id: str, file_paths: list[Path]) -> bool:
        """ファイルを課題に提出する (ドラフト保存し，必要なら採点提出する).

        Args:
            assignment_id: 課題 (assignment) の ID．
            file_paths: 提出するローカルファイル．

        Returns:
            採点提出 (submit_for_grading) まで確定したら ``True``，
            保存のみ (保存=提出方式) なら ``False``．

        Raises:
            MoodleAPIError: 提出に失敗した場合．
        """
        _, constraints = await self.get_assignment_detail(assignment_id)
        draft_id = await self._upload_to_draft(file_paths)
        save_res = await self._call(
            "mod_assign_save_submission",
            assignmentid=int(assignment_id),
            plugindata={"files_filemanager": draft_id},
        )
        _raise_on_warnings(save_res, "mod_assign_save_submission")

        if not constraints.submission_drafts:
            return False
        submit_res = await self._call(
            "mod_assign_submit_for_grading",
            assignmentid=int(assignment_id),
            acceptsubmissionstatement=1,
        )
        _raise_on_warnings(submit_res, "mod_assign_submit_for_grading")
        return True

    async def list_announcements(self, course_id: str | None = None) -> list[Announcement]:
        """お知らせ・休講情報 (アナウンスフォーラム) の一覧を取得する."""
        if course_id is not None:
            courseids = [int(course_id)]
        else:
            courseids = [int(c.id) for c in await self.list_courses()]
        if not courseids:
            return []

        forums = await self._call("mod_forum_get_forums_by_courses", courseids=courseids)
        announcements: list[Announcement] = []
        for forum in forums:
            if forum.get("type") != "news":
                continue
            announcements.extend(await self._announcements_from_forum(forum))
        return announcements

    async def _announcements_from_forum(self, forum: dict[str, Any]) -> list[Announcement]:
        """1 つのニュースフォーラムから掲示一覧を取得する."""
        result = await self._call(
            "mod_forum_get_forum_discussions",
            forumid=int(forum["id"]),
            perpage=_ANNOUNCEMENT_PER_FORUM,
            page=0,
        )
        course_id = str(forum.get("course")) if forum.get("course") is not None else None
        discussions = result.get("discussions", []) if isinstance(result, dict) else []
        return [
            Announcement(
                id=str(d.get("discussion") or d.get("id")),
                title=d.get("name") or "",
                course_id=course_id,
                posted_at=_to_datetime(d.get("created")),
                body=_strip_html(d.get("message")),
            )
            for d in discussions
        ]

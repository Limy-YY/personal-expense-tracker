"""数据导出：将全部记录打包为可下载的 JSON 备份文件。"""

import json

from flask import Blueprint, Response

import storage

bp = Blueprint("export", __name__)


@bp.route("/api/export")
def export_records():
    """返回全量记录的 JSON 附件，触发浏览器下载。"""
    records = storage.load_records()
    data = json.dumps({"records": records}, ensure_ascii=False, indent=2)
    return Response(
        data,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=records.json"},
    )

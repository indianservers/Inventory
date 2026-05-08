import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

from flask import current_app


def backup_uploads():
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    target = Path(current_app.config["UPLOAD_FOLDER"]).parent / f"uploads-backup-{stamp}.zip"
    with ZipFile(target, "w") as zf:
        upload_root = Path(current_app.config["UPLOAD_FOLDER"])
        for file in upload_root.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(upload_root))
    return target


def backup_mysql():
    cfg = current_app.config
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    target = Path(current_app.instance_path) / f"{cfg['DB_NAME']}-{stamp}.sql"
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as fh:
        subprocess.run(
            ["mysqldump", "-h", cfg["DB_HOST"], "-P", str(cfg["DB_PORT"]), "-u", cfg["DB_USER"], f"-p{cfg['DB_PASSWORD']}", cfg["DB_NAME"]],
            stdout=fh,
            check=True,
        )
    return target


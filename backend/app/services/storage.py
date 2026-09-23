import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile


class InvalidPdfError(ValueError):
    pass


class UploadTooLargeError(ValueError):
    pass


@dataclass(frozen=True)
class StoredFile:
    original_filename: str
    sha256: str
    size_bytes: int
    relative_path: str


async def store_pdf(
    upload: UploadFile,
    storage_root: str,
    max_upload_bytes: int,
) -> StoredFile:
    original_filename = Path(upload.filename or "upload.pdf").name

    root = Path(storage_root)
    tmp_dir = root / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    hasher = hashlib.sha256()
    total_size = 0
    first_chunk = True
    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=tmp_dir,
            prefix="upload-",
            suffix=".tmp",
        ) as temp_file:
            temp_path = Path(temp_file.name)

            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break

                if first_chunk:
                    first_chunk = False
                    if not chunk.startswith(b"%PDF-"):
                        raise InvalidPdfError("uploaded file is not a valid PDF")

                total_size += len(chunk)
                if total_size > max_upload_bytes:
                    raise UploadTooLargeError(
                        f"PDF exceeds upload limit of {max_upload_bytes} bytes"
                    )

                hasher.update(chunk)
                temp_file.write(chunk)

        if total_size == 0:
            raise InvalidPdfError("uploaded PDF is empty")

        digest = hasher.hexdigest()
        relative_path = Path("documents") / digest[:2] / f"{digest}.pdf"
        final_path = root / relative_path
        final_path.parent.mkdir(parents=True, exist_ok=True)

        if final_path.exists():
            temp_path.unlink(missing_ok=True)
        else:
            os.replace(temp_path, final_path)

        return StoredFile(
            original_filename=original_filename,
            sha256=digest,
            size_bytes=total_size,
            relative_path=relative_path.as_posix(),
        )
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

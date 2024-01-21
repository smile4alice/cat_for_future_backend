import os
from typing import Type
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from sqlalchemy import func, select
import aiofiles

from src.auth.models import User
from src.auth.utils import create_user
from src.database.database import Base, get_async_session
from src.config import FILE_FORMATS, MAX_FILE_SIZE_MB, PHOTO_FORMATS, settings
from src.exceptions import INVALID_FILE, INVALID_PHOTO, OVERSIZE_FILE


async def lifespan(app: FastAPI):
    async for s in get_async_session():
        async with s.begin():
            user_count = await s.execute(select(func.count()).select_from(User))
            if user_count.scalar() == 0:
                await create_user(
                    email=settings.ADMIN_USERNAME, password=settings.ADMIN_PASSWORD
                )
    yield


async def save_photo(file: UploadFile, model: Type[Base], is_file=False) -> str:
    if not is_file and not file.content_type in PHOTO_FORMATS:
        raise HTTPException(
            status_code=415, detail=INVALID_PHOTO % (file.content_type, PHOTO_FORMATS)
        )
    if file.size > MAX_FILE_SIZE_MB**1024:
        raise HTTPException(status_code=413, detail=OVERSIZE_FILE)
    if is_file and not file.content_type in FILE_FORMATS:
        raise HTTPException(
            status_code=415, detail=INVALID_FILE % (file.content_type, FILE_FORMATS)
        )

    folder_path = os.path.join("static", model.__tablename__.lower().replace(" ", "_"))
    os.makedirs(folder_path, exist_ok=True)

    file_name = f'{uuid4().hex}.{file.filename.split(".")[-1]}'
    file_path = os.path.join(folder_path, file_name)
    async with aiofiles.open(file_path, "wb") as buffer:
        await buffer.write(await file.read())
    return file_path


async def delete_photo(path: str) -> bool:
    path_exists = os.path.exists(path)
    if path_exists:
        os.remove(path)
    return path_exists


async def update_photo(
    file: UploadFile,
    record: Type[Base],
    field_name: str,
    background_tasks: BackgroundTasks,
    is_file=False,
) -> str:
    old_photo = getattr(record, field_name, None)
    if old_photo:
        background_tasks.add_task(delete_photo, old_photo)
    return await save_photo(file, record, is_file)

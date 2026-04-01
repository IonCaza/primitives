import uuid
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import User, SSHCredential
from app.auth.dependencies import get_current_user
from app.services.encryption import generate_keypair, KeyType

router = APIRouter(prefix="/ssh-keys", tags=["ssh-keys"])


class SSHKeyCreate(BaseModel):
    name: str
    key_type: KeyType = KeyType.ED25519
    rsa_bits: int = 4096


class SSHKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_type: str
    public_key: str
    fingerprint: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("", response_model=SSHKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_ssh_key(body: SSHKeyCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if body.key_type == KeyType.RSA and body.rsa_bits not in (2048, 3072, 4096):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="RSA key size must be 2048, 3072, or 4096")
    public_key, encrypted_private, fingerprint, key_type = generate_keypair(body.key_type, body.rsa_bits)
    cred = SSHCredential(
        name=body.name,
        key_type=key_type,
        public_key=public_key,
        private_key_encrypted=encrypted_private,
        fingerprint=fingerprint,
        created_by_id=user.id,
    )
    db.add(cred)
    await db.commit()
    await db.refresh(cred)
    return cred


@router.get("", response_model=list[SSHKeyResponse])
async def list_ssh_keys(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(SSHCredential).where(SSHCredential.created_by_id == user.id).order_by(SSHCredential.created_at.desc()))
    return result.scalars().all()


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ssh_key(key_id: uuid.UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(SSHCredential).where(SSHCredential.id == key_id, SSHCredential.created_by_id == user.id))
    cred = result.scalar_one_or_none()
    if cred is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSH key not found")
    await db.delete(cred)
    await db.commit()

"""SQLite 기반 이력/중복방지 저장소"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, sessionmaker, relationship, Session
from .config import settings


class Base(DeclarativeBase):
    pass


class Media(Base):
    __tablename__ = "media"
    med_seq = Column(Integer, primary_key=True)
    title = Column(String(500))
    description = Column(Text)
    keyword = Column(Text)
    reg_date = Column(String(8))
    pbls_no = Column(String(100))
    shp_nm = Column(String(50))
    atcfl_no = Column(String(50))
    thumbnail_path = Column(String(500))
    crawled_at = Column(DateTime, default=datetime.utcnow)

    files = relationship("MediaFile", back_populates="media", cascade="all, delete")


class MediaFile(Base):
    __tablename__ = "media_files"
    id = Column(Integer, primary_key=True, autoincrement=True)
    med_seq = Column(Integer, ForeignKey("media.med_seq"))
    atcfl_no = Column(String(50))
    atcfl_seq = Column(Integer)
    original_name = Column(String(500))
    saved_path = Column(String(500))
    size = Column(BigInteger)
    downloaded_at = Column(DateTime, default=datetime.utcnow)

    media = relationship("Media", back_populates="files")
    __table_args__ = (UniqueConstraint("atcfl_no", "atcfl_seq", name="uix_file"),)


engine = create_engine(f"sqlite:///{settings.DB_PATH}", echo=False, future=True)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Session:
    return SessionLocal()


def is_media_seen(session: Session, med_seq: int) -> bool:
    return session.get(Media, med_seq) is not None


def is_file_downloaded(session: Session, atcfl_no: str, atcfl_seq: int, expected_size: int | None = None) -> bool:
    row = session.query(MediaFile).filter_by(atcfl_no=atcfl_no, atcfl_seq=atcfl_seq).first()
    if not row:
        return False
    if expected_size and row.size != expected_size:
        return False
    from pathlib import Path
    return Path(row.saved_path).exists()

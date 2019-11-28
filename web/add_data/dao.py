from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey,
                        Integer, String, Text, create_engine, func)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# DB_CONNECT = 'mysql+pymysql://root:Xiaoi@123456@192.168.160.69:3306/gallery?charset=utf8'
# DB_CONNECT = 'mysql+pymysql://root:Wcy206211.@127.0.0.1:3306/gallery?charset=utf8'
DB_CONNECT = 'mysql+pymysql://root:XiaoI/5a@4a@127.0.0.1:3306/gallery?charset=utf8'
engine = create_engine(DB_CONNECT, echo=False, encoding='utf-8')
Session = sessionmaker(bind=engine)
session = Session()
BASE = declarative_base(engine)


class image(BASE):
    __tablename__ = 'image'
    id = Column(Integer, primary_key=True, autoincrement=True)
    image_path = Column(String(1000))
    category = Column(String(100))
    tag = Column(String(1000))
    fuzzy = Column(Integer)


class Visual(BASE):
    __tablename__ = 'visual'
    id = Column(Integer, primary_key=True, autoincrement=True)
    image_path = Column(String(255))
    image_label = Column(String(2000))
    image_fuzzy = Column(Integer)


class VisualShanghai(BASE):
    __tablename__ = 'visual_shanghai'
    id = Column(Integer, primary_key=True, autoincrement=True)
    image_path = Column(String(255))
    image_label = Column(String(2000))
    image_fuzzy = Column(Integer)


myImage = image

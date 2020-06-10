# -*- coding: utf-8 -*-
import os
import redis
from contextlib import contextmanager
from flask_celery import Celery
from flask_sqlalchemy import SQLAlchemy as _SQLAlchemy
from ..extensions.weixin import WeixinPay
from .qiniu.storage import QiniuStorage
from .query_session import Query
from .loggers import LoggerHandler
from .weixin.mp import WeixinMP
from ..config.secret import MiniProgramAppId, MiniProgramAppSecret, MiniProgramWxpay_notify_url, miniprogram_dir, \
    QINIU_ACCESS_KEY, QINIU_SECRET_KEY, QINIU_BUCKET_NAME, DB_PARAMS, mch_id, mch_key, apiclient_key, apiclient_cert


class SQLAlchemy(_SQLAlchemy):
    def init_app(self, app):
        app.config.setdefault('SQLALCHEMY_DATABASE_URI', DB_PARAMS)
        app.config.setdefault('SQLALCHEMY_TRACK_MODIFICATIONS', False)
        # app.config.setdefault('SQLALCHEMY_ECHO', True)  # 开启sql日志
        super(SQLAlchemy, self).init_app(app)

    @contextmanager
    def auto_commit(self):
        try:
            yield db.session
            self.session.commit()
        except Exception as e:
            db.session.rollback()
            raise e


db = SQLAlchemy(query_class=Query, session_options={"expire_on_commit": False, "autoflush": False})

mini_wx_pay = WeixinPay(MiniProgramAppId, mch_id, mch_key, MiniProgramWxpay_notify_url, apiclient_key, apiclient_cert)

mp_miniprogram = (WeixinMP(MiniProgramAppId,
                           MiniProgramAppSecret,
                           ac_path=os.path.join(miniprogram_dir, ".access_token"),
                           jt_path=os.path.join(miniprogram_dir, ".jsapi_ticket")))

qiniu_oss = QiniuStorage(QINIU_ACCESS_KEY, QINIU_SECRET_KEY, QINIU_BUCKET_NAME)

conn = redis.Redis(host='localhost', port=6379, db=1)

celery = Celery()


def register_ext(app, logger_file='/tmp/qixing/'):
    db.init_app(app)
    celery.init_app(app)
    LoggerHandler(app, file=logger_file).error_handler()

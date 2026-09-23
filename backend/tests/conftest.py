"""pytest 全局配置：在导入应用前把数据库指向临时 SQLite。

应用导入时只是 create_engine，不会真正连接；
各用例通过 fixtures 把 engine/SessionLocal 换成共享的内存 SQLite。
"""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("JWT_SECRET", "test-secret")

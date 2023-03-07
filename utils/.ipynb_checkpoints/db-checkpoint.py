from utils.logger import logger
from collections import defaultdict, Counter
import pymysql
import json
import time
import os


class DBManager():
    def __init__(self, db_info_str, sql):
        db_info_dic = json.loads(db_info_str)
        con = pymysql.connect(**db_info_dic, charset='utf8', autocommit=True, cursorclass=pymysql.cursors.Cursor)
        self.cur = con.cursor()
        
        # update data
        self.sql = sql
        self.code2name = None
        self.name2code = None
        self.update_order_today()
        
    def update_order_today(self):
        self.cur.execute(self.sql)
        rows = self.cur.fetchall()
        self.code2name = dict(rows)
        self.name2code = dict(zip(self.code2name.values(), self.code2name.keys()))
        
        
        
        
        
class NODBManager():
    def __init__(self, nodb_path):
        self.nodb_path = nodb_path
        self.code2name = None
        self.name2code = None
        self.update_order_today()
        
    def update_order_today(self):
        with open(self.nodb_path, 'r', encoding="utf-8") as f:
            code2name = json.load(f)
        self.code2name = code2name
        self.name2code = dict(zip(self.code2name.values(), self.code2name.keys()))
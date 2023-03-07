from utils.text import *
from utils.logger import logger
from utils.camera import SentechCam, BaslerCam
from utils.ocr import OcrEngine
from utils.crypto import glance
from utils.db import DBManager, NODBManager
from utils import tool, process

import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font as font
import tkinter.filedialog as filedialog

from collections import defaultdict
from threading import Thread, Lock
from queue import Queue
from glob import glob
import numpy as np
import serial
import time
import json
import os

from tkinter import messagebox as mb

class MainWindow(tk.Tk):
    def __init__(self, *arg, nodb=False, **kwargs):
        super().__init__(*arg, **kwargs)
        self.iconbitmap(ICON_PATH)
        self.title(TITLE)
        
        # 화면 사이즈
        self.state("zoomed")
        self.geometry(f"{self.winfo_screenwidth()//5*2}x{self.winfo_screenheight()//5*2}")
        self.minsize(self.winfo_screenwidth()//5*2, self.winfo_screenheight()//5*2)
        self.win_factor = np.linalg.norm((self.winfo_screenheight(), 
                                          self.winfo_screenwidth())) / 2202.9071700822983
        
        # 디자인
        self.__configure()
        self.button1.configure(text="..", command=lambda:time.sleep(0.1))
        self.button2.configure(text="..", command=lambda:time.sleep(0.1))
        
        # 기타 변수 초기화
        self.current_origin_image = np.zeros((100,100,3), dtype=np.uint8)
        self.current_image = None
        self.today = tool.get_time_str(day=True)
        self.make_recode_dir()
        self.selected_code = None
        
        # 쓰레드 통신용
        self.stop_signal = True
        self.raw_Q = Queue()
        self.analy_Q = Queue()
        self.draw_Q = Queue()
        self.image_Q = Queue()
        self.data_Q = Queue()
        self.db_Q = Queue()
        self.recode_Q = Queue()
        self.thr_lock = Lock()
                
        # code to ~
        # self.code2polys = self.load_jsons(JSON_DIR_PATH)
        # self.code2data = defaultdict(lambda:{"ALL":0, "OK":0, "NG":0, "exist":"X"})
        # for code in self.code2polys: self.code2data[code]["exist"] = "O"
        # logger.info("Loaded JSON.")
                
        # 오래걸리는 로딩
        self.cam = None
        self.serial = True
        self.ocr_engine = None
        self.load_check_stop = False
        self.db_mng = None
        Thread(target=self.load_check, args=(), daemon=True).start()
        Thread(target=self.load_cam, args=(EXPOSURE_TIME,), daemon=True).start()
        # Thread(target=self.load_serial, args=(SERIAL_PORT,), daemon=True).start()
        Thread(target=self.load_ocr, args=(OCR_MODEL_PATH,), daemon=True).start()
        Thread(target=self.load_db, args=(nodb,), daemon=True).start()
        
        # 자동 DB, GUI 업데이트
        Thread(target=self.auto_update, args=(10,), daemon=True).start()
        
        
    #######################################################################
    def load_db(self, nodb):
        err_msg = ""
        if not nodb:
            db_info_str = glance(DB_INFO_PATH, KEY_PATH)
            with open(SQL_PATH, 'r') as f:
                sql = f.read()
            try: self.db_mng = DBManager(db_info_str, sql)
            except Exception as e:
                err_msg = "DB 로딩 실패\n테스트버전으로 전환\n"
                err_msg += str(e)
                logger.warn(e)
                mb.showwarning(title="", message=err_msg)
                
        if nodb or err_msg:
            self.db_mng = NODBManager(NODB_PATH)
            
        logger.info("Loaded DB.")
    
    def load_cam(self, ExposureTime):
        try:
            self.cam = BaslerCam(ExposureTime=ExposureTime, logger=logger, gray_scale=True)
            logger.info("Loaded Cam.")
        except:
            self.load_check_stop = True
            print(self.cam)
            mb.showwarning(title="", message="카메라 로딩 실패")
        
    def load_serial(self, port):
        try:
            self.serial = serial.Serial(port, 9600, timeout=0.05)
            logger.info("Loaded Serial.")
        except:
            self.load_check_stop = True
            mb.showwarning(title="", message="시리얼연결 실패")
        
    def load_ocr(self, model_path):
        try:
            self.ocr_engine = OcrEngine(model_path)
            logger.info("Loaded OcrEngine.")
        except:
            self.load_check_stop = True
            mb.showwarning(title="", message="OCR 모델 로딩 실패")
    
    def load_check(self):
        while True:
            time.sleep(0.1)
            if self.load_check_stop: break
            if (self.cam is not None) and (self.serial is not None) and (self.ocr_engine is not None):
                self.init_button_()
                break
                
        self.load_check_stop = True
            
    #######################################################################
    def load_jsons(self, dir_path):
        file_names = os.listdir(dir_path)
        json_paths = list(map(lambda x:os.path.join(dir_path, x), file_names))
        codes = list(map(lambda x:x.split('.')[0], file_names))
        # open json
        polys_list, moves = [], []
        for path in json_paths:
            with open(path, "r", encoding='utf-8') as f:
                data = json.load(f)
                date_shapes = list(filter(lambda x:x['label']=='date', data["shapes"]))
                move_shapes = list(filter(lambda x:x['label']=='move', data["shapes"]))
            polys = np.float32([shape["points"] for shape in date_shapes])
            move = np.float32([shape["points"] for shape in move_shapes])[0]
            polys_list.append(polys)
            moves.append(move)
        return dict(zip(codes, polys_list)), dict(zip(codes, moves))
        
    #######################################################################
    def init_gui_data(self):
        # 모든 리스트박스 청소
        self.listbox1.delete(0, 'end') # 제품명
        self.listbox2.delete(0, 'end') # 총갯수
        self.listbox3.delete(0, 'end') # OK갯수
        self.listbox4.delete(0, 'end') # NG갯수
        self.listbox5.delete(0, 'end') # 지시수량
        
        for i, code in enumerate(self.db_mng.code2name):
            self.listbox1.insert(i, self.db_mng.code2name[code]) # 제품명
            self.listbox2.insert(i, self.code2data[code]["ALL"]) # 총갯수
            self.listbox3.insert(i, self.code2data[code]["OK"]) # OK갯수
            self.listbox4.insert(i, self.code2data[code]["NG"]) # NG갯수
            self.listbox5.insert(i, self.code2data[code]["exist"]) # 등록여부
        
    #######################################################################
    def auto_update(self, period=60):
        # db_mng 대기
        while True:
            time.sleep(0.1)
            if self.db_mng is not None and self.db_mng.code2name is not None: break
        
        # DB, poly load
        self.code2polys, self.code2move = self.load_jsons(JSON_DIR_PATH)
        self.code2data = defaultdict(lambda:{"ALL":0, "OK":0, "NG":0, "exist":"?"})
        self.db_mng.update_order_today()
        
        # poly 존재여부 체크
        for code in self.db_mng.code2name:
            self.code2data[code]["exist"] = "O" if code in self.code2polys else "X"
        
        # GUI 적용
        self.init_gui_data()
        
        while True:
            time.sleep(period)
            logger.info("Auto Update!")
            
            # DB, poly reload
            self.db_mng.update_order_today()
            self.code2polys = self.load_jsons(JSON_DIR_PATH)
            
            # 날짜 바뀜 체크
            today = tool.get_time_str(day=True)
            if self.today != today:
                self.today = today
                self.code2data = defaultdict(lambda:{"ALL":0, "OK":0, "NG":0, "exist":"X"})
                
            # poly 존재여부 체크
            for code in self.db_mng.code2name:
                self.code2data[code]["exist"] = "O" if code in self.code2polys else "X"
                
            # GUI 적용
            self.init_gui_data()
            
    #######################################################################
    def select_code(self, event):
        Thread(target=self.select_code2, args=(), daemon=True).start()
        
    def select_code2(self):
        time.sleep(0.01)
        tup = self.listbox1.curselection()
        code = None
        # 선택검사
        if not tup:
            self.selected_code = None
        else:
            idx = tup[0]
            name = self.listbox1.get(idx,idx)[0]
            code = self.db_mng.name2code[name]
            
        # poly존재 검사
        if not code in self.code2polys:
            self.stop_signal = True
            mb.showinfo(title="", message="등록된 품목이 아닙니다.")
            self.selected_code = None
        else:
            self.selected_code = code
            
        # GUI 적용
        self.selected_label.configure(text=name if self.selected_code else "선택안됨")
        
    
    #######################################################################    
    def init_button_(self):
        self.button1.configure(text="...", command=lambda:time.sleep(0.1))
        self.button2.configure(text="...", command=lambda:time.sleep(0.1))
        time.sleep(0.3)
        self.button1.configure(text="▶시작", bg="#080", command=self.read_mode)
        self.button2.configure(text="●등록", command=self.add_mode)
        
    #######################################################################
    def stop(self):
        # self.write_sys_msg("중지.")
        logger.info("Stop button clicked.")
        self.stop_signal = True
    
    #######################################################################
    def read_mode(self):
        logger.info("read_mode button clicked.")
        if self.cam == None or self.serial == None:
            logger.error("device 로드 안됐는데 시작 버튼 눌림.")
            # self.write_sys_msg("ERROR : device 로드 안됐는데 시작 버튼 눌림.")
            return

        # 선택된 품목코드 가져오기
        if self.selected_code is None:
            mb.showinfo(title="", message="품목이 선택되지 않았습니다.")
            return
        
        # 선택상태에서 자동업데이트로 바뀌었을때
        if not self.selected_code in self.db_mng.code2name:
            mb.showinfo(title="", message="품목이 목록에서 사라졌습니다.")
            self.selected_code = None
            self.selected_label.configure(text=name if self.selected_code else "선택안됨")
            return
        
        # 선택상태에서 자동업데이트로 바뀌었을때 2
        if not self.selected_code in self.code2polys:
            mb.showinfo(title="", message="품목이 등록되지 않게 됐습니다.")
            self.selected_code = None
            self.selected_label.configure(text=name if self.selected_code else "선택안됨")
            return
        
        # 시작
        self.stop_signal = False
        Thread(target=self.read_thread, args=(), daemon=True).start()

    def read_thread(self):
        tool.clear_Q(self.raw_Q)
        tool.clear_Q(self.analy_Q)
        tool.clear_Q(self.draw_Q)
        tool.clear_Q(self.image_Q)
        tool.clear_Q(self.data_Q)
        tool.clear_Q(self.recode_Q)
        
        Thread(target=process.image_eater, args=(self,), daemon=True).start()
        Thread(target=process.data_eater, args=(self,), daemon=True).start()
        Thread(target=process.auto_cam, args=(self,), daemon=True).start()
        Thread(target=process.read, args=(self,), daemon=True).start()
        Thread(target=process.analysis, args=(self,), daemon=True).start()
        Thread(target=process.draw, args=(self,), daemon=True).start()
        Thread(target=process.recode, args=(self,), daemon=True).start()

        self.button1.configure(text="...", command=lambda:time.sleep(0.1))
        self.button2.configure(text="...", command=lambda:time.sleep(0.1))
        time.sleep(0.3)
        self.button1.configure(text="■중지", bg="#F00", fg="#ffffff", command=self.stop)
        self.button2.configure(text="", command=lambda:time.sleep(0.1))
        
        # self.write_sys_msg("판독모드 시작!")
        
        while not self.stop_signal: time.sleep(0.05)
        # self.thr_lock.acquire()
        # time.sleep(0.05)
        # self.serial.write(b"\xA0\x01\x00\xA1") # off
        # self.thr_lock.release()
        self.init_button_()
        self.ok_label.configure(text='', anchor='center')
        
    #######################################################################
    def add_mode(self):
        mb.showinfo(title="", message="미구현")
        pass
    
    #######################################################################
    
    #######################################################################
    def make_recode_dir(self):
        if not os.path.isdir(SAVE_IMG_DIR): os.mkdir(SAVE_IMG_DIR)
        if not os.path.isdir(SAVE_RAW_IMG_DIR): os.mkdir(SAVE_RAW_IMG_DIR)
        if not os.path.isdir(SAVE_OK_IMG_DIR): os.mkdir(SAVE_OK_IMG_DIR)
        if not os.path.isdir(SAVE_NG_IMG_DIR): os.mkdir(SAVE_NG_IMG_DIR)
    
    #######################################################################
    def __configure(self):
        # 제목
        self.title_label = tk.Label(self, bd=1, relief="solid") # "solid"
        self.title_label.place(relx=0.0, rely=0.0, relwidth=1, relheight=0.1)
        self.title_label['font'] = font.Font(family='Helvetica', size=int(50*self.win_factor), weight='bold')
        self.title_label.configure(text='소비기한 불량 검출', bg='#008', fg="#fff", anchor='center')
        
        # 이미지프레임
        self.image_frame = tk.Frame(self, bd=1, relief="solid") # "solid"
        self.image_frame.place(relx=0.0, rely=0.1, relwidth=0.3, relheight=0.3)
        # 이미지프레임 - 이미지
        self.image_label = tk.Label(self.image_frame, anchor="center", text='image')
        self.image_label.pack(expand=True, fill="both")
        
        # OK
        self.ok_label = tk.Label(self, relief="solid", bd=1) # "solid"
        self.ok_label.place(relx=0.3, rely=0.1, relwidth=0.3, relheight=0.3)
        self.ok_label['font'] = font.Font(family='Helvetica', size=int(250*self.win_factor), weight='bold')
        self.ok_label.configure(text='OK', fg='#92D050', anchor='center')
        
        # 버튼프레임
        self.btn_frame = tk.Frame(self, relief="solid", bd=1)
        self.btn_frame.place(relx=0.6, rely=0.1, relwidth=0.4, relheight=0.3)
        # 버튼프레임 - 버튼
        self.button1 = tk.Button(self.btn_frame, bd=1)
        self.button1.place(relx=0.0, rely=0.0, relwidth=0.5, relheight=0.7)
        self.button1['font'] = font.Font(family='Helvetica', size=int(70*self.win_factor), weight='bold')
        self.button1.configure(text="▶시작", bg="#080", fg="#ffffff", command=None)
        # self.button1.configure(text="■종료", bg="#F00", fg="#ffffff", command=None)
        self.button2 = tk.Button(self.btn_frame, bd=1)
        self.button2.place(relx=0.5, rely=0.0, relwidth=0.5, relheight=0.7)
        self.button2['font'] = font.Font(family='Helvetica', size=int(70*self.win_factor), weight='bold')
        self.button2.configure(text="●등록", bg="#0079BF", fg="#ffffff", command=None)
        # 버튼프레임 - 라벨
        self.selected_label = tk.Label(self.btn_frame, text="선택안됨")
        self.selected_label['font'] = font.Font(family='Helvetica', size=int(30*self.win_factor), weight='bold')
        self.selected_label.place(relx=0.0, rely=0.7, relwidth=1, relheight=0.3)
        
        # 리스트프레임
        self.list_frame = tk.Frame(self, relief=None, bd=10) # "solid"
        self.list_frame.place(relx=0.0, rely=0.4, relwidth=1, relheight=0.6)
        # 리스트프레임 - 타이틀
        self.list_frame_title = tk.Frame(self.list_frame, relief="solid", bd=2, bg="#368")
        self.list_frame_title.place(relx=0.0, rely=0.0, relwidth=1.0, relheight=0.1)
        # 리스트프레임 - 타이틀 - 라벨
        self.temp = tk.Label(self.list_frame_title, text="제품 이름", bg="#368", fg="#fff", relief="solid", bd=1)
        self.temp['font'] = font.Font(family='Helvetica', size=int(30*self.win_factor), weight='bold')
        self.temp.place(relx=0.0, rely=0.0, relwidth=0.55, relheight=1)
        self.temp = tk.Label(self.list_frame_title, text="총 수량", bg="#368", fg="#fff", relief="solid", bd=1)
        self.temp['font'] = font.Font(family='Helvetica', size=int(30*self.win_factor), weight='bold')
        self.temp.place(relx=0.55, rely=0.0, relwidth=0.10, relheight=1)
        self.temp = tk.Label(self.list_frame_title, text="OK 수량", bg="#368", fg="#fff", relief="solid", bd=1)
        self.temp['font'] = font.Font(family='Helvetica', size=int(30*self.win_factor), weight='bold')
        self.temp.place(relx=0.65, rely=0.0, relwidth=0.10, relheight=1)
        self.temp = tk.Label(self.list_frame_title, text="NG 수량", bg="#368", fg="#fff", relief="solid", bd=1)
        self.temp['font'] = font.Font(family='Helvetica', size=int(30*self.win_factor), weight='bold')
        self.temp.place(relx=0.75, rely=0.0, relwidth=0.10, relheight=1)
        self.temp = tk.Label(self.list_frame_title, text="등록여부", bg="#368", fg="#fff", relief="solid", bd=1)
        self.temp['font'] = font.Font(family='Helvetica', size=int(30*self.win_factor), weight='bold')
        self.temp.place(relx=0.85, rely=0.0, relwidth=0.10, relheight=1)
        # 리스트프레임 - 내용
        self.list_frame_content = tk.Frame(self.list_frame, relief="solid", bd=2)
        self.list_frame_content.place(relx=0.0, rely=0.1, relwidth=1.0, relheight=0.9)
        # 리스트프레임 - 내용 - 스크롤
        style = ttk.Style(self.list_frame_content)
        style.layout('arrowless.Vertical.TScrollbar', 
             [('Vertical.Scrollbar.trough',
               {'children': [('Vertical.Scrollbar.thumb', 
                              {'expand': '1', 'sticky': 'nswe'})],
                'sticky': 'ns'})])
        self.scrollbar = ttk.Scrollbar(self.list_frame_content, style='arrowless.Vertical.TScrollbar')
        self.scrollbar.pack(side="right", fill="y")
        # 리스트프레임 - 내용 - 리스트박스
        func = lambda x,y:(self.scrollbar.set(x,y), self.listbox2.yview("moveto",x), 
                           self.listbox3.yview("moveto",x), self.listbox4.yview("moveto",x), 
                           self.listbox5.yview("moveto",x), )
        self.listbox1 = tk.Listbox(self.list_frame_content, yscrollcommand=func, bg="#E2F0D9")
        self.listbox1.place(relx=0.0, rely=0.0, relwidth=0.55, relheight=1.0)
        self.listbox1['font'] = font.Font(family='Helvetica', size=int(40*self.win_factor), weight='bold')
        func = lambda x,y:self.listbox1.yview("moveto",x)
        self.listbox2 = tk.Listbox(self.list_frame_content, yscrollcommand=func, bg="#E2F0D9")
        self.listbox2.place(relx=0.55, rely=0.0, relwidth=0.10, relheight=1.0)
        self.listbox2['font'] = font.Font(family='Helvetica', size=int(40*self.win_factor), weight='bold')
        func = lambda x,y:self.listbox1.yview("moveto",x)
        self.listbox3 = tk.Listbox(self.list_frame_content, yscrollcommand=func, bg="#E2F0D9")
        self.listbox3.place(relx=0.65, rely=0.0, relwidth=0.10, relheight=1.0)
        self.listbox3['font'] = font.Font(family='Helvetica', size=int(40*self.win_factor), weight='bold')
        func = lambda x,y:self.listbox1.yview("moveto",x)
        self.listbox4 = tk.Listbox(self.list_frame_content, yscrollcommand=func, bg="#E2F0D9")
        self.listbox4.place(relx=0.75, rely=0.0, relwidth=0.10, relheight=1.0)
        self.listbox4['font'] = font.Font(family='Helvetica', size=int(40*self.win_factor), weight='bold')
        func = lambda x,y:self.listbox1.yview("moveto",x)
        self.listbox5 = tk.Listbox(self.list_frame_content, yscrollcommand=func, bg="#E2F0D9")
        self.listbox5.place(relx=0.85, rely=0.0, relwidth=0.10, relheight=1.0)
        self.listbox5['font'] = font.Font(family='Helvetica', size=int(40*self.win_factor), weight='bold')
        func = lambda x,y:(self.listbox1.yview(x,y), self.listbox2.yview(x,y), 
                           self.listbox3.yview(x,y), self.listbox4.yview(x,y), self.listbox5.yview(x,y), )
        self.scrollbar.config(command=func)
        
        self.listbox1.bind("<Button-1>", self.select_code)
        
        # test
        for i in range(20):
            self.listbox1.insert(tk.END, f"사과{i:02d}")
            self.listbox2.insert(tk.END, f"{i:02d}")
            self.listbox3.insert(tk.END, f"{i:02d}")
            self.listbox4.insert(tk.END, f"{i:02d}")
            # self.listbox5.insert(tk.END, f"{i:02d}")
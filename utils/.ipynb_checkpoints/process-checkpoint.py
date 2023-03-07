from utils.logger import logger
from utils.text import *
from utils import tool
from collections import defaultdict
from PIL import ImageFont, ImageDraw, Image, ImageTk
from threading import Thread
from functools import reduce
import numpy as np
import time
import cv2
import os
import re

##################################################### 실시간 이미지 조정
def image_eater(self): # 쓰레드 # self.image_Q에 있는 이미지 출력
    current_winfo = self.image_frame.winfo_width(), self.image_frame.winfo_height()
    while True:
        time.sleep(0.02)
        if self.stop_signal: break
        last_winfo = self.image_frame.winfo_width(), self.image_frame.winfo_height()
            
        if current_winfo == last_winfo and self.image_Q.empty(): continue
        if current_winfo != last_winfo: current_winfo = last_winfo
        if not self.image_Q.empty(): self.current_origin_image = self.image_Q.get() # BGR
        if self.current_origin_image is None: continue
            
        __auto_resize_img(self)
        # imgtk = ImageTk.PhotoImage(Image.fromarray(self.current_image[:,:,::-1]))
        imgtk = ImageTk.PhotoImage(Image.fromarray(self.current_image))
        self.image_label.configure(image=imgtk)
        self.image_label.image = imgtk
    
    self.current_origin_image = None #np.zeros((100,100,3), dtype=np.uint8)
    self.current_image = None
    self.image_label.configure(image=None)
    self.image_label.image = None
    

def __auto_resize_img(self):
    h, w = self.current_origin_image.shape[:2]
    ratio = h/w
    wh = self.image_frame.winfo_height() - 24
    ww = self.image_frame.winfo_width() - 24
    wratio = wh/ww
        
    if ratio < wratio: size, target = ww, 'w'
    else: size, target = wh, 'h'
    self.current_image = tool.fix_ratio_resize_img(self.current_origin_image, size=size, target=target)

# 실시간 데이터 수정####################################################
def data_eater(self):
    while not self.stop_signal:
        time.sleep(0.02)
        
        if self.data_Q.empty(): continue    
        code, isok = self.data_Q.get()
        
        # 전체 데이터에 추가
        self.code2data[code]["ALL"] += 1
        self.code2data[code]["OK"] += isok
        self.code2data[code]["NG"] += not isok
        update_gui(self, isok)

def update_gui(self, isok):
    self.init_gui_data()
    # self.listbox2.delete(idx)
    # self.listbox2.insert(idx, self.code2data[code]["ALL"])
    # self.listbox3.delete(idx)
    # self.listbox3.insert(idx, self.code2data[code]["OK"])
    # self.listbox4.delete(idx)
    # self.listbox4.insert(idx, self.code2data[code]["NG"])
    
    # OK, NG
    if isok: self.ok_label.configure(text='OK', fg='#92D050', anchor='center')
    else: self.ok_label.configure(text='NG', fg='#ff0000', anchor='center')
    
#######################################################################
def alarm(self):
    self.thr_lock.acquire()
    time.sleep(0.05)
    self.serial.write(b"\xA0\x01\x01\xA2") # ON
    time.sleep(3)
    self.serial.write(b"\xA0\x01\x00\xA1") # OFF
    self.thr_lock.release()

#######################################################################
def auto_cam(self, period=0.15, repeat_num=3, patience_num=15):
    patience_cnt = 0
    current_name = None
    before_move_img = None
    
    logger.info("auto_cam 시작")
    
    while not self.stop_signal:
        time.sleep(period)
        # 가져갈때까지 대기
        # if not self.raw_Q.empty(): continue
        if 1 < self.raw_Q.qsize(): continue
        
        # 촬영
        img = self.cam.get_image()
        if img is None: continue
        # print('.', end='')
        
        # 선택된 제품의 소비기한 polys, 움직임감지 move
        polys = self.code2polys[self.selected_code]
        move_poly = self.code2move[self.selected_code]
        
        # 
        move_img = tool.crop_obj_in_bg2(img, [move_poly])
        move_img = cv2.resize(move_img, (5,5))
        
        #################################여기부터 해야됨
        
        # # 촬영한 이미지에서 소비기한 추출
        # imgs = tool.crop_obj_in_bg2(img, polys)
        # # dark_values = list(map(lambda img:cv2.threshold(img, 130, 1, cv2.THRESH_BINARY_INV)[1], imgs))
        # dark_values = list(map(lambda img:cv2.threshold(img, 180, 1, cv2.THRESH_BINARY_INV)[1], imgs))
        # dark_values = list(map(np.sum, dark_values))
        # dark_values = list(filter(lambda x:x>300, dark_values))
        # print(len(dark_values))
        
        if len(dark_values) == 0:
            patience_cnt += 1
            if patience_cnt == patience_num: # 한번만
                logger.info("감지안됨")
                self.recode_Q.put([img, None, 'raw'])
                self.data_Q.put([self.selected_code, False])
                # Thread(target=alarm, args=(self,), daemon=True).start()
                
                # 왜 감지가 안됐는지 확인용
                time.sleep(period)
                img = self.cam.get_image()
                if img is None: continue
                imgs = tool.crop_obj_in_bg2(img, polys)
                self.draw_Q.put([self.selected_code, False, imgs])
        
        # 멈췄다 싶으면 다섯번 찍기
        elif patience_cnt >= 2:
            logger.info("감지")
            patience_cnt = 0
            current_name = None
            imgss = []
            for _ in range(repeat_num):
                time.sleep(period)
                img = self.cam.get_image()
                if img is None: continue
                imgs = tool.crop_obj_in_bg2(img, polys)
                imgss.append(imgs)
                
            if len(imgss) == 0:
                self.stop_signal = True
                logger.error("카메라 에러")
                mb.showerror(title="", message="카메라 에러")
                continue
                
            self.raw_Q.put([self.selected_code, imgss])
        
    
#######################################################################
def read(self):
    try:
        while not self.stop_signal:
            time.sleep(0.05)
            if self.raw_Q.empty(): continue
            start_time = time.time()

            # get image
            code, imgss = self.raw_Q.get()

            # OCR
            repeat_num = len(imgss)
            poly_num = len(imgss[0])
            flat_imgs = list(reduce(lambda x,y:x+y, imgss))
            flat_dates = self.ocr_engine(flat_imgs)
            
            end_time = time.time()
            logger.info(f"Detect Time : {end_time-start_time:.3f}")
            logger.info(f"flat_dates : {flat_dates}")
            self.analy_Q.put([code, repeat_num, poly_num, flat_dates, flat_imgs])
            
    except Exception as e:
        logger.error(f"[read]{e}")
        # self.write_sys_msg(e)
        self.stop_signal = True

#######################################################################
# def policy_check(text):
#     if type(text) != str: return False
#     if not text: return False
#     text = ''.join(text.split('.'))
#     text = ''.join(text.split(' '))
#     if not text.isdigit(): return False
#     if len(text) != 8: return False
#     return True

def policy_check(text):
    assert type(text) == str
    
    # 6글자 보다 적으면 NG
    if len(text) <= 6: return False

    # 22.22.22 꼴이면 OK
    if re.search("[0-9]{2}[^0-9][0-9]{2}[^0-9][0-9]{2}", text) is not None: return True

    # . 이 없으면 NG
    if not '.' in text: return False

    # .을 없앴을때 6글자 미만이면 NG
    text = ''.join(text.split('.'))
    text = ''.join(text.split(' '))
    if len(text) < 6: return False
    return True

def analysis(self):
    try:
        while not self.stop_signal:
            time.sleep(0.05)
            if self.analy_Q.empty(): continue

            # 조건 분석
            code, repeat_num, poly_num, flat_dates, flat_imgs = self.analy_Q.get()
            flat_isok = list(map(policy_check, flat_dates))
            isokss = np.array(flat_isok).reshape(repeat_num, poly_num)
            
            # OK check
            # isoks = np.any(isokss, axis=0) # len(poly_num) # 반복중 하나라도 OK면 OK
            # isok = np.all(isoks) # 여러개중 모두 OK면 OK
            isok = np.any(isokss) # 하나라도 OK면 OK
            if not isok:
                # Thread(target=alarm, args=(self,), daemon=True).start()
                pass
            
            date_imgs = flat_imgs[-poly_num:]
            
            self.data_Q.put([code, isok])
            self.draw_Q.put([code, isok, date_imgs]) # 저장때문에 code, isok 필요
        
    except Exception as e:
        logger.error(f"[analysis]{e}")
        # self.write_sys_msg(e)
        self.stop_signal = True
        
#######################################################################
def draw(self):
    try:
        while not self.stop_signal:
            time.sleep(0.05)
            if self.draw_Q.empty(): continue
            
            code, isok, date_imgs = self.draw_Q.get()
            
            # 이미지 사이즈 통일, 합치기
            h, w = date_imgs[0].shape[:2]
            date_imgs = list(map(lambda img:cv2.resize(img, (w, h)), date_imgs))
            img = cv2.vconcat(date_imgs)
            
            self.image_Q.put(img)
            self.recode_Q.put([img, code, isok])
        
    except Exception as e:
        logger.error(f"[draw]{e}")
        # self.write_sys_msg(e)
        self.stop_signal = True

#######################################################################
# def snap(self):
#     self.serial.write(LIGHT_ON)
#     time.sleep(0.2)
#     self.cam.set_exposure(2500)
#     img = self.cam.get_image()
#     self.serial.write(LIGHT_OFF)
#     self.image_Q.put(img)

#######################################################################
# def json_saver(self):
#     img, poly, name = None, None, None
    
#     while not self.stop_signal:
#         time.sleep(0.05)
        
#         # 데이터 받기
#         if not self.pair_Q.empty():
#             img, poly = self.pair_Q.get()
#         if not self.enter_Q.empty():
#             name = self.enter_Q.get()
            
#         if img is None or name is None: continue
        
#         # 데이터 받은 후
#         path = os.path.join(IMG_DIR_PATH, f"{name}.jpg")
#         tool.imwrite(path, img)
#         path = os.path.join(JSON_DIR_PATH, f"{name}.json")
#         tool.poly2json(path, ["object"], [poly])
#         # self.write_sys_msg(f"[{name}] 등록되었습니다.")
#         logger.info(f"[{name}] applied.")
#         self.poly_detector.update_check()
#         self.init_gui_data()
        
#         # 이미지 초기화
#         img, poly, name = None, None, None
        
#         self.current_origin_image = None
#         self.current_image = None
        
#         imgtk = ImageTk.PhotoImage(Image.fromarray(np.zeros((10,10,3), dtype=np.uint8)))
#         self.image_label.configure(image=imgtk)
#         self.image_label.image = imgtk
#         del imgtk
#         self.image_label.configure(image=None)
#         self.image_label.image = None
        
#######################################################################
def recode(self):
    dir_dic = {'raw':SAVE_RAW_IMG_DIR, 'debug':SAVE_DEBUG_IMG_DIR, 
               True:SAVE_OK_IMG_DIR, False:SAVE_NG_IMG_DIR, None:""}
    
    while not self.stop_signal:
        time.sleep(0.01)
        
        if self.recode_Q.empty(): continue
        img, code, isok = self.recode_Q.get()
        file_name = f"{tool.get_time_str()}.jpg"
        
        # dir 없으면 만들기
        dir_path = dir_dic[isok]
        if code:
            dir_path = os.path.join(dir_path, code)
            if not os.path.isdir(dir_path): os.mkdir(dir_path)
        
        # 이미지 저장
        path = os.path.join(dir_path, file_name)
        tool.imwrite(path, img)
        tool.manage_file_num(dir_path)
        
#######################################################################
#######################################################################
#######################################################################
#######################################################################
#######################################################################
#######################################################################












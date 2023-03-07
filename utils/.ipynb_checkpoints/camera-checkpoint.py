# import stapipy as st
import numpy as np
import cv2
import time

class SentechCam():
    def __init__(self, logger=None, ExposureTime=20000, AcquisitionMode="SingleFrame", gray_scale=False):
        self.logger = logger
        self.ExposureTime = ExposureTime
        self.AcquisitionMode = AcquisitionMode
        self.gray_scale = gray_scale
        
        st.initialize()
        st_system = st.create_system()
        self.st_device = st_system.create_first_device()
        self.set_configure()
        if self.logger is not None:
            self.logger.debug(f"Device:{self.st_device.info.display_name}")
            
        self.st_datastream = self.st_device.create_datastream()
        self.st_datastream.start_acquisition()
        
        self.img_shape = self.get_image().shape
        
    def get_image(self):
        start = time.time()
        
        self.st_device.acquisition_start()
        with self.st_datastream.retrieve_buffer() as st_buffer:
            if not st_buffer.info.is_image_present:
                if self.logger is not None:
                    self.logger.error("st_buffer.info.is_image_present : False !!")
                self.st_device.acquisition_stop()
                return None
            st_image = st_buffer.get_image()
            st_image = st_buffer.get_image()
            pixel_format = st_image.pixel_format
            pixel_format_info = st.get_pixel_format_info(pixel_format)

            data = st_image.get_image_data()

            if pixel_format_info.each_component_total_bit_count > 8:
                nparr = np.frombuffer(data, np.uint16)
                division = pow(2, pixel_format_info
                               .each_component_valid_bit_count - 8)
                nparr = (nparr / division).astype('uint8')
            else:
                nparr = np.frombuffer(data, np.uint8)

            # Process image for display.
            nparr = nparr.reshape(st_image.height, st_image.width, 1)

            # Perform color conversion for Bayer.
            if pixel_format_info.is_bayer:
                if self.gray_scale:
                    bayer_type = pixel_format_info.get_pixel_color_filter()
                    if bayer_type == st.EStPixelColorFilter.BayerRG:
                        nparr = cv2.cvtColor(nparr, cv2.COLOR_BAYER_RG2GRAY)
                    elif bayer_type == st.EStPixelColorFilter.BayerGR:
                        nparr = cv2.cvtColor(nparr, cv2.COLOR_BAYER_GR2GRAY)
                    elif bayer_type == st.EStPixelColorFilter.BayerGB:
                        nparr = cv2.cvtColor(nparr, cv2.COLOR_BAYER_GB2GRAY)
                    elif bayer_type == st.EStPixelColorFilter.BayerBG:
                        nparr = cv2.cvtColor(nparr, cv2.COLOR_BAYER_BG2GRAY)
                else:
                    bayer_type = pixel_format_info.get_pixel_color_filter()
                    if bayer_type == st.EStPixelColorFilter.BayerRG:
                        nparr = cv2.cvtColor(nparr, cv2.COLOR_BAYER_RG2RGB)
                    elif bayer_type == st.EStPixelColorFilter.BayerGR:
                        nparr = cv2.cvtColor(nparr, cv2.COLOR_BAYER_GR2RGB)
                    elif bayer_type == st.EStPixelColorFilter.BayerGB:
                        nparr = cv2.cvtColor(nparr, cv2.COLOR_BAYER_GB2RGB)
                    elif bayer_type == st.EStPixelColorFilter.BayerBG:
                        nparr = cv2.cvtColor(nparr, cv2.COLOR_BAYER_BG2RGB)
        
        self.st_device.acquisition_stop()
        end = time.time()
        
        if self.logger is not None:
            self.logger.debug(f"Shot Time : {end-start:.4f}")
            
        return nparr # RGB 라는데 BGR 임
    
    def set_configure(self):
        nodemap = self.st_device.remote_port.nodemap
        node = nodemap.get_node("ExposureTime")
        st.PyIFloat(node).set_value(self.ExposureTime)
        node = nodemap.get_node("AcquisitionMode")
        st.PyIEnumeration(node).set_symbolic_value(self.AcquisitionMode)
        
        if self.logger is not None:
            self.logger.debug(f"ExposureTime:{self.ExposureTime}, AcquisitionMode:{self.AcquisitionMode}")
            
    def set_exposure(self, value):
        assert type(value) == int and 500 <= value <= 50000
        nodemap = self.st_device.remote_port.nodemap
        node = nodemap.get_node("ExposureTime")
        st.PyIFloat(node).set_value(value)

        
        
        
        
from pypylon import pylon
import cv2

class BaslerCam():
    def __init__(self, ExposureTime=25000, logger=None, gray_scale=False):
        # conecting to the first available camera
        self.camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())

        # Grabing Continusely (video) with minimal delay
        self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly) 
        self.converter = pylon.ImageFormatConverter()

        # converting to opencv bgr format
        if gray_scale:
            self.converter.OutputPixelFormat = pylon.PixelType_Mono8
        else:
            self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed
        self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

        # settimg ExposureTime
        self.camera.ExposureTime.SetValue(ExposureTime)
        
        if logger is not None:
            logger.info(f"Camera Name : {self.camera.GetDeviceInfo().GetModelName()}")
            logger.info(f"Exposure Time : {self.camera.ExposureTime.GetValue()}")
            logger.info(f"DeviceLinkThroughputLimit : {self.camera.DeviceLinkThroughputLimit.GetValue()}")

    def get_image(self):
        image = None
        if self.camera.IsGrabbing():
            grabResult = self.camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
            if grabResult.GrabSucceeded():
                # Access the image data
                image = self.converter.Convert(grabResult)
                image = image.GetArray()
            grabResult.Release()
        return image

    def set_exposure(self, value):
        assert type(value) == int and 100 <= value <= 50000
        self.camera.ExposureTime.SetValue(value)

    def close(self):
        self.camera.StopGrabbing()
        
        
        
        
        
        
        
        
        
if __name__ == "__main__":
    import os
    cam = SentechCam(ExposureTime=25000, gray_scale=True)
    n = len(os.listdir("./images"))
    for i in range(n, 5000):
        img = cam.get_image()
        cv2.imwrite(f"./images/{i:04d}.png", img)
        cv2.imshow('test', img)
        if cv2.waitKey(1000*300) == ord('q'): break
    cv2.destroyAllWindows()

import cv2
import numpy as np

def crop_forward():
    img = cv2.imread('temp.png')
    if img is None:
        print("錯誤：工作目錄下找不到 temp.png 檔案。")
        return
    
    # 1. 將 1440p 高畫質圖片縮小至與日端範本原圖相同的 1024x576 解析度，以確保比對尺度一致
    img_resized = cv2.resize(img, (1024, 576), interpolation=cv2.INTER_LANCZOS4)
    h, w, c = img_resized.shape
    print(f"縮小後的影像尺寸: {w}x{h}")
    
    # 2. 擷取中央區域感興趣區 (ROI)
    crop_ymin, crop_ymax = int(h * 0.25), int(h * 0.5)
    crop_xmin, crop_xmax = int(w * 0.3), int(w * 0.7)
    
    center_roi = img_resized[crop_ymin:crop_ymax, crop_xmin:crop_xmax]
    
    # 3. 轉換到 HSV 空間，擷取符合金色的文字像素
    hsv = cv2.cvtColor(center_roi, cv2.COLOR_BGR2HSV)
    lower_gold = np.array([15, 80, 150])
    upper_gold = np.array([28, 255, 255])
    
    mask = cv2.inRange(hsv, lower_gold, upper_gold)
    
    # 4. 尋找金色區塊輪廓以精確擷取 FORWARD! 文字的 bounding box
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        # 合併所有符合金色的輪廓點
        all_pts = np.concatenate(contours)
        x, y, bbox_w, bbox_h = cv2.boundingRect(all_pts)
        
        # 額外擴充 5 像素的外邊距
        padding = 5
        bx = max(0, x - padding)
        by = max(0, y - padding)
        bw = min(center_roi.shape[1] - bx, bbox_w + 2 * padding)
        bh = min(center_roi.shape[0] - by, bbox_h + 2 * padding)
        
        forward_template = center_roi[by:by+bh, bx:bx+bw]
        cv2.imwrite("forward_template.png", forward_template)
        print(f"成功裁剪並覆蓋 forward_template.png，尺寸為: {bw}x{bh}")
    else:
        print("未偵測到符合金色範圍的輪廓，改用預設中央裁剪。")
        cv2.imwrite("forward_template.png", center_roi)

if __name__ == "__main__":
    crop_forward()

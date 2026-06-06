import cv2
import numpy as np

def main():
    # 讀取使用者上傳的截圖
    img_path = r"C:\Users\BlackCat\.gemini\antigravity\brain\2cf43390-3499-442a-a774-d58ebe4a6060\media__1780725110635.png"
    img = cv2.imread(img_path)
    if img is None:
        print("錯誤：找不到影像檔案。")
        return

    h, w, c = img.shape
    print(f"原圖尺寸: {w}x{h}")

    # 擷取中央區域 (RESTART 通常在中央偏上)
    # y: 150 到 300, x: 300 到 724
    crop_ymin, crop_ymax = int(h * 0.25), int(h * 0.5)
    crop_xmin, crop_xmax = int(w * 0.3), int(w * 0.7)
    
    center_roi = img[crop_ymin:crop_ymax, crop_xmin:crop_xmax]
    cv2.imwrite("roi_center.png", center_roi)
    print("已儲存 ROI 區域至 roi_center.png")

    # 轉換到 HSV 空間，用以提取金色/黃色文字
    hsv = cv2.cvtColor(center_roi, cv2.COLOR_BGR2HSV)
    
    # 金色/黃色的 HSV 範圍 (大約值)
    lower_gold = np.array([15, 80, 150])
    upper_gold = np.array([28, 255, 255])
    
    mask = cv2.inRange(hsv, lower_gold, upper_gold)
    
    # 尋找輪廓以定位 RESTART 字樣的 bounding box
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        # 合併所有符合黃金色的輪廓
        all_pts = np.concatenate(contours)
        x, y, bbox_w, bbox_h = cv2.boundingRect(all_pts)
        
        # 往外擴展一點邊距
        padding = 5
        bx = max(0, x - padding)
        by = max(0, y - padding)
        bw = min(center_roi.shape[1] - bx, bbox_w + 2 * padding)
        bh = min(center_roi.shape[0] - by, bbox_h + 2 * padding)
        
        # 裁剪出模板
        restart_template = center_roi[by:by+bh, bx:bx+bw]
        cv2.imwrite("restart_template.png", restart_template)
        print(f"成功定位並裁剪 RESTART 模板！尺寸: {bw}x{bh}，已儲存至 restart_template.png")
    else:
        print("未偵測到符合金色範圍的輪廓，改用預設中央裁剪。")
        # 預設直接保存中央感興趣區域
        cv2.imwrite("restart_template.png", center_roi)

if __name__ == "__main__":
    main()

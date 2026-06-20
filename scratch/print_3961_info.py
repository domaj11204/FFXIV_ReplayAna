import cv2
import numpy as np
import os

def check_file(filename):
    path = os.path.join("debug_wipes", filename)
    if not os.path.exists(path):
        print(f"檔案不存在: {path}")
        return
    img = cv2.imread(path)
    if img is None:
        print(f"無法讀取圖片: {path}")
        return
    # 灰階轉換
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # pix_th = 0.15, 亮度低於 38.25
    black_pixels = np.sum(gray < 38.25)
    total_pixels = gray.shape[0] * gray.shape[1]
    ratio = black_pixels / total_pixels
    print(f"檔案: {filename} | 解析度: {img.shape[1]}x{img.shape[0]} | 黑像素比例: {ratio*100:.2f}% | 判定: {'黑屏' if ratio >= 0.98 else '非黑屏'}")

def main():
    print("=== 1:06:00 ~ 1:06:03 裁切區域黑像素比例診斷 ===")
    files = sorted(os.listdir("debug_wipes"))
    for f in files:
        if f.startswith("diag_crop_") and ("3960." in f or "3961." in f or "3962." in f or "3963." in f):
            check_file(f)

if __name__ == "__main__":
    main()

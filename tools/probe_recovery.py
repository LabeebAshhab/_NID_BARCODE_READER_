"""Developer-only recovery search; prints diagnostics, never decoded identity data."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cv2
import numpy as np
import zxingcpp
from nid_scanner.pipeline import load_image


def rotate(gray, angle):
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w/2, h/2), angle, 1)
    c, s = abs(m[0, 0]), abs(m[0, 1])
    nw, nh = int(w*c+h*s), int(h*c+w*s)
    m[:, 2] += ((nw-w)/2, (nh-h)/2)
    return cv2.warpAffine(gray, m, (nw, nh), borderValue=255)


def angle_of(gray):
    smooth = cv2.GaussianBlur(gray, (5, 5), 1)
    edges = cv2.Canny(smooth, 20, 70)
    lines = cv2.HoughLinesP(edges, 1, np.pi/720, 70, minLineLength=gray.shape[1]//6, maxLineGap=25)
    angles = []
    if lines is not None:
        for x1, y1, x2, y2 in lines[:, 0]:
            angle = np.degrees(np.arctan2(y2-y1, x2-x1))
            angle = (angle+45)%90-45
            angles.append(angle)
    return float(np.median(angles)) if angles else 0


def probe(path):
    gray = cv2.cvtColor(load_image(path), cv2.COLOR_BGR2GRAY)
    angle = angle_of(gray)
    print(path.name, 'angle', round(angle,2), flush=True)
    n = 0
    for delta in (0, -1, 1):
        base = rotate(gray, angle+delta)
        for scale in (1, .5, .75, 1.5, 2):
            im = cv2.resize(base, None, fx=scale, fy=scale)
            # Generic tiles include lower card barcode without consulting the original.
            for region in (im, im[im.shape[0]//2:,:]):
                smooth = cv2.GaussianBlur(region, (0,0), 1)
                light = cv2.GaussianBlur(smooth, (0,0), 21)
                norm = cv2.divide(smooth, np.maximum(light, 1), scale=180)
                candidates = [('raw',region),('smooth',smooth),('norm',norm)]
                for sigma in (.7,1.2,2,3):
                    low = cv2.GaussianBlur(norm,(0,0),sigma)
                    for amount in (1,2,4):
                        candidates.append((f'sharp-{sigma}-{amount}',cv2.addWeighted(norm,1+amount,low,-amount,0)))
                for name, candidate in candidates:
                    for binarizer in (zxingcpp.Binarizer.LocalAverage,zxingcpp.Binarizer.GlobalHistogram):
                        n+=1
                        results=zxingcpp.read_barcodes(candidate,formats=[zxingcpp.BarcodeFormat.PDF417],binarizer=binarizer)
                        if any(r.valid for r in results):
                            print('SUCCESS',path.name, delta,scale,name,str(binarizer),'attempt',n,flush=True)
                            return
                    for block in (15,31,51):
                        for c in (0,3,7):
                            n+=1
                            th=cv2.adaptiveThreshold(candidate,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,block,c)
                            if zxingcpp.read_barcodes(th,formats=[zxingcpp.BarcodeFormat.PDF417],binarizer=zxingcpp.Binarizer.FixedThreshold):
                                print('SUCCESS',path.name,delta,scale,name,block,c,'attempt',n,flush=True)
                                return
        print('angle pass done',delta,n,flush=True)
    print('NO READ',path.name,n,flush=True)

if __name__=='__main__':
    for pattern in ('*medium*.jpg','*hard*.jpg'):
        for path in Path('low_img').rglob(pattern):
            probe(path)

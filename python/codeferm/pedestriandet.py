"""
Copyright (c) Steven P. Goldsmith. All rights reserved.

Created by Steven P. Goldsmith on February 8, 2017
sgoldsmith@codeferm.com
"""

"""Pedestrian detector using ROI.

@author: sgoldsmith

"""

import cv2

# Initialize HOG
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

def detect(locations, image, resizeImg, mark):
    """Check ROIs for pedestrians"""
    global hog
    for x, y, w, h in locations:
        # Make sure ROI is big enough for detector
        if w > 63 and h > 127:
            imageRoi = resizeImg[y:y + h, x:x + w]
            foundLocations, foundWeights = hog.detectMultiScale(imageRoi, winStride=(8, 8), padding=(8, 8), scale=1.1)
    return foundLocations
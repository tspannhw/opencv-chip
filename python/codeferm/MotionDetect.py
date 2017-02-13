"""
Copyright (c) Steven P. Goldsmith. All rights reserved.

Created by Steven P. Goldsmith on February 4, 2017
sgoldsmith@codeferm.com
"""

"""Motion detector.

Resizes frame, sampling and uses moving average to determine change percent. Inner
rectangles are filtered out as well. This can result in better performance and
a more stable ROI.

Optional pedestrian detector using sampling, resize and motion ROI. Histogram of Oriented
Gradients ([Dalal2005]) object detector is used. You can get up to 1200%
performance boost using this method.

A frame buffer is used to record 1 second before motion threshold is triggered.

sys.argv[1] = configuration file name or will default to "motiondetect.ini" if no args passed.

@author: sgoldsmith

"""

import ConfigParser, logging, sys, os, time, datetime, numpy, cv2, urlparse, mjpegclient, motiondet, pedestriandet

if __name__ == '__main__':
    if len(sys.argv) < 2:
        configFileName = "motiondetect.ini"
    else:
        configFileName = sys.argv[1]
    parser = ConfigParser.SafeConfigParser()
    # Read configuration file
    parser.read(configFileName)
    # Configure logger
    logger = logging.getLogger("MotionDetect")
    logger.setLevel(parser.get("logging", "level"))
    formatter = logging.Formatter(parser.get("logging", "formatter"))
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    # Set camera related data attributes
    cameraName = parser.get("camera", "name")    
    url = parser.get("camera", "url")
    frames = parser.getint("camera", "frames")
    fps = parser.getint("camera", "fps")
    fourcc = parser.get("camera", "fourcc")
    recordFileExt = parser.get("camera", "recordFileExt")
    recordDir = parser.get("camera", "recordDir")
    detectType = parser.get("camera", "detectType")
    mark = parser.getboolean("camera", "mark")
    # See if we should use MJPEG client
    if urlparse.urlparse(url).scheme == "http":
        mjpeg = True
    else:
        mjpeg = False
    # Init video capture
    if mjpeg:
        # Open MJPEG stream
        socketFile, streamSock, boundary = mjpegclient.open(url, 10)
        # Determine image dimensions
        image = mjpegclient.getFrame(socketFile, boundary)
        frameHeight, frameWidth, unknown = image.shape
        framesLeft = frames
    else:
        videoCapture = cv2.VideoCapture(url)
        frameHeight = int(videoCapture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frameWidth = int(videoCapture.get(cv2.CAP_PROP_FRAME_WIDTH))
        fps = int(videoCapture.get(cv2.CAP_PROP_FPS))
        # We do not know frame count using VideoCapture to read file
        framesLeft = 10000000
    logger.info("OpenCV %s" % cv2.__version__)
    logger.info("URL: %s, frames to capture: %d" % (url, frames))
    logger.info("Resolution: %dx%d" % (frameWidth, frameHeight))
    # Make sure we have positive values
    if frameWidth > 0 and frameHeight > 0:
        # Motion detection generally works best with 320 or wider images
        widthDivisor = int(frameWidth / 320)
        if widthDivisor < 1:
            widthDivisor = 1
        frameResizeWidth = int(frameWidth / widthDivisor)
        frameResizeHeight = int(frameHeight / widthDivisor)
        logger.info("Resized to: %dx%d" % (frameResizeWidth, frameResizeHeight))
        # Used for full size image marking
        widthMultiplier = int(frameWidth / frameResizeWidth)
        heightMultiplier = int(frameHeight / frameResizeHeight)
        # Analyze only ~3 FPS which works well with this type of detection
        frameToCheck = int(fps / 4)
        # 0 means check every frame
        if frameToCheck < 1:
            frameToCheck = 0
        skipCount = 0         
        # Frame buffer, so we can record just before motion starts
        frameBuf = []
        # Buffer one second of video
        frameBufSize = fps
        recording = False
        frameOk = True
        frameCount = 0
        start = time.time()
        # Calculate FPS
        while(framesLeft > 0 and frameOk):
            now = datetime.datetime.now()  # Used for timestamp in frame buffer and filename
            if mjpeg:
                image = mjpegclient.getFrame(socketFile, boundary)
            else:
                ret, image = videoCapture.read()
                frameOk = ret
            if frameOk:
                frameCount += 1
                # Buffer image
                if len(frameBuf) == frameBufSize:
                    # Toss first image in list (oldest)
                    frameBuf.pop(0)
                # Add new image to end of list
                frameBuf.append((image, int(time.mktime(now.timetuple()) * 1000000 + now.microsecond)))            
                # Skip frames until skip count <= 0
                if skipCount <= 0:
                    skipCount = frameToCheck
                    # Resize image if not the same size as the original
                    if frameResizeWidth != frameWidth:
                        resizeImg = cv2.resize(image, (frameResizeWidth, frameResizeHeight), interpolation=cv2.INTER_NEAREST)
                    else:
                        resizeImg = image
                    # Detect motion
                    motionPercent, movementLocations = motiondet.detect(resizeImg)
                    # Threshold to trigger motion
                    if motionPercent > 2.0:
                        if not recording:
                            # Construct directory name from recordDir and date
                            fileDir = "%s%s%s%s%s%s" % (recordDir, os.sep, "motion", os.sep, now.strftime("%Y-%m-%d"), os.sep)
                            # Create dir if it doesn"t exist
                            if not os.path.exists(fileDir):
                                os.makedirs(fileDir)
                            fileName = "%s.%s" % (now.strftime("%H-%M-%S"), "avi")
                            videoWriter = cv2.VideoWriter("%s/%s" % (fileDir, fileName), cv2.VideoWriter_fourcc(fourcc[0], fourcc[1], fourcc[2], fourcc[3]), fps, (frameWidth, frameHeight), True)
                            logger.info("Start recording (%4.2f) %s%s @ %3.1f FPS" % (motionPercent, fileDir, fileName, fps))
                            peopleFound = False
                            recording = True
                        if mark:
                            for x, y, w, h in movementLocations:
                                cv2.putText(image, "%dw x %dh" % (w, h), (x * widthMultiplier, (y * heightMultiplier) - 4), cv2.FONT_HERSHEY_PLAIN, 1.5, (255, 255, 255), thickness=2, lineType=cv2.LINE_AA)
                                # Draw rectangle around found objects
                                cv2.rectangle(image, (x * widthMultiplier, y * heightMultiplier),
                                              ((x + w) * widthMultiplier, (y + h) * heightMultiplier),
                                              (0, 255, 0), 2)
                        # Detect pedestrians ?
                        if detectType.lower() == "p":
                            foundLocationsList, foundWeightsList = pedestriandet.detect(movementLocations, resizeImg)
                            if len(foundLocationsList) > 0:
                                peopleFound = True
                                if mark:
                                    for foundLocations, foundWeights in zip(foundLocationsList,foundWeightsList):
                                        i = 0
                                        for x2, y2, w2, h2 in foundLocations:
                                            imageRoi2 = image[y * heightMultiplier:y * heightMultiplier + (h * heightMultiplier), x * widthMultiplier:x * widthMultiplier + (w * widthMultiplier)]
                                            # Draw rectangle around people
                                            cv2.rectangle(imageRoi2, (x2, y2), (x2 + (w2 * widthMultiplier), y2 + (h2 * heightMultiplier) - 1), (255, 0, 0), 2)
                                            # Print weight
                                            cv2.putText(imageRoi2, "%1.2f" % foundWeights[i], (x2, y2 - 4), cv2.FONT_HERSHEY_PLAIN, 1.5, (255, 255, 255), thickness=2, lineType=cv2.LINE_AA)
                                            i += 1
                                logger.debug("People detected locations: %s" % (foundLocationsList))
                else:
                    skipCount -= 1
            # If recording write frame and check motion percent
            if recording:
                # Write first image in buffer (the oldest)
                if frameOk:
                    videoWriter.write(frameBuf[0][0])
                # Threshold to stop recording
                if motionPercent <= 0.25 or not frameOk:
                    logger.info("Stop recording")
                    del videoWriter
                    # Rename video to show people found
                    if peopleFound:
                        os.rename("%s/%s" % (fileDir, fileName),"%s/people-%s" % (fileDir, fileName))
                    recording = False
            framesLeft -= 1
        elapsed = time.time() - start
        # Use actual frame count if VideoCapture
        if not mjpeg:
            frames = frameCount
        fpsElapsed = frames / elapsed
        logger.info("Calculated %4.1f FPS, frames: %d, elapsed time: %4.2f seconds" % (fpsElapsed, frameCount, elapsed))
        # Clean up
        if mjpeg:
            socketFile.close()
            streamSock.close()
        else:
            del videoCapture

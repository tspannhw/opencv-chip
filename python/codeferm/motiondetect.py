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

import ConfigParser, logging, sys, os, time, datetime, numpy, cv2, urlparse, mjpegclient, motiondet, pedestriandet, cascadedet

def markMotion(target, rects, widthMul, heightMul, boxColor, boxThickness):
    """Mark motion objects in image"""
    for x, y, w, h in rects:
        # Mark target
        cv2.rectangle(target, (x * widthMul, y * heightMul), ((x + w) * widthMul, (y + h) * heightMul), boxColor, boxThickness)
        if x <= 2:
            x = 4
        if y <= 0:
            y = 9
        # Show width and height of full size image
        cv2.putText(target, "%dx%d" % (w * widthMul, h * heightMul), (x * widthMul, (y * heightMul) - 4), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 255), thickness=1, lineType=cv2.LINE_AA)

def markPedestrian(target, locList, foundLocsList, foundWghtsList, widthMul, heightMul, boxColor, boxThickness):
    """Mark pedestrian objects in image"""
    for location, foundLocations, foundWeights in zip(locList, foundLocsList, foundWghtsList):
        i = 0
        # Mark target
        for x, y, w, h in foundLocations:
            x2, y2, w2, h2 = location
            cv2.rectangle(target, ((x + x2) * widthMultiplier, (y + y2) * heightMultiplier),
            ((x + x2 + w) * widthMultiplier, (y + y2 + h) * heightMultiplier), boxColor, boxThickness)
            if x2 <= 2:
                x2 = 4
            if y2 <= 0:
                y2 = 9
            # Print weight
            cv2.putText(image, "%1.2f" % foundWeights[i], ((x + x2) * widthMultiplier, (y + y2 + h) * heightMultiplier - 4), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 255), thickness=1, lineType=cv2.LINE_AA)
            i += 1

def markRoi(target, locList, foundLocsList, widthMul, heightMul, boxColor, boxThickness):
    """Mark ROI objects in image"""
    for location, foundLocations in zip(locList, foundLocsList):
        # Mark target
        for x, y, w, h in foundLocations:
            x2, y2, w2, h2 = location
            cv2.rectangle(target, ((x + x2) * widthMultiplier, (y + y2) * heightMultiplier),
            ((x + x2 + w) * widthMultiplier, (y + y2 + h) * heightMultiplier), boxColor, boxThickness)
        if x2 <= 2:
            x2 = 4
        if y2 <= 0:
            y2 = 9
        # Show width and height of full size image
        cv2.putText(image, "%dx%d" % (w * widthMul, h * heightMul), ((x + x2) * widthMultiplier, (y + y2 + h) * heightMultiplier - 4), cv2.FONT_HERSHEY_PLAIN, 1.0, (255, 255, 255), thickness=1, lineType=cv2.LINE_AA)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        configFileName = "../config/motiondetect.ini"
    else:
        configFileName = sys.argv[1]
    parser = ConfigParser.SafeConfigParser()
    # Read configuration file
    parser.read(configFileName)
    # Configure logger
    logger = logging.getLogger("motiondetect")
    logger.setLevel(parser.get("logging", "level"))
    formatter = logging.Formatter(parser.get("logging", "formatter"))
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    # Set camera related data attributes
    cameraName = parser.get("camera", "name")    
    url = parser.get("camera", "url")
    resizeWidthDiv = parser.getint("camera", "resizeWidthDiv")
    fpsInterval = parser.getfloat("camera", "fpsInterval")
    fps = parser.getint("camera", "fps")
    fourcc = parser.get("camera", "fourcc")
    recordFileExt = parser.get("camera", "recordFileExt")
    recordDir = parser.get("camera", "recordDir")
    detectType = parser.get("camera", "detectType")
    mark = parser.getboolean("camera", "mark")
    # Set motion related data attributes
    kSize = eval(parser.get("motion", "kSize"), {}, {})
    alpha = parser.getfloat("motion", "alpha")
    blackThreshold = parser.getint("motion", "blackThreshold")
    maxChange = parser.getfloat("motion", "maxChange")
    skipFrames = parser.getint("motion", "skipFrames")
    startThreshold = parser.getfloat("motion", "startThreshold")
    stopThreshold = parser.getfloat("motion", "stopThreshold")
    # Set contour related data attributes
    dilateAmount = parser.getint("motion", "dilateAmount")
    erodeAmount = parser.getint("motion", "erodeAmount")
    # Set pedestrian detect related data attributes
    hitThreshold = parser.getfloat("pedestrian", "hitThreshold")
    winStride = eval(parser.get("pedestrian", "winStride"), {}, {})
    padding = eval(parser.get("pedestrian", "padding"), {}, {})
    scale0 = parser.getfloat("pedestrian", "scale0")
    finalThreshold = parser.getfloat("pedestrian", "finalThreshold")
    useMeanshiftGrouping = parser.getboolean("pedestrian", "useMeanshiftGrouping")          
    # Set cascade related data attributes
    cascadeFile = parser.get("cascade", "cascadeFile")
    scaleFactor = parser.getfloat("cascade", "scaleFactor")
    minNeighbors = parser.getint("cascade", "minNeighbors")
    minWidth = parser.getint("cascade", "minWidth")
    minHeight = parser.getint("cascade", "minHeight")
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
    else:
        videoCapture = cv2.VideoCapture(url)
        frameHeight = int(videoCapture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frameWidth = int(videoCapture.get(cv2.CAP_PROP_FRAME_WIDTH))
        fps = int(videoCapture.get(cv2.CAP_PROP_FPS))
    logger.info("OpenCV %s" % cv2.__version__)
    logger.info("URL: %s, fps: %d" % (url, fps))
    logger.info("Resolution: %dx%d" % (frameWidth, frameHeight))
    # Make sure we have positive values
    if frameWidth > 0 and frameHeight > 0:
        # Motion detection generally works best with 320 or wider images
        widthDivisor = int(frameWidth / resizeWidthDiv)
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
        frames = 0
        # Init cascade classifier
        if detectType.lower() == "h":
            cascadedet.init(cascadeFile)
        start = time.time()
        appstart = start
        # Calculate FPS
        while(frameOk):
            # Used for timestamp in frame buffer and filename
            now = datetime.datetime.now()
            if mjpeg:
                image = mjpegclient.getFrame(socketFile, boundary)
            else:
                frameOk, image = videoCapture.read()
            if frameOk:
                # Calc FPS    
                frames += 1
                curTime = time.time()
                elapse = curTime - start
                # Log FPS
                if elapse >= fpsInterval:
                    start = curTime
                    fps = frames / elapse
                    logger.debug("%3.1f FPS" % fps)
                    frames = 0                
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
                    grayImg, motionPercent, movementLocations = motiondet.detect(resizeImg, kSize, alpha, blackThreshold, maxChange, dilateAmount, erodeAmount)
                    # Threshold to trigger motion
                    if motionPercent > startThreshold:
                        if not recording:
                            # Construct directory name from camera name, recordDir and date
                            fileDir = "%s/%s/%s" % (os.path.expanduser(recordDir), cameraName, now.strftime("%Y-%m-%d"))
                            # Create dir if it doesn"t exist
                            if not os.path.exists(fileDir):
                                os.makedirs(fileDir)
                            fileName = "%s.%s" % (now.strftime("%H-%M-%S"), recordFileExt)
                            videoWriter = cv2.VideoWriter("%s/%s" % (fileDir, fileName), cv2.VideoWriter_fourcc(fourcc[0], fourcc[1], fourcc[2], fourcc[3]), fps, (frameWidth, frameHeight), True)
                            logger.info("Start recording (%4.2f) %s/%s @ %3.1f FPS" % (motionPercent, fileDir, fileName, fps))
                            peopleFound = False
                            cascadeFound = False
                            recording = True
                        if mark:
                            # Draw rectangle around found objects
                            markMotion(image, movementLocations, widthMultiplier, heightMultiplier, (0, 255, 0), 2)
                        # Detect pedestrians ?
                        if detectType.lower() == "p":
                            locationsList, foundLocationsList, foundWeightsList = pedestriandet.detect(movementLocations, resizeImg, winStride, padding, scale0)
                            if len(foundLocationsList) > 0:
                                peopleFound = True
                                if mark:
                                    # Draw rectangle around found objects
                                    markPedestrian(image, locationsList, foundLocationsList, foundWeightsList, widthMultiplier, heightMultiplier, (255, 0, 0), 2)
                                logger.debug("Pedestrian detected locations: %s" % (foundLocationsList))
                        # Haar Cascades detection?
                        elif detectType.lower() == "h":
                            locationsList, foundLocationsList = cascadedet.detect(movementLocations, grayImg, scaleFactor, minNeighbors, minWidth, minHeight)
                            if len(foundLocationsList) > 0:
                                cascadeFound = True
                                if mark:
                                    # Draw rectangle around found objects
                                    markRoi(image, locationsList, foundLocationsList, widthMultiplier, heightMultiplier, (255, 0, 0), 2)
                                logger.debug("Cascade detected locations: %s" % (foundLocationsList))
                else:
                    skipCount -= 1
            # If recording write frame and check motion percent
            if recording:
                # Write first image in buffer (the oldest)
                if frameOk:
                    videoWriter.write(frameBuf[0][0])
                # Threshold to stop recording
                if motionPercent <= stopThreshold or not frameOk:
                    logger.info("Stop recording")
                    del videoWriter
                    # Rename video to show pedestrian found
                    if peopleFound:
                        os.rename("%s/%s" % (fileDir, fileName), "%s/pedestrian-%s" % (fileDir, fileName))
                    # Rename video to show cascade found
                    elif cascadeFound:
                        os.rename("%s/%s" % (fileDir, fileName), "%s/cascade-%s" % (fileDir, fileName))
                    recording = False
        elapsed = time.time() - appstart
        logger.info("Calculated %4.1f FPS, elapsed time: %4.2f seconds" % (frames / elapsed, elapsed))        
        # Clean up
        if mjpeg:
            socketFile.close()
            streamSock.close()
        else:
            del videoCapture

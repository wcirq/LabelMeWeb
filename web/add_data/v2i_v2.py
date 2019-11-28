import os
import sys
import cv2

save_path = "../data/image3"
mp4_path = "../data/video"
mp4_path2 = "../data/video2"


other = os.listdir(mp4_path)

mp4_list = os.listdir(mp4_path2)
exist = len(other)
for index, fileName in enumerate(mp4_list):
    index += exist
    if fileName in other:
        exist -= 1
        continue
    mp4File = os.path.join(mp4_path2, fileName)
    cap = cv2.VideoCapture(mp4File)
    i = 0
    successful = True
    frames_num = cap.get(7)
    while successful:
        if i % 100 == 0: print("\r{} [{}/{}]".format(fileName, i, frames_num), end="")
        sys.stdout.flush()
        successful, frame = cap.read()
        if successful:
            # name = "{}_{}.jpg".format(fileName.split(".")[0], str(i).zfill(5))
            name = "{}_{}.jpg".format(str(index).zfill(4), str(i).zfill(5))
            path_name = os.path.join(save_path, name)
            cv2.imwrite(path_name, frame)
            i += 1
        cv2.waitKey(1)
    print("{} 分帧完成".format(fileName))

import glob
import json
import os

from add_data.dao import session, myImage as MyImage, VisualShanghai


def main():
    image_path = session.query(VisualShanghai.image_path).all()
    image_path = [os.path.basename(id[0]) for id in image_path]
    imageDir = "../data/image2"
    imageList = glob.glob(os.path.join(imageDir, '*.jpg'))  # 文件搜索
    lable = '{"version": "0.1.1", "flags": {}, "lineColor": [0, 255, 0, 128], "fillColor": [255, 0, 0, 128], "imagePath": "043_00976.jpg", "imageData": null, "imageFuzzy": 0, "imageWidth": 3840, "imageHeight": 2160, "shapes": []}'
    lable = dict()
    lable["version"] = "0.1.1"
    lable["flags"] = {}
    lable["lineColor"] = [0, 255, 0, 128]
    lable["fillColor"] = [255, 0, 0, 128]
    lable["imagePath"] = ""
    lable["imageData"] = None
    lable["imageFuzzy"] = 0
    lable["imageWidth"] = 3840
    lable["imageHeight"] = 2160
    lable["shapes"] = []
    for index, file_path in enumerate(imageList):
        # if index<50000:
        #     continue
        if index % 500: print("[{}/{}]".format(index, len(imageList)))
        file_name = os.path.basename(file_path)
        if not file_name in image_path:
            lable["imagePath"] = file_name
            obj = VisualShanghai(image_path=file_name, image_fuzzy=0, image_label=json.dumps(lable))
            session.add(obj)
            if index % 200 == 0:
                session.commit()
    session.commit()
    session.close()


if __name__ == "__main__":
    main()

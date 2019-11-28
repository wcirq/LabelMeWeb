import glob
import json
import os

from add_data.dao import session, myImage as MyImage, VisualShanghai

if __name__ == '__main__':
    VisualShanghai = session.query(VisualShanghai.image_label).all()
    count = 0
    print(len(VisualShanghai))
    for visual in VisualShanghai:
        data = json.loads(visual[0])
        if len(data["shapes"]) > 0:
            count += 1
    print(count)

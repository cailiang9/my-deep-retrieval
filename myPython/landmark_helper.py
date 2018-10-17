# -*- coding: utf-8 -*-

# Python class with common operations on the landmark dataset

# import download_helper  # used in Python 3, annotated first
import argparse
import os
from urllib.request import urlretrieve


class LandMarkDataset:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.csv_dir = os.path.join(self.root_dir, 'csv')
        self.csv_file = os.path.join(self.csv_dir, 'train.csv')
        self.training_dir = os.path.join(self.root_dir, 'training')
        self.cls_dir = os.path.join(self.training_dir, 'cls')
        self.url_dict = {}
        if not os.path.exists(self.training_dir):
            os.makedirs(self.training_dir)
            os.makedirs(self.cls_dir)

    # get the image url of each landmark which has image between l and h
    def read_url_from_file(self, l, h):
        url_temp = {}
        f = open(self.csv_file, 'r')
        lines = f.readlines()
        lines = lines[1:]  # give up the first line
        for line in lines:
            line_apart = line.strip().split(',')
            if len(line_apart) != 3 or line_apart[2] == 'None':
                continue
            landmark_id = int(line_apart[2])
            if landmark_id not in url_temp.keys():
                url_temp[landmark_id] = [line_apart[1].strip('"')]
            else:
                url_temp[landmark_id].append(line_apart[1].strip('"'))
        # print(self.url_dict)
        img_cnt = 0
        keys = url_temp.keys()
        for k in keys:
            if 100 <= len(url_temp[k]) <= 150:
                self.url_dict[k] = url_temp[k]
                img_cnt += len(self.url_dict[k])
        print('Total number of landmarks selected: %d' % len(self.url_dict.keys()))
        print('Total number of images selected: %d' % img_cnt)

    # download the images from the url (run read_url_from_file() first)
    def download_image(self):
        id_downloaded = []
        url_forbidden = []
        downloaded_log = os.path.join(self.cls_dir, 'downloaded.log')
        forbidden_log = os.path.join(self.cls_dir, 'forbidden.log')
        # check where the process of downloading should begin
        if os.path.exists(downloaded_log):
            r_downloaded_log = open(downloaded_log, 'r')
            for line in r_downloaded_log.readlines():
                id_downloaded.append(int(line.strip()))
            r_downloaded_log.close()
        # check which url is broken
        if os.path.exists(forbidden_log):
            r_forbidden_log = open(forbidden_log, 'r')
            for line in r_forbidden_log.readlines():
                url_forbidden.append(line.strip())
            r_forbidden_log.close()

        w_downloaded_log = open(downloaded_log, 'a')

        for landmark_id in self.url_dict.keys():
            if landmark_id in id_downloaded:
                continue
            cls_path = os.path.join(self.cls_dir, str(landmark_id))
            if not os.path.exists(cls_path):
                os.makedirs(cls_path)
            for k, url in enumerate(self.url_dict[landmark_id]):
                img_path = os.path.join(cls_path, str(k)+'.jpg')
                if not os.path.exists(img_path):
                    # pass if the url is broken
                    if url in url_forbidden:
                        continue
                    # add the url to the black-list before downloading
                    a_forbidden_log = open(forbidden_log, 'a')
                    a_forbidden_log.write(url + '\n')
                    a_forbidden_log.close()
                    # downloading ...
                    try:
                        urlretrieve(url, img_path)
                        # if successfully downloaded, remove the url from the black-list
                        r_forbidden_log = open(forbidden_log, 'r')
                        lines = r_forbidden_log.readlines()
                        r_forbidden_log.close()
                        w_forbidden_log = open(forbidden_log, 'w')
                        w_forbidden_log.writelines([u for u in lines[:-1]])
                        w_forbidden_log.close()
                    except Exception as e:
                        print('image of url %s missing ...' % url)
            w_downloaded_log.write(str(landmark_id)+'\n')
            print("%d images of landmark %d downloaded" % (len(self.url_dict[landmark_id]), landmark_id))

        w_downloaded_log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='build the landmark dataset')
    parser.add_argument('--root_dir', type=str, required=False, help='root path to the Paris dataset')
    parser.set_defaults(root_dir='/home/gordonwzhe/data/Paris/')
    args = parser.parse_args()

    landmark_dataset = LandMarkDataset(args.root_dir)
    landmark_dataset.read_url_from_file(l=100, h=150)
    landmark_dataset.download_image()

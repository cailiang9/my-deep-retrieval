# -*- coding: utf-8 -*-

# Python script that divide the Oxford dataset into the training set and the test set (size controlled by --train_ratio)
# It makes the training/test division of jpg and lab directory

# usage:  python ./myPython/make_train_test.py
#   --S 512
#   --train_dir /home/processyuan/data/myOxford/train-512/
#   --test_dir /home/processyuan/data/myOxford/test-512/

import os
import cv2
import argparse
import random
import numpy as np
import sys
sys.path.append("/home/processyuan/NetworkOptimization/deep-retrieval/myPython")
from class_helper import *


def transform_image(size, src, dst):
    im = cv2.imread(src)
    im_size_hw = np.array(im.shape[0:2])
    ratio = float(size) / np.max(im_size_hw)
    new_size = tuple(np.round(im_size_hw * ratio).astype(np.int32))
    im_resized = cv2.resize(im, (new_size[1], new_size[0]))
    cv2.imwrite(dst, im_resized)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Divide the dataset into training/test')
    parser.add_argument('--S', type=int, required=False, help='Resize larger side of image to S pixels (e.g. 800)')
    parser.add_argument('--dataset', type=str, required=False, help='Path to the Oxford / Paris directory')
    parser.add_argument('--train_ratio', type=float, required=False, help='ratio of the training set in the dataset')
    parser.add_argument('--train_dir', type=str, required=False, help='Path to directory of training set')
    parser.add_argument('--test_dir', type=str, required=False, help='Path to directory of test set')
    parser.set_defaults(S=512)
    parser.set_defaults(dataset='/home/processyuan/data/Oxford/')
    parser.set_defaults(train_ratio=0.5)
    parser.set_defaults(train_dir='/home/processyuan/data/myOxford/train/')
    parser.set_defaults(test_dir='/home/processyuan/data/myOxford/test/')
    args = parser.parse_args()

    # Load the dataset
    dataset = Dataset(args.dataset)

    img_dir = 'jpg'
    lab_dir = 'lab'
    img_all = []  # list of all image files: 5063 images in total
    img_root = os.path.join(args.dataset, img_dir)  # Path to images of original dataset
    lab_root = os.path.join(args.dataset, lab_dir)  # Path to txt of original dataset

    q_filename_temp = dataset.filename_to_name.keys()
    q_filename = [q_filename_temp[k] + '.jpg' for k in range(dataset.N_queries)]

    # delete first
    if not os.path.exists(args.train_dir):
        os.makedirs(args.train_dir)
        os.makedirs(os.path.join(args.train_dir, img_dir))
        os.makedirs(os.path.join(args.train_dir, lab_dir))
    else:
        train_jpg_path = os.path.join(args.train_dir, img_dir)
        for f in os.listdir(train_jpg_path):
            full_name = os.path.join(train_jpg_path, f)
            if os.path.isfile(full_name):
                os.remove(full_name)

    if not os.path.exists(args.test_dir):
        os.makedirs(args.test_dir)
        os.makedirs(os.path.join(args.test_dir, img_dir))
        os.makedirs(os.path.join(args.test_dir, lab_dir))
    else:
        test_jpg_path = os.path.join(args.test_dir, img_dir)
        for f in os.listdir(test_jpg_path):
            full_name = os.path.join(test_jpg_path, f)
            if os.path.isfile(full_name):
                os.remove(full_name)

    # get the list of all image files
    for f in os.listdir(img_root):
        img_all.append(f)

    random.shuffle(img_all)  # shuffle
    img_num = len(img_all)
    train_num = int(img_num * args.train_ratio)
    test_num = img_num - train_num
    img_train = img_all[0: train_num]
    img_test = img_all[train_num:]

    # make the "jpg" directory of training set (Note that images in queries is shared by both training and test set)
    for k in range(len(img_train)):
        src_file = os.path.join(img_root, img_train[k])
        dst_file = os.path.join(args.train_dir, img_dir, img_train[k])
        if os.path.isfile(src_file):
            if img_train[k] in q_filename:
                img_test.append(img_train[k])
            else:
                transform_image(args.S, src_file, dst_file)
        else:
            print('image not found: %s' % src_file)

    # make the "jpg" directory of test set
    for k in range(len(img_test)):
        src_file = os.path.join(img_root, img_test[k])
        dst_file = os.path.join(args.test_dir, img_dir, img_test[k])
        if os.path.isfile(src_file):
            if img_test[k] in q_filename:
                q_file = os.path.join(args.train_dir, img_dir, img_test[k])
                open(q_file, 'wb').write(open(src_file, 'rb').read())  # save the origin image
                open(dst_file, 'wb').write(open(src_file, 'rb').read())
                if img_test[k] not in img_train:
                    img_train.append(img_test[k])
            else:
                transform_image(args.S, src_file, dst_file)
        else:
            print('image not found: %s' % src_file)

    # make the "lab" directory
    for f in os.listdir(lab_root):
        full_name = os.path.join(lab_root, f)
        f_lab = open(full_name, 'r')
        f_train_lab = open(os.path.join(args.train_dir, lab_dir, f), 'w')
        f_test_lab = open(os.path.join(args.test_dir, lab_dir, f), 'w')
        if f.endswith('_query.txt'):
            content = f_lab.read()
            f_train_lab.write(content)
            f_test_lab.write(content)
        else:
            for line in f_lab.readlines():
                img_filename = line.strip() + '.jpg'
                if img_filename in img_train:
                    f_train_lab.write(line)
                if img_filename in img_test:
                    f_test_lab.write(line)
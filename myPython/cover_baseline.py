# -*- coding: utf-8 -*-

import os
import sys
import numpy as np
import caffe
import cv2
import argparse
from tqdm import tqdm


def get_rmac_region_coordinates(H, W, L):
    # Almost verbatim from Tolias et al Matlab implementation.
    # Could be heavily pythonized, but really not worth it...
    # Desired overlap of neighboring regions
    ovr = 0.4
    # Possible regions for the long dimension
    steps = np.array((2, 3, 4, 5, 6, 7), dtype=np.float32)
    w = np.minimum(H, W)

    b = (np.maximum(H, W) - w) / (steps - 1)
    # steps(idx) regions for long dimension. The +1 comes from Matlab
    # 1-indexing...
    idx = np.argmin(np.abs(((w ** 2 - w * b) / w ** 2) - ovr)) + 1

    # Region overplus per dimension
    Wd = 0
    Hd = 0
    if H < W:
        Wd = idx
    elif H > W:
        Hd = idx

    regions_xywh = []
    for l in range(1, L + 1):
        wl = np.floor(2 * w / (l + 1))
        wl2 = np.floor(wl / 2 - 1)
        # Center coordinates
        if l + Wd - 1 > 0:
            b = (W - wl) / (l + Wd - 1)
        else:
            b = 0
        cenW = np.floor(wl2 + b * np.arange(l - 1 + Wd + 1)) - wl2
        # Center coordinates
        if l + Hd - 1 > 0:
            b = (H - wl) / (l + Hd - 1)
        else:
            b = 0
        cenH = np.floor(wl2 + b * np.arange(l - 1 + Hd + 1)) - wl2

        for i_ in cenH:
            for j_ in cenW:
                regions_xywh.append([j_, i_, wl, wl])

    # Round the regions. Careful with the borders!
    for i in range(len(regions_xywh)):
        for j in range(4):
            regions_xywh[i][j] = int(round(regions_xywh[i][j]))
        if regions_xywh[i][0] + regions_xywh[i][2] > W:
            regions_xywh[i][0] -= ((regions_xywh[i][0] + regions_xywh[i][2]) - W)
        if regions_xywh[i][1] + regions_xywh[i][3] > H:
            regions_xywh[i][1] -= ((regions_xywh[i][1] + regions_xywh[i][3]) - H)
    return np.array(regions_xywh).astype(np.float32)


def pack_regions_for_network(all_regions):
    n_regs = np.sum([len(e) for e in all_regions])
    R = np.zeros((n_regs, 5), dtype=np.float32)
    cnt = 0
    # There should be a check of overflow...
    for i, r in enumerate(all_regions):
        try:
            R[cnt:cnt + r.shape[0], 0] = i
            R[cnt:cnt + r.shape[0], 1:] = r
            cnt += r.shape[0]
        except:
            continue
    assert cnt == n_regs
    R = R[:n_regs]
    # regs where in xywh format. R is in xyxy format, where the last coordinate is included. Therefore...
    R[:n_regs, 3] = R[:n_regs, 1] + R[:n_regs, 3] - 1
    R[:n_regs, 4] = R[:n_regs, 2] + R[:n_regs, 4] - 1
    return R


class CoverData:
    def __init__(self, dataset_path, L):
        self.path = dataset_path
        self.S = None
        self.L = L
        self.test_set = os.path.join(self.path, 'test')
        self.cls_set = os.path.join(self.path, 'cls')
        # calculates the mean on training set in advance
        self.mean = np.array([117.80904, 130.27611, 134.65074], dtype=np.float32)[:, None, None]
        self.dataset = os.listdir(os.path.join(self.test_set, 'dataset'))  # list of image names
        self.q_fname = []  # list of image names
        self.a_fname = []  # list of image names in list of classes
        self.a_idx = []  # list of image indices in list of classes
        q_lines = open(os.path.join(self.test_set, 'query.txt')).readlines()
        a_lines = open(os.path.join(self.test_set, 'answer.txt')).readlines()
        for line in q_lines:
            self.q_fname.append(line.strip())
        for line in a_lines:
            a_fname_list = line.strip().split(' ')
            self.a_fname.append(a_fname_list)
            self.a_idx.append([self.dataset.index(a_fname_list[i]) for i in range(len(a_fname_list))])

        self.num_queries = len(self.q_fname)
        self.num_dataset = len(self.dataset)

    def load_image(self, fname):
        img = cv2.imread(fname)
        if self.S is not None:
            img_size_hw = np.array(img.shape[0:2])
            ratio = float(self.S) / np.max(img_size_hw)
            new_size = tuple(np.round(img_size_hw * ratio).astype(np.int32))
            img = cv2.resize(img, (new_size[1], new_size[0]))
        return img.transpose(2, 0, 1) - self.mean

    def prepare_image_and_grid_regions_for_network(self, img_dir, fname):
        img = self.load_image(os.path.join(self.test_set, img_dir, fname))
        all_regions = [get_rmac_region_coordinates(img.shape[1], img.shape[2], self.L)]
        regions = pack_regions_for_network(all_regions)
        return np.expand_dims(img, axis=0), regions

    # Calculates the mean precision when number of prediction is equal to GT
    def cal_precision(self, sim, copy_img=False):
        assert len(sim.shape) == 2, 'This is a 2-dim similarity matrix'
        assert sim.shape[0] == self.num_queries, 'number of rows should be equal to number of queries'
        assert sim.shape[1] == self.num_dataset, 'number of columns should be equal to number of dataset'
        q_precision = np.zeros(self.num_queries, dtype=np.float32)
        idx = np.argsort(sim, axis=1)[:, ::-1]
        for q in range(self.num_queries):
            top_k = len(self.a_idx[q])  # choose the top-k prediction
            top_idx = list(idx[q, : top_k])
            cnt_correct = len([i for i in top_idx if i in self.a_idx[q]])
            q_precision[q] = float(cnt_correct) / float(top_k)
            # copy image to 'cls' directory to make a comparison
            if copy_img:
                top_img = [self.dataset[top_idx[i]] for i in range(len(top_idx))]
                for im in top_img:
                    src_img = os.path.join(self.test_set, 'dataset', im)
                    dst_img = os.path.join(self.cls_set, str(q/2), 'test_' + im)
                    if not os.path.exists(dst_img):
                        open(dst_img, 'wb').write(open(src_img, 'rb').read())

        return q_precision.mean(axis=0) * 100.0

    # Calculates the value of mAP according to the standard of VOC2010 and later
    def cal_mAP(self, sim):
        assert len(sim.shape) == 2, 'This is a 2-dim similarity matrix'
        assert sim.shape[0] == self.num_queries, 'number of rows should be equal to number of queries'
        assert sim.shape[1] == self.num_dataset, 'number of columns should be equal to number of dataset'
        q_AP = np.zeros(self.num_queries, dtype=np.float32)
        idx = np.argsort(sim, axis=1)[:, ::-1]
        for q in range(self.num_queries):
            cnt_correct_last = 0
            q_ans = self.a_idx[q]
            recall = np.zeros(len(q_ans), dtype=np.float32)
            for d in range(self.num_dataset):
                top_k = d+1
                top_idx = list(idx[q, : top_k])
                cnt_correct = len([i for i in top_idx if i in q_ans])
                assert cnt_correct >= cnt_correct_last
                assert cnt_correct <= len(q_ans)
                if cnt_correct > cnt_correct_last:
                    recall[cnt_correct-1] = float(cnt_correct) / float(top_k)  # precision under the given recall
                    cnt_correct_last = cnt_correct
                if cnt_correct == len(q_ans):
                    break
            # calculates the maximum precision when no less than given recall
            recall_max = np.zeros(len(q_ans), dtype=np.float32)
            for r in range(len(q_ans)):
                recall_max[r] = np.max(recall[r:])
            q_AP[q] = recall_max.mean(axis=0)
            print("AP of query %d: %f" % (q, q_AP[q]))  # print for checking as the function is too slow ...
        return q_AP.mean(axis=0) * 100.0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Evaluate on the cover dataset')
    parser.add_argument('--gpu', type=int, required=False, help='GPU ID to use (e.g. 0)')
    parser.add_argument('--L', type=int, required=False, help='Use L spatial levels (e.g. 2)')
    parser.add_argument('--proto', type=str, required=False, help='Path to the prototxt file')
    parser.add_argument('--weights', type=str, required=False, help='Path to the caffemodel file')
    parser.add_argument('--dataset', type=str, required=False, help='Path to the directory of cover data')
    parser.add_argument('--temp_dir', type=str, required=False,
                        help='Path to a temporary directory to store features and ranking')
    parser.set_defaults(gpu=0)
    parser.set_defaults(L=2)
    parser.set_defaults(proto='/home/processyuan/NetworkOptimization/deep-retrieval/proto/deploy_resnet101.prototxt')
    parser.set_defaults(weights='/home/processyuan/NetworkOptimization/deep-retrieval/'
                                'caffemodel/deep_image_retrieval_model.caffemodel')
    parser.set_defaults(dataset='/home/processyuan/NetworkOptimization/cover')
    parser.set_defaults(temp_dir='/home/processyuan/NetworkOptimization/deep-retrieval/eval/eval_test/')

    args = parser.parse_args()

    # Configure caffe and load the network ResNet-101
    caffe.set_device(args.gpu)
    caffe.set_mode_gpu()
    net = caffe.Net(args.proto, args.weights, caffe.TEST)

    # Load the cover dataset
    cData = CoverData(args.dataset, args.L)

    # Output of ResNet-101
    output_layer = 'rmac/normalized'  # suppose that the layer name is always the same as the blob name
    dim_features = net.blobs[output_layer].data.shape[1]
    features_queries = np.zeros((cData.num_queries, dim_features), dtype=np.float32)
    features_dataset = np.zeros((cData.num_dataset, dim_features), dtype=np.float32)

    Ss = [248, 496, 744]  # multi-solution
    # First part, queries
    for S in Ss:
        for k in tqdm(range(cData.num_queries), file=sys.stdout, leave=False, dynamic_ncols=True):
            cData.S = S
            img, reg = cData.prepare_image_and_grid_regions_for_network('queries', cData.q_fname[k])
            net.blobs['data'].reshape(img.shape[0], int(img.shape[1]), int(img.shape[2]), int(img.shape[3]))
            net.blobs['data'].data[:] = img
            net.blobs['rois'].reshape(reg.shape[0], reg.shape[1])
            net.blobs['rois'].data[:] = reg.astype(np.float32)
            net.forward(end=output_layer)
            features_queries[k] = np.squeeze(net.blobs[output_layer].data)
        features_queries_fname = os.path.join(args.temp_dir, "queries_S{0}.npy".format(S))
        np.save(features_queries_fname, features_queries)
    features_queries = np.dstack(
        [np.load((args.temp_dir, "queries_S{0}.npy".format(S))) for S in Ss]).sum(axis=2)
    # np.save(os.path.join(args.temp_dir, 'queries_baseline.npy'), features_queries)

    # Second part, dataset
    for S in Ss:
        for k in tqdm(range(cData.num_dataset), file=sys.stdout, leave=False, dynamic_ncols=True):
            cData.S = S
            img, reg = cData.prepare_image_and_grid_regions_for_network('dataset', cData.dataset[k])
            net.blobs['data'].reshape(img.shape[0], int(img.shape[1]), int(img.shape[2]), int(img.shape[3]))
            net.blobs['data'].data[:] = img
            net.blobs['rois'].reshape(reg.shape[0], reg.shape[1])
            net.blobs['rois'].data[:] = reg.astype(np.float32)
            net.forward(end=output_layer)
            features_dataset[k] = np.squeeze(net.blobs[output_layer].data)
        features_dataset_fname = os.path.join(args.temp_dir, "dataset_S{0}.npy".format(S))
        np.save(features_dataset_fname, features_dataset)
    features_dataset = np.dstack(
        [np.load("dataset_S{0}.npy".format(S)) for S in Ss]).sum(axis=2)
    # np.save(os.path.join(args.temp_dir, 'dataset_baseline.npy'), features_dataset)

    # Compute similarity
    sim = features_queries.dot(features_dataset.T)
    np.save(os.path.join(args.temp_dir, 'sim.npy'), sim)
    # sim = np.load(os.path.join(args.temp_dir, 'sim.npy'))  # test

    # Calculates the precision and mAP
    print('precision: %f' % cData.cal_precision(sim, True))
    print('mAP: %f' % cData.cal_mAP(sim))

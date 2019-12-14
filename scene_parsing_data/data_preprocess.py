import scene_parsing_data
import os
import pickle
import imageio
import numpy as np
import random
import multiprocessing
from scipy.ndimage.morphology import distance_transform_edt
from scipy.io import loadmat
import sys


def matlab_mat_to_numpy():
    """read the colour palette and convert to an nd array"""
    if not os.path.exists(scene_parsing_data.COLORMAP_ORIG_PATH):
        os.system('wget {} -O {}'.format(scene_parsing_data.COLOR_DOWNLOAD_URL, scene_parsing_data.COLORMAP_ORIG_PATH))

    colors = loadmat(scene_parsing_data.COLORMAP_ORIG_PATH)['colors']
    background_colour = np.zeros([1, 3], dtype=np.uint8)
    colors = np.concatenate([background_colour, colors], axis=0)
    np.save(scene_parsing_data.COLORMAP_PATH[:-4], colors)


def parse_object_info():
    """Convert the text file to a a dictionary with properly typed values"""
    is_header = True
    # will contain integer_id -> info
    meta_data = {}
    with open(scene_parsing_data.ORIG_OBJECT_INFO_PATH, 'r') as text_file:
        for row in text_file:
            if is_header:
                is_header = False
                continue
            else:
                info = row.split()
                id_ = int(info[0])
                ratio = float(info[1])
                train = int(info[2])
                val = int(info[3])
                names = info[4]
                meta_data[id_] = {
                    'ratio': ratio,
                    'train': train,
                    'val': val,
                    'names': names,}
    with open(scene_parsing_data.OBJECT_INFO_PATH, 'wb') as pfile:
        pickle.dump(meta_data, pfile)


def build_legend_info(object_ids):
    names = []
    colours = []
    for object_id in object_ids:
        if object_id == 0:
            names.append('other')
        else:
            object_info = scene_parsing_data.OBJECT_INFO[object_id]
            names.append(object_info['names'])
        colours.append(scene_parsing_data.COLOURS[object_id])
    return names, colours


##################################################################
# Building the edge maps
##################################################################


def flat_label_to_edge_mask(label,):
    """
    Converts a segmentation label (H,W) to a binary edgemap (H,W)
    """
    radius = 2

    one_hot_basis = np.eye(scene_parsing_data.N_CLASSES)
    one_hot = one_hot_basis[label]

    one_hot_pad = np.pad(one_hot, ((1, 1), (1, 1), (0, 0)), mode='constant', constant_values=0)
    edgemap = np.zeros(one_hot.shape[:-1])

    for i in range(scene_parsing_data.N_CLASSES):
        dist = distance_transform_edt(one_hot_pad[..., i]) + distance_transform_edt(1.0 - one_hot_pad[..., i])
        dist = dist[1:-1, 1:-1]
        dist[dist > radius] = 0
        edgemap += dist
    edgemap = np.expand_dims(edgemap, axis=-1)
    edgemap = (edgemap > 0).astype(np.uint8)
    return edgemap


def edge_path_from_label_path(label_path):
    label_name = os.path.basename(label_path)
    label_dir = os.path.dirname(label_path)
    edge_name = scene_parsing_data.EDGE_PREFIX + label_name
    edge_path = os.path.join(label_dir, edge_name)
    return edge_path

def label_path_to_edge_saved(label_path):
    edge_path = edge_path_from_label_path(label_path)
    label = imageio.imread(label_path)
    edge = flat_label_to_edge_mask(label)
    imageio.imsave(edge_path, edge)

def create_edge_labels():
    pool = multiprocessing.Pool(4)
    train_labels = [os.path.join(scene_parsing_data.TRAINING_ANNOTATION_DIR, x) for x in os.listdir(scene_parsing_data.TRAINING_ANNOTATION_DIR)]
    val_labels = [os.path.join(scene_parsing_data.VALIDATION_ANNOTATION_DIR, x) for x in os.listdir(scene_parsing_data.VALIDATION_ANNOTATION_DIR)]

    num_train = len(train_labels)
    print('creating training edge maps')
    for i, _ in enumerate(pool.imap_unordered(label_path_to_edge_saved, train_labels), 1):
        sys.stderr.write('\rdone {0:%}'.format(i / num_train))

    num_val = len(val_labels)
    print('creating val edge maps')
    for i, _ in enumerate(pool.imap_unordered(label_path_to_edge_saved, val_labels), 1):
        sys.stderr.write('\rdone {0:%}'.format(i / num_val))


def list_files(startpath):
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        print('{}{}/'.format(indent, os.path.basename(root)))
        subindent = ' ' * 4 * (level + 1)
        if len(files) > 100:
            print('{}#{}files'.format(subindent, len(files)))
        else:
            for f in files:
                print('{}{}'.format(subindent, f))


def get_dataset():
    if scene_parsing_data.DATA_DOWNLOAD_DIR is None:
        raise NotImplementedError('please specify the dataset directory in scene_parsing_data.__init__.py')

    # download the data and convert
    # the colour palette to numpy
    print('downloading raw scene parsing dataset and converting some')
    print('matlab files for use in python')
    os.system('wget {} -O {}'.format(scene_parsing_data.DATASET_URL, scene_parsing_data.DATA_DOWNLOAD_ZIP_PATH))
    os.system('unzip {} -d {}'.format(scene_parsing_data.DATA_DOWNLOAD_ZIP_PATH, scene_parsing_data.DATA_DOWNLOAD_DIR))
    os.remove(scene_parsing_data.DATA_DOWNLOAD_ZIP_PATH)
    print('converting object info txt file to python dictionary pickle')
    parse_object_info()
    print('downloading colour palette and converting to numpy array')
    matlab_mat_to_numpy()

    # build edge mask
    print('creating edge maps takes a long time!')
    create_edge_labels()
    print('FINIISHED!')
    print('your dataset directory looks like')
    list_files(scene_parsing_data.DATA_DIR)


##################################################################
def flat_label_to_plottable(label):
    coloured_image = scene_parsing_data.COLOURS[label]
    objects_present = np.unique(label)
    names, colours = build_legend_info(objects_present)
    return coloured_image, (names, colours)


def paths_from_example_id(example_id):
    image_path = os.path.join(scene_parsing_data.TRAINING_IM_DIR, example_id + '.jpg')
    label_path = os.path.join(scene_parsing_data.TRAINING_ANNOTATION_DIR, example_id + '.png')
    return image_path, label_path


def example_paths_from_single_path(single_path):
    example_id = os.path.basename(single_path)[:-4]
    return paths_from_example_id(example_id)


def get_random_example_paths():
    im_path = random.choice(os.listdir(scene_parsing_data.TRAINING_IM_DIR))
    return example_paths_from_single_path(im_path)


def get_random_example():
    im_p, label_p = get_random_example_paths()
    return imageio.imread(im_p), imageio.imread(label_p)


if __name__ == '__main__':
    get_dataset()
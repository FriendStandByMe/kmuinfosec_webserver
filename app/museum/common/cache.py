import os
import pickle


USER_HOME = os.path.expanduser('~')
CACHE_DIR = os.path.join(USER_HOME, 'museum_cache')
CACHE_SMALLEST_DIR = os.path.join(CACHE_DIR, 'smallest')
CACHE_MINMAX_DIR = os.path.join(CACHE_DIR, 'minmax')
CACHE_INDEPENDENT_DIR = os.path.join(CACHE_DIR, 'independent')
if not os.path.isdir(CACHE_DIR):
    os.mkdir(CACHE_DIR)
if not os.path.isdir(CACHE_SMALLEST_DIR):
    os.mkdir(CACHE_SMALLEST_DIR)
if not os.path.isdir(CACHE_MINMAX_DIR):
    os.mkdir(CACHE_MINMAX_DIR)
if not os.path.isdir(CACHE_INDEPENDENT_DIR):
    os.mkdir(CACHE_INDEPENDENT_DIR)


def check_cached(cache_path):
    if os.path.isfile(cache_path):
        return True
    else:
        return False


def get_cache_file_path(md5, index_info):
    if index_info['use_smallest']:
        cache_dir = CACHE_SMALLEST_DIR
    elif index_info['use_minmax']:
        cache_dir = CACHE_MINMAX_DIR
    # 예제에서는 둘다 아님
    else:
        cache_dir = CACHE_INDEPENDENT_DIR
    cache_dir = os.path.join(os.path.join(cache_dir, index_info['module'].get_info()), str(index_info['num_hash']))
    cache_dir = os.path.join(os.path.join(cache_dir, md5[:2]), md5[2:4])
    cache_file_path = os.path.join(cache_dir, md5)
    return cache_file_path


def load_cache(file_path):
    with open(file_path, 'rb') as f:
        cache_pkl = pickle.load(f)
    min_hashes, feature_size = cache_pkl[0], cache_pkl[1]
    return min_hashes, feature_size


def make_cache(cache_path, min_hashes, feature_size):
    with open(cache_path, 'wb') as f:
        pickle.dump((min_hashes, feature_size), f)

import sys

from museum.core import preprocess
from museum.data.elasticsearch.template import get_index_template, get_bulk_request, get_search_body, \
    get_msearch_request, get_exists_request
from museum.exception import *
from museum.common.utils import *
from museum.common.report import make_report_hits
from tqdm import tqdm

from elasticsearch import Elasticsearch, ConnectionTimeout
import os
import time


class MUSEUM:
    def __init__(self, host, port, use_caching=False):
        self.es = Elasticsearch(hosts=host, port=port, timeout=600)
        self.use_caching = use_caching

    def create_index(self, index, module, num_hash=128, use_smallest=False,
                     use_mod=False, use_minmax=False, shards=5, replicas=1, interval=10):
        if index == '':
            raise NotDefinedError("Index parameter is not passed")
        if self.es.indices.exists(index):
            raise AlreadyExistError("\"{}\" already exist index".format(index))

        res = self.es.indices.create(
            index=index,
            body=get_index_template(module, num_hash, use_smallest, use_mod, use_minmax, shards, replicas, interval)
        )
        return res

    def get_index_info(self, index_name):
        if not self.es.indices.exists(index=index_name):
            raise NotExistError("Index does not exist")
        index_info = self.es.indices.get_mapping(index=index_name)[index_name]['mappings']['_meta']
        # {
        #           "module_name" : "AsymmetricExtremum",
        #           "module_params" : {
        #             "window_size" : 128
        #           }
        index_info['module'] = module_loader(index_info['module_info'])
        return index_info

    # 인덱스 이름, 담을 디렉토리
    def bulk(self, index_name, target, process_count=8, batch_size=10000, disable_tqdm=False, pass_indexed_files=False):
        # index_info["module"] 에는 AE 객체
        index_info = self.get_index_info(index_name)

        if type(target) is list and type(target[0]) is list:
            preprocess_action = preprocess.by_file_bytes
        elif type(target) is list and type(target[0]) is str:
            preprocess_action = preprocess.by_file_path
        elif type(target) is str and os.path.isdir(target):
            # 엘라스틱서치에 담을 파일이름 리스트
            target = walk_directory(target)
            preprocess_action = preprocess.by_file_path
        else:
            raise NotADirectoryError("{} is not a directory".format(target))

        pbar = tqdm(total=len(target), desc="Bulk index", disable=disable_tqdm, file=sys.stdout)
        # batch_target_list - 10000개의 파일 절대 경로 리스트
        for batch_target_list in batch_generator(target, batch_size):
            if pass_indexed_files and preprocess_action == preprocess.by_file_path:
                remain_file_list = []
                exist_md5_set = self.__check_exists(index_name, batch_target_list)
                for file_path in batch_target_list:
                    # 이미 존재하는 파일이 아닐 경우
                    if not os.path.splitext(os.path.split(file_path)[1])[0] in exist_md5_set:
                        remain_file_list.append(file_path)
                    else:
                        pbar.update(1)
            else:
                remain_file_list = batch_target_list

            bulk_body_list = []
            # sampled_data -> 이게 해쉬된 128개의 값
            for file_md5, sampled_data, feature_size, target_name in mp_helper(preprocess_action, remain_file_list,
                                                                             process_count, index_info=index_info,
                                                                             use_caching=self.use_caching):
                if sampled_data:
                    bulk_body_list.append(get_bulk_request(file_md5, sampled_data, feature_size, target_name, index_name))
                pbar.update(1)

            if bulk_body_list:
                self.es.bulk(body=bulk_body_list)
        pbar.close()
        # print("Waiting {} sec for index refresh".format(index_info["refresh_interval"]))
        # time.sleep(int(index_info["refresh_interval"]))
    def sampling(self, index_name, target, limit=1, index_info=None):
        if not index_info:
            index_info = self.get_index_info(index_name)

        if type(target) is str:
            preprocess_action = preprocess.by_file_path
        else:
            preprocess_action = preprocess.by_file_bytes

        _, query_samples, query_feature_size, query_name = preprocess_action(target, index_info, self.use_caching)

        return query_samples
    def real_feature(self,index_name,file_path,index_info=None) :

        if not index_info:
            index_info = self.get_index_info(index_name)
        preprocess_action = preprocess.by_myself
        feature_set = preprocess_action(file_path,index_info)
        return feature_set
    def search(self, index_name, target, limit=1, index_info=None):
        x = time.time()
        if not index_info:
            index_info = self.get_index_info(index_name)

        if type(target) is str:
            preprocess_action = preprocess.by_file_path
        else:
            preprocess_action = preprocess.by_file_bytes

        _, query_samples, query_feature_size, query_name = preprocess_action(target, index_info, self.use_caching)

        report = {'query': query_name, 'hits': []}
        if query_samples:
            try:
                response = self.es.search(index=index_name, body=get_search_body(query_samples, limit), search_type='dfs_query_then_fetch')
            except ConnectionTimeout:
                print('Search error detected')
                return report
            report['hits'] = make_report_hits(response, query_samples, query_feature_size, index_info)
            report['time'] = time.time()-x
        return report

    def multi_search(self, index_name, target, limit=1, process_count=1, batch_size=100, disable_tqdm=False):
        if type(target) is list and type(target[0]) is list:
            preprocess_action = preprocess.by_file_bytes
        elif type(target) is list and type(target[0]) is str:
            preprocess_action = preprocess.by_file_path
        elif type(target) is str and os.path.isdir(target):
            target = walk_directory(target)
            preprocess_action = preprocess.by_file_path
        else:
            raise NotADirectoryError("{} is not a directory".format(target))

        index_info = self.get_index_info(index_name)
        pbar = tqdm(total=len(target), disable=disable_tqdm, desc="Multiple search", file=sys.stdout)
        for jobs in batch_generator(target, batch_size):
            search_data_list = []
            query_samples_list = []
            query_feature_size_list = []
            file_name_list = []
            for _, query_samples, query_feature_size, file_name in mp_helper(preprocess_action, jobs, process_count,
                                                                             index_info=index_info,
                                                                             use_caching=self.use_caching):
                if query_samples:
                    search_data_list.append(get_msearch_request(index_name, query_samples, limit))
                    query_samples_list.append(query_samples)
                    query_feature_size_list.append(query_feature_size)
                    file_name_list.append(file_name)
            report_list = []
            if search_data_list:
                try:
                    resp = self.es.msearch(body="\n".join(search_data_list))
                except ConnectionTimeout:
                    print('Search error detected')
                    continue
                for i, response in enumerate(resp['responses']):
                    report = {'query': file_name_list[i],
                              'hits': make_report_hits(response, query_samples_list[i],
                                                       query_feature_size_list[i], index_info)}
                    report_list.append(report)
            pbar.update(len(report_list))
            yield report_list
        pbar.close()

    def __check_exists(self, index_name, batch_file_list):
        # 파일 이름 리스트?
        md5_list = [os.path.splitext(os.path.split(file_path)[1])[0] for file_path in batch_file_list]
        exist_query_list = []
        for md5 in md5_list:
            exist_query_list.append(get_exists_request(index_name, md5))
        responses = self.es.msearch(body="\n".join(exist_query_list))['responses']
        exist_md5_set = set()
        for response in responses:
            hits = response['hits']['hits']
            if hits:
                exist_md5_set.add(hits[0]['_id'])
        return exist_md5_set
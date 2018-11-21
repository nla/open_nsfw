#!/usr/bin/env python
"""
Classify images in local or remote WARC files.

    ./classify_warc.py eg1.warc.gz http://example.org/eg2.warc.gz > classifications.txt

Based on open_nsfw which is:

Copyright 2016 Yahoo Inc.
Licensed under the terms of the 2 clause BSD license. 
Please see LICENSE file in the project root for terms.
"""
import argparse
import os
import traceback

if 'OMP_THREAD_LIMIT' not in os.environ:
    os.environ['OMP_THREAD_LIMIT'] = '1' # default to single-threaded, it seems multiple threads are not helpful.

os.environ['GLOG_minloglevel'] = '2' # Quieten log output. Must be set before importing caffe.

import caffe
import numpy as np
import sys
import hashlib
from binascii import hexlify
from base64 import b32decode
from socket import socket
from warcio.archiveiterator import ArchiveIterator
from urllib import urlretrieve
from tempfile import NamedTemporaryFile
from classify_nsfw import caffe_preprocess_and_compute
from multiprocessing import Manager, Process, cpu_count

def get_content_type(record):
    "Get the basic content-type of the record"
    content_type = record.http_headers.get_header('Content-Type')
    if content_type is None: return None
    return content_type.split(';')[0].lower().strip()

def calc_digest(record, image_data):
    "Calculate/read sha1 digest and truncate to 64-bits"
    header = record.rec_headers.get_header('WARC-Payload-Digest')
    if header and header.startswith('sha1:'):
        digest = b32decode(header.split(':')[1])
    else:
        digest = hashlib.sha1(image_data).digest()
    return hexlify(digest[:8]).upper()

sock = None

def read_warc(filename, args):
    if filename.startswith('http:') or filename.startswith('https:'):
        stream = NamedTemporaryFile('rb')
        sys.stderr.write('Fetching ' + filename + '\n')
        sys.stderr.flush()
        urlretrieve(filename, stream.name)
    else:
        stream = open(filename, 'rb')

    allowed_types = set(args.types.split(' '))

    for record in ArchiveIterator(stream, arc2warc=True):

        # Is this a 2xx image response with a sane size?
        if record.rec_type != 'response': continue
        if record.http_headers is None: continue
        if not args.min_length <= record.length <= args.max_length: continue
        if not 200 <= int(record.http_headers.get_statuscode()) < 300: continue
        if get_content_type(record) not in allowed_types: continue

        image_data = record.content_stream().read()

        digest = calc_digest(record, image_data)

        # Check with the classification lookup server if we've already seen this digest
        if args.server:
            if sock is None:
                sock = socket()
                host, port = args.server.split(':')
                sock.connect((host, int(port)))

            # C  - conditional store
            # \1 - queued for classification
            sock.write('C' + digest + '\1')
            response = sock.read(1)
            if response == 'N': continue # already seen

        url = record.rec_headers.get_header('WARC-Target-URI')
        yield url, digest, image_data

def classify_image(image_data, caffe_transformer, nsfw_net):
    "Run the classifier"
    try:
        return caffe_preprocess_and_compute(image_data, caffe_transformer=caffe_transformer, caffe_net=nsfw_net, output_layers=['prob'])[1]
    except:
        return -99.0

def reader(warcq, imageq, args):
    while True:
        filename = warcq.get()
        try:
          for url, digest, image_data in read_warc(filename, args):
               imageq.put((url, digest, image_data))
        except:
            traceback.print_exc()
        warcq.task_done()

def worker(imageq, outq):
    nsfw_net = caffe.Net("nsfw_model/deploy.prototxt", "nsfw_model/resnet_50_1by2_nsfw.caffemodel", caffe.TEST)
    caffe_transformer = caffe.io.Transformer({'data': nsfw_net.blobs['data'].data.shape})
    caffe_transformer.set_transpose('data', (2, 0, 1))  # move image channels to outermost
    caffe_transformer.set_mean('data', np.array([104, 117, 123]))  # subtract the dataset-mean value in each channel
    caffe_transformer.set_raw_scale('data', 255)  # rescale from [0, 1] to [0, 255]
    caffe_transformer.set_channel_swap('data', (2, 1, 0))  # swap channels from RGB to BGR

    while True:
        url, digest, image_data = imageq.get()
        score = classify_image(image_data, caffe_transformer, nsfw_net)
        outq.put((digest, score))
        imageq.task_done()

def printer(outq):
    while True:
        digest, score = outq.get()
        print digest, score
        outq.task_done()

def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--min-length', type=int, default=2000)
    parser.add_argument('--max-length', type=int, default=100000000)
    parser.add_argument('--types', nargs='+', default='image/jpeg image/png image/bmp image/gif')
    parser.add_argument('--server', help='host:port of classification lookup server')
    parser.add_argument('--print-url', help='include URLs in output', action='store_true')
    parser.add_argument('--readers', default=cpu_count(), type=int)
    parser.add_argument('--workers', default=cpu_count(), type=int)
    parser.add_argument('warcs', nargs='+')
    args = parser.parse_args()

    m = Manager()
    warcq = m.Queue()
    imageq = m.Queue(args.workers)
    outq = m.Queue(1000)

    for i in range(args.readers):
        Process(target=reader, args=(warcq, imageq, args)).start()

    for i in range(args.workers):
        Process(target=worker, args=(imageq, outq)).start()

    Process(target=printer, args=(outq,)).start()

    for filename in args.warcs:
        warcq.put(filename)

    warcq.join()
    imageq.join()
    outq.join()

if __name__ == '__main__':
    main(sys.argv)

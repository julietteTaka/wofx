
import os
import uuid
import json
import atexit
import logging
import tempfile
import multiprocessing
import mimetypes
import urllib
import requests
import imghdr

from flask import request, jsonify, send_file, abort, Response, make_response
from bson import json_util, ObjectId

import config
import renderScene

mimetypes.init()
mimetypes.add_type('image/bmp','.bmp')
mimetypes.add_type('image/x-panasonic-raw', '.raw')

# list of all computing renders
g_renders = {}
g_rendersSharedInfo = {}

# Pool for rendering jobs
# processes=None => os.cpu_count()
g_pool = multiprocessing.Pool(processes=4)
g_enablePool = False

# Manager to share rendering information
g_manager = multiprocessing.Manager()



def mongodoc_jsonify(*args, **kwargs):
    return Response(json.dumps(args[0], default=json_util.default), mimetype='application/json')


@config.g_app.route('/')
def index():
    return "ShuttleOFX Render service"

@config.g_app.route('/render', methods=['POST'])
def newRender():
    '''
    Create a new render and return graph information.
    '''
    inputScene = request.json
    renderID = str(uuid.uuid1())
    logging.info("RENDERID: " + renderID)
    scene, outputResources = renderScene.convertScenePatterns(inputScene)

    newRender = {}
    newRender['id'] = renderID
    # TODO: return a list of output resources in case of several writers.
    newRender['outputFilename'] = outputResources[0]
    newRender['scene'] = scene
    g_renders[renderID] = newRender

    config.g_app.logger.debug('new resource is ' + newRender['outputFilename'])

    renderSharedInfo = g_manager.dict()
    renderSharedInfo['status'] = 0
    g_rendersSharedInfo[renderID] = renderSharedInfo

    outputFilesExist = all([os.path.exists(os.path.join(config.renderDirectory, f)) for f in outputResources])
    if not outputFilesExist:
        if g_enablePool:
            g_pool.apply(renderScene.launchComputeGraph, args=[renderSharedInfo, newRender])
        else:
            renderScene.launchComputeGraph(renderSharedInfo, newRender)
    else:
        # Already computed
        renderSharedInfo['status'] = 3

    return jsonify(render=newRender)


@config.g_app.route('/progress/<renderID>', methods=['GET'])
def getProgress(renderID):
    '''
    Return render progress.
    '''
    return str(g_rendersSharedInfo[renderID]['status'])


@config.g_app.route('/render', methods=['GET'])
def getRenders():
    '''
        Returns all renders in JSON format
    '''
    totalRenders = {"renders": g_rendersSharedInfo}
    return jsonify(**totalRenders)


@config.g_app.route('/render/<renderID>', methods=['GET'])
def getRenderById(renderID):
    '''
    Get a render by id in json format.
    '''

    for key, render in g_renders.iteritems():
        if renderID == key:
            return jsonify(render=render)
    logging.error('id '+ renderID +" doesn't exists")
    abort(make_response("id "+ renderID +" doesn't exists", 404))


@config.g_app.route('/render/<renderId>/resource/<resourceId>', methods=['GET'])
def resource(renderId, resourceId):
    '''
    Returns file resource by renderId and resourceId.
    '''
    if not os.path.isfile( os.path.join(config.renderDirectory, resourceId) ):
        logging.error(config.renderDirectory + resourceId + " doesn't exists")
        abort(make_response(config.renderDirectory + resourceId + " doesn't exists", 404))

    return send_file( os.path.join(config.renderDirectory, resourceId) )

@config.g_app.route('/render/<renderID>', methods=['DELETE'])
def deleteRenderById(renderID):
    '''
    Delete a render from the render array.
    TODO: needed?
    TODO: kill the corresponding process?
    '''
    if renderID not in g_renders:
        logging.error("id "+renderID+" doesn't exists")
        abort(make_response("id "+renderID+" doesn't exists", 404))
    del g_renders[renderID]


@config.g_app.route('/resource', methods=['POST'])
def addResource():
    '''
    Upload resource file on the database
    '''
    if not 'file' in request.files:
        abort(make_response("Empty request", 500))

    mimetype = request.files['file'].content_type
    logging.debug("mimetype = " + mimetype)

    if not mimetype:
        logging.error("Invalid resource.")
        abort(make_response("Invalid resource.", 404))

    uid = config.resourceTable.insert({
        "mimetype" : mimetype,
        "size" : request.content_length,
        "name" : request.files['file'].filename,
        "registeredName" : ""})

    _, extension = os.path.splitext(request.files['file'].filename)
    if not extension:
        extension = mimetypes.guess_extension(mimetype)
    imgFile = str(uid) + extension
    config.resourceTable.update({"_id" : uid}, {"registeredName" : imgFile})
    imgFile = os.path.join(config.resourcesPath, imgFile)
    
    file = request.files['file']
    file.save(imgFile)

    resource = config.resourceTable.find_one({ "_id" : ObjectId(uid)})
    return mongodoc_jsonify(resource)


@config.g_app.route('/resource/<resourceId>', methods=['GET'])
def getResource(resourceId):
    '''
    Returns resource file.
    '''
    resource = os.path.join(config.resourcesPath, resourceId)

    if os.path.isfile(resource):
        return send_file(resource)
    else:
        logging.error("can't find " + resource)
        abort(make_response("can't find " + resource, 404))

@config.g_app.route('/resource/tmp/<resourceId>', methods=['GET'])
def getTmpResource(resourceId):
    '''
    Returns tmp resource file.
    '''
    resource = os.path.join(config.resourcesPath, 'tmp', resourceId)

    if os.path.isfile(resource):
        return send_file(resource)
    else:
        logging.error("can't find " + resource)
        abort(make_response("can't find " + resource, 404))

@config.g_app.route('/resource/', methods=['GET'])
def getResourcesDict():
    '''
    Returns all resources files from db.
    '''
    count = int(request.args.get('count', 10))
    skip = int(request.args.get('skip', 0))
    resources = config.resourceTable.find().limit(count).skip(skip)
    return mongodoc_jsonify({"resources":[ result for result in resources ]})

@config.g_app.route('/upload', methods=['GET'])
def uploadPage():
    return """<!DOCTYPE html>
      <html lang="en">
      <head>
      </head>
      <body>
        <div class="container">
          <div class="header">
            <h3 class="text-muted">UPLOAD A RESOURCE</h3>
          </div>
          <hr/>
          <div>
            <form action="/resource" method="POST" enctype="multipart/form-data">
              <input type="file" name="file">
              <br/><br/>
              <input type="submit" value="Upload">
            </form>
          </div>
        </div>
      </body>
      </html>"""

@config.g_app.route('/download', methods=['POST'])
def download():
    '''
    download an image from an url
    '''

    imgUrl = request.json['url']
    if imgUrl.isspace() or not imgUrl:
        abort(make_response("Empty request", 500))

    if not imgUrl.startswith('http://') and not imgUrl.startswith('https://'):
        imgUrl = 'http://' + imgUrl

    imgId = "tmp/" + str(uuid.uuid4())

    imgPath = os.path.join(config.resourcesPath, imgId)

    #urllib.urlretrieve(imgUrl, imgPath)

    try:
        imgData = requests.get(imgUrl)

    except requests.exceptions.ConnectionError as e:
        abort(make_response("Not exist", 404))

    if not imgData.status_code == requests.codes.ok:
        abort(make_response("Not found", imgData.status_code))

    if not imgData.headers['content-type'].startswith('image'):
        abort(make_response("Not an image", 404))

    imgFile = open(imgPath,'w+')
    imgFile.write(imgData.content)
    imgFile.close()

    ext = imghdr.what(imgPath)

    newImgPath = imgPath + "." + ext

    os.rename(imgPath, newImgPath)

    return imgId + "." + ext

@atexit.register
def cleanPool():
    '''
    Close processes and quit pool at exit.
    '''
    g_pool.close()
    g_pool.terminate()
    g_pool.join()

if __name__ == '__main__':
    config.g_app.run(host="0.0.0.0",port=5005,debug=True)

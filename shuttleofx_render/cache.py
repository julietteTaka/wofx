import os
from processify import processify

import config

@processify
def cleanCache():
    '''
        Clean the render folder so it does not get bigger
        than the limit set in the config file
    '''
    # Clean the render folder
    allFiles = []
    cacheSize = 0

    # Loop through each files and delete the oldest
    # TODO pass directory as an argument
    for path, dirs, files in os.walk(config.renderDirectory):
        # Ignore resources folder
        # TODO remove this if we want to make a generic function
        if 'resources' in dirs :
            dirs.remove('resources')

        for file in files:
            filePath = os.path.join(path, file)
            fileSize = os.stat(filePath).st_size
            # List all file : timestamp | size | filename
            allFiles.append((os.path.getmtime(filePath), fileSize, file))
            cacheSize += fileSize

    allFiles.sort()

    while cacheSize >= config.cacheMaxSize:
        for file in allFiles:
            # TODO Remove folder if empty ?
            os.remove(os.path.join(config.renderDirectory, os.path.join(config.renderDirectory, file[2])))
            cacheSize -= file[1]


def cachePathFromFile(filename):
    '''
        Create a path from a file
        example : convert 123456789.png to 1234/5678/9.png
    '''
    
    file, extension = os.path.splitext(filename)
    # Split hash in strings of 4 characters
    length = 4
    charactersList = [file[i:i+length] for i in range(0, len(file), length)]
    # Add the extension to the last element of the list
    charactersList[len(charactersList)-1] += extension

    return os.path.join(*charactersList)

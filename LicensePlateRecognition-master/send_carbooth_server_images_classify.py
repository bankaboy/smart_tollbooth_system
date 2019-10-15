# imports for classifier
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

# imports for license plate character detection
import tensorflow as tf
from tensorflow.keras import layers, models
import numpy as np
import cv2
import imutils
from darkflow.net.build import TFNet
import random
import time
from flask import Flask, render_template, request, flash, request, redirect, url_for, jsonify
import json
import requests
from statistics import mode
import glob

# used to detect plate using yolo model
options = {"pbLoad": "Plate_recognition_weights/yolo-plate.pb", "metaLoad": "Plate_recognition_weights/yolo-plate.meta", "gpu": 0.9}
yoloPlate = TFNet(options)

# used to detect characters on number plate
options = {"pbLoad": "Character_recognition_weights/yolo-character.pb", "metaLoad": "Character_recognition_weights/yolo-character.meta", "gpu":0.9}
yoloCharacter = TFNet(options)

characterRecognition = tf.keras.models.load_model('character_recognition.h5')

# function that returns the cropped  detection with the highest confidence (last in confidence sorted list)
# draws rectangle around the highest confidence of license plate detecttions given to it
def firstCrop(img, predictions):
    predictions.sort(key=lambda x: x.get('confidence'))
    xtop = predictions[-1].get('topleft').get('x')
    ytop = predictions[-1].get('topleft').get('y')
    xbottom = predictions[-1].get('bottomright').get('x')
    ybottom = predictions[-1].get('bottomright').get('y')
    firstCrop = img[ytop:ybottom, xtop:xbottom]
    cv2.rectangle(img,(xtop,ytop),(xbottom,ybottom),(0,255,0),3)
    return firstCrop
    
# applies contour function on top of the image
# used on top of the cropped out license plate
def secondCrop(img):
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    ret,thresh = cv2.threshold(gray,127,255,0)
    contours,_ = cv2.findContours(thresh,cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    areas = [cv2.contourArea(c) for c in contours]
    if(len(areas)!=0):
        max_index = np.argmax(areas)
        cnt=contours[max_index]
        x,y,w,h = cv2.boundingRect(cnt)
        cv2.rectangle(img,(x,y),(x+w,y+h),(0,255,0),2)
        secondCrop = img[y:y+h,x:x+w]
    else: 
        secondCrop = img
    return secondCrop

def auto_canny(image, sigma=0.33):
    # compute the median of the single channel pixel intensities
    v = np.median(image)
 
    # apply automatic Canny edge detection using the computed median
    lower = int(max(0, (1.0 - sigma) * v))
    upper = int(min(255, (1.0 + sigma) * v))
    edged = cv2.Canny(image, lower, upper)
 
    # return the edged image
    return edged

# find the characters in the image and return as a string
# works on top of the contoured license plate image
def opencvReadPlate(img):
    charList=[]
    gray = cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    thresh_inv = cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_MEAN_C,cv2.THRESH_BINARY_INV,39,1)
    edges = auto_canny(thresh_inv)
    ctrs, _ = cv2.findContours(edges.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    sorted_ctrs = sorted(ctrs, key=lambda ctr: cv2.boundingRect(ctr)[0])
    img_area = img.shape[0]*img.shape[1]

    for i, ctr in enumerate(sorted_ctrs):
        x, y, w, h = cv2.boundingRect(ctr)
        roi_area = w*h
        non_max_sup = roi_area/img_area

        if((non_max_sup >= 0.015) and (non_max_sup < 0.09)):
            if ((h>1.2*w) and (3*w>=h)):
                char = img[y:y+h,x:x+w]
                charList.append(cnnCharRecognition(char))
                cv2.rectangle(img,(x,y),( x + w, y + h ),(90,0,255),2)
    cv2.imshow('OpenCV character segmentation',img)
    cv2.waitKey()
    licensePlate="".join(charList)
    return licensePlate

# used to detect characters using keras model on the license plate
def cnnCharRecognition(img):
    dictionary = {0:'0', 1:'1', 2 :'2', 3:'3', 4:'4', 5:'5', 6:'6', 7:'7', 8:'8', 9:'9', 10:'A',
    11:'B', 12:'C', 13:'D', 14:'E', 15:'F', 16:'G', 17:'H', 18:'I', 19:'J', 20:'K',
    21:'L', 22:'M', 23:'N', 24:'P', 25:'Q', 26:'R', 27:'S', 28:'T', 29:'U',
    30:'V', 31:'W', 32:'X', 33:'Y', 34:'Z'}

    blackAndWhiteChar=cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blackAndWhiteChar = cv2.resize(blackAndWhiteChar,(75,100))
    image = blackAndWhiteChar.reshape((1, 100,75, 1))
    image = image / 255.0
    new_predictions = characterRecognition.predict(image)
    char = np.argmax(new_predictions)
    return dictionary[char]

'''FUNCTIONS FOR IMAGE CLASSIFICATION'''

def load_graph(model_file):
    graph = tf.Graph()
    graph_def = tf.GraphDef()
    
    with open(model_file, "rb") as f:
        graph_def.ParseFromString(f.read())
    with graph.as_default():
        tf.import_graph_def(graph_def)
    
    return graph
    

def read_tensor_from_image_file(image,
                                input_height=299,
                                input_width=299,
                                input_mean=0,
                                input_std=255):
    # input_image = cv2.imread(file_name)
    img2= cv2.resize(image,dsize=(input_height,input_width), interpolation = cv2.INTER_CUBIC)
    # Numpy array
    np_image_data = np.asarray(img2)
    # maybe insert float convertion here - see edit remark!
    np_final = np.expand_dims(np_image_data,axis=0)
    normalized = tf.divide(tf.subtract(np_final, [input_mean]), [input_std])
    sess = tf.Session()
    result = sess.run(normalized)

    return result


def load_labels(label_file):
    label = []
    proto_as_ascii_lines = tf.gfile.GFile(label_file).readlines()
    for l in proto_as_ascii_lines:
        label.append(l.rstrip())
    return label

def predict(image):
    model_file = "Vehicle_classifier_weights/output_graph.pb"
    label_file = "Vehicle_classifier_weights/output_labels.txt"
    input_height = 299
    input_width = 299
    input_mean = 0
    input_std = 255
    input_layer = "Mul"
    output_layer = "final_result"


    graph = load_graph(model_file)
    t = read_tensor_from_image_file(
        image,
        input_height=input_height,
        input_width=input_width,
        input_mean=input_mean,
        input_std=input_std)

    input_name = "import/" + input_layer
    output_name = "import/" + output_layer
    input_operation = graph.get_operation_by_name(input_name)
    output_operation = graph.get_operation_by_name(output_name)

    with tf.Session(graph=graph) as sess:
        results = sess.run(output_operation.outputs[0], {
          input_operation.outputs[0]: t
        })
    results = np.squeeze(results)

    top_k = results.argsort()[-5:][::-1]
    labels = load_labels(label_file)
    return [top_k, labels, results]

def main(booth_image_directory):

    for file in glob.glob(booth_image_directory+'/*'):
        frame = cv2.imread(file)
        print("\n Printing results for image file: ",file)
        h, w, l = frame.shape
        # frame = imutils.rotate(frame, 270)

        try:
            booth_number = random.randint(1,5)
            predictions = yoloPlate.return_predict(frame)
            firstCropImg = firstCrop(frame, predictions)
            # cv2.imshow('First crop plate',firstCropImg)
            secondCropImg = secondCrop(firstCropImg)
            # cv2.imshow('Second crop plate',secondCropImg)
            secondCropImgCopy = secondCropImg.copy()
            licensePlate = opencvReadPlate(secondCropImg)

            vehicle_dict =  {}
            # create a single record for the vehicle
            ts =  time.time()
            top_k, labels, results = predict(frame)
            vehicle_dict['Type']
            vehicle_dict['Timestamp'] = ts
            vehicle_dict['LicenseNumber'] = licensePlate
            vehicle_dict['BoothID'] = 'A'+str(booth_number)
            vehicle_record = json.dumps(vehicle_dict)
            print(vehicle_record)
            # request = requests.post("http://192.168.43.156:8000/record/add", data=car_dict)
                        
        except Exception as e:
            # pass
            print('EXCEPTION: ', e)


main('./test_images')
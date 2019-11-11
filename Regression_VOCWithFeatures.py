import numpy as np
import pandas as pd
from math import trunc
import pickle
import copy
import random
from sklearn.ensemble import RandomForestRegressor
from sklearn import metrics

#vocRounding is used to truncate the VOCs to 3dp allowing for flexible matching between 2013 and 2015 datasets
def vocRounding(vocDf):
    vocList = list()
    for index in range(0, len(vocDf.columns)):
        if vocDf.columns[index] == 'Time' or vocDf.columns[index] == 'ocs' or vocDf.columns[index] == 'co' or vocDf.columns[index] == 'CO2':
            vocList.append(vocDf.columns[index])    
        else:
            #string slice to get the molar mass
            voc = vocDf.columns[index]
            mass = (trunc(float(voc[1:])*1000))/1000 #TRUNCATE TO 3DP
            vocList.append(mass)
    return vocList

#generate normalised screenings
#remove invalid screenings (divide by NaN or divide by 0)
def generateNormalisedScreenings(sliceDict, vocData):
    screeningList = list()
    matchedMovies = list()
    for index in range(0,sliceDict['sliceDf'].shape[0]):
        start,end = sliceDict['sliceDf'].loc[index]
        screening = vocData[start:end+1]
        normalisedFrame = copy.deepcopy(screening)
        if max(normalisedFrame.values) != 0 and not(np.isnan(max(normalisedFrame.values))):
            normalisedFrame = normalisedFrame.values/max(normalisedFrame.values)
            screeningList.append(normalisedFrame)
            matchedMovies.append(sliceDict['matchedMovies'][index])
    return screeningList, matchedMovies


def grouping(visualList):
    framesPerInterval = 30
    movieVisuals = list()
    for index in range(0, int(len(visualList)/framesPerInterval)):
        segment = visualList[index*framesPerInterval:index*framesPerInterval+framesPerInterval]
        movieVisuals.append(segment)
    return movieVisuals

def processVisuals(movieVisualData, runtime, isColour):
    visualDataIntervals = grouping(movieVisualData)
    #the visual data also has the credits accounted for so remove them
    visualDataIntervals = visualDataIntervals[:runtime]
    #create a dataframe 
    if isColour: 
        #create a dominant colour dataframe
        framesPerInterval = 30
        header = list();
        for i in range(1,framesPerInterval+1):
            header = header + ['R'+str(i), 'G' + str(i),  'B'+str(i)]
    else: #shade object to be parsed
        framesPerInterval = 30
        header = ['S' + str(x) for x in range(1,framesPerInterval+1)]
    
    visualDf = pd.DataFrame(columns=header)
    #assemble the dataframe
    for segment in visualDataIntervals:
        index = visualDataIntervals.index(segment)
        colourRow = list()
        for colour in segment:
            if isColour:
                colourRow = colourRow + [colour[0], colour[1], colour[2]]
            else:
                colourRow = colourRow + [colour[0]]
        #assign that colour row to the dataframe
        visualDf.loc[index] = colourRow
            
    return visualDf

def processAudio(runtime, audio):
    audioFeatures = list(audio.keys())

    audioDf = pd.DataFrame(columns=[])        
    for key in audioFeatures:
        audio[key] = audio[key][:runtime]

        #assemble df 
        #create header
        if key != 'tempo':
            header = [key + str(x) for x in range(1, len(audio[key][0])+1)]
        else:
            header = ['tempo']

        audioFeatureDf = pd.DataFrame(columns=header)
        for index in range(0, len(audio[key])):
            feature = audio[key][index]
            audioFeatureDf.loc[index] = feature

        #concatenate featureDf to audioDf
        audioDf = pd.concat([audioDf,audioFeatureDf], axis=1)
    
    return audioDf

def processSubtitles(subs, effectiveRuntime):
    
    header = ['sentiment value']
    subSentimentDf = pd.DataFrame(columns=header)
    for sentimentIndex in range(0, len(subs)):
        sentiment = subs[sentimentIndex]
        if len(sentiment) != 0:
            if sentiment['sentimentValue'] == np.NaN:
                print('YES')
            else:         
                subSentimentDf.loc[sentimentIndex] = [sentiment['sentimentValue']]
        else:
            subSentimentDf.loc[sentimentIndex] = [-1] #indicates no dialog occurred during the scene
        
        #enforce no dialog until the credit scene if there is in fact no dialog
        if len(subSentimentDf) != effectiveRuntime:
            #no dialog at the end thus need to fill the rest with -1
            for index in range(0, effectiveRuntime-len(subSentimentDf)+1):
                 subSentimentDf.loc[index] = [-1]
    
    return subSentimentDf

def processASL(asl, effectiveRuntime):
    
    header = ['average shot length']
    aslDf = pd.DataFrame(columns=header)
    for index in range(0, effectiveRuntime): 
        aslValue = asl[index]
        aslDf.loc[index] = aslValue
    return aslDf

#train test split - one movie is left out for the test set 
def movieTrainTestSplit(movieList,matchedMovies,screeningList):
    
    testScreeningList = list()
    testMovieList = list()
    testMovie = movieList[random.randint(0, len(movieList)-1)] #pick random test movie 
    while True:
        try:
            matchedIndex = matchedMovies.index(testMovie)
            screening = screeningList.pop(matchedIndex)
            testScreeningList.append(screening)
            matchedMovie = matchedMovies.pop(matchedIndex)
            testMovieList.append(testMovie)
        except ValueError:
            break
    
    return testScreeningList,testMovieList,screeningList,matchedMovies


#create overall feature label dataframe
def inputOutputDf(screeningList,matchedMovies,movieFeatureDict):
    
    #create input-output df
    info = np.array([])
    for i in range(0, len(screeningList)): 
        
        matchedMovie = matchedMovies[i]
        screening = screeningList[i]  
        
        #input voc's 
        inputVOC = [screening[x:x+10] for x in range(0,len(screening))]
        inputVOCMatrix = np.array([])
        for vocSeq in inputVOC:
            if len(vocSeq) == 10:
                if inputVOCMatrix.size == 0:
                    inputVOCMatrix = vocSeq
                else:
                    inputVOCMatrix = np.vstack((inputVOCMatrix,vocSeq))
    
        #only join movie if the movie screening and the length of the features is the same
        if len(movieFeatureDict[matchedMovie]) == len(screening[9:]):
            #concatenate the movie features and the vocs 
            if info.size == 0:
                features = np.hstack((inputVOCMatrix,movieFeatureDict[matchedMovie].values))
                info = np.hstack((features,np.expand_dims(screening[9:], axis=1)))
            else:
                features = np.hstack((inputVOCMatrix,movieFeatureDict[matchedMovie].values))
                info = np.vstack((info,
                                 np.hstack((features,np.expand_dims(screening[9:], axis=1)))))
                
    
    #convert all values inside the dataset to floats
    info = info.astype(float)
    
    return info 

#regressor 
def RegressionModel(featuresTrain,labelsTrain, labelsTest, featuresTest):
    
    regressor = RandomForestRegressor() #random forest will base parameters
    regressor.fit(featuresTrain, labelsTrain)
    labelsPred = regressor.predict(featuresTest)
    
    #metrics
    RMSE = np.sqrt(metrics.mean_squared_error(labelsTest, labelsPred))
    MAE = metrics.mean_absolute_error(labelsTest, labelsPred)
    R2 = metrics.r2_score(labelsTest, labelsPred)
    
    return RMSE,MAE,R2

def main():
    
    resultsHeader = ['RandomState','VOC','RMSE', 'MAE', 'R2']
    #FEATURE DF

    #overall feature and labels df
    featureDf = pd.DataFrame([]) #film feature dataframe
    labelDf = pd.DataFrame([]) #voc dataframe

    #import movie runtimes
    movieRuntimesPath = 'Numerical Data/movie_runtimes.csv'
    movieRuntimeDf = pd.read_csv(movieRuntimesPath, usecols = ['movie', 'runtime (mins)', 'effective runtime'])
    movieList = list(movieRuntimeDf['movie'])
    movieFeatureDict = dict() #dict contains the movie film features with the keys being the movies
    #import pickle objects for movies and then assemble the dataframes  
    for movie in movieList:
        #load pickle feauture objects
        featurePath = 'Pickle Objects/Audio Feature Pickle Objects/' + movie + '.p'
        audio = pickle.load(open(featurePath, "rb" )) 
        featurePath = 'Pickle Objects/Colour Pickle Objects/' + movie + '.p'
        colour = pickle.load(open(featurePath, "rb" )) 
        featurePath = 'Pickle Objects/Shade Pickle Objects/' + movie + '.p'
        shade = pickle.load(open(featurePath, "rb" )) 
        featurePath = 'Pickle Objects/Subtitle Sentiment Pickle Objects/' + movie + '.p'
        sentiment = pickle.load(open(featurePath, "rb" )) 
        featurePath = 'Pickle Objects/ASL Pickle Objects/' + movie + '.p'
        asl = pickle.load(open(featurePath, "rb" )) 

        runtime = int(movieRuntimeDf.loc[movieList.index(movie)]['effective runtime'])

        colourDf = processVisuals(colour, runtime, True)
        shadeDf = processVisuals(shade, runtime, False)
        audioDf = processAudio(runtime, audio)
        sentimentDf = processSubtitles(sentiment,runtime)
        aslDf = processASL(asl, runtime)

        #add windowing
        effectiveRuntime = movieRuntimeDf['effective runtime'][movieList.index(movie)]
        movieFeatureArray = np.array([])
        for index in range(9, effectiveRuntime):
            endIndex = index
            startIndex = index - 9
            colourWindow = colourDf.loc[startIndex:endIndex,:].values.ravel() #create 1D vector of values
            audioWindow = audioDf.loc[startIndex:endIndex,:].values.ravel()
            shadeWindow = shadeDf.loc[startIndex:endIndex,:].values.ravel()
            sentimentWindow = sentimentDf.loc[startIndex:endIndex,:].values.ravel() 
            aslWindow = aslDf.loc[startIndex:endIndex,:].values.ravel()
            window = np.concatenate([colourWindow, audioWindow, shadeWindow, sentimentWindow,aslWindow])
            if len(movieFeatureArray) == 0:
                movieFeatureArray = window
            else:
                movieFeatureArray = np.vstack([movieFeatureArray, window])

        movieFeatureDict[movie] = pd.DataFrame(movieFeatureArray)

    print('Features Loaded')
    
    #CREATE VOC DF
    #import various numeric csvs
    vocPath = 'Numerical Data/2013VOCData.csv'
    voc2013DfAll = pd.read_csv(vocPath, header = 0, nrows = 74208, low_memory=False)
    movieScreeningsPath = 'Numerical Data/screening_times.csv'
    movingScreeningsDf = pd.read_csv(movieScreeningsPath, usecols = ['scheduled','movie','filled %'])
    movieRuntimesPath = 'Numerical Data/movie_runtimes.csv'
    movieRuntimeDf = pd.read_csv(movieRuntimesPath, usecols = ['movie', 'runtime (mins)', 'effective runtime'])
    #2015 Dataset
    starWarsPath = 'Numerical Data/Star Wars-The Force Awakens.csv'
    starWarsScreeningDf = pd.read_csv(starWarsPath)
    imOffThenPath = 'Numerical Data/I\'m Off Then.csv'
    imOffThenScreeningDf = pd.read_csv(imOffThenPath)
    helpIShrunkTheTeacherPath = 'Numerical Data/Help, I Shrunk My Teacher.csv'
    helpIShrunkTheTeacherScreeningDf = pd.read_csv(helpIShrunkTheTeacherPath)
    vocPath = 'Numerical Data/2015VOCData.csv'
    voc2015DfAll = pd.read_csv(vocPath)
    #remove first column of 2015 voc df as its not used
    voc2015DfAll.drop("Unnamed: 0", axis=1, inplace=True)

    #full list of movies
    movieList = list(movieRuntimeDf['movie'])


    #import the slicing indices
    slicePath = 'Pickle Objects/VocSlices.p'
    sliceDict = pickle.load(open(slicePath, "rb" )) #contains df of co2 slice indices and matched movie list

    #round the vocs
    voc2015Col = vocRounding(voc2015DfAll)
    voc2013Col = vocRounding(voc2013DfAll)
    voc2013Df = copy.deepcopy(voc2013DfAll)
    voc2015Df = copy.deepcopy(voc2015DfAll)
    voc2013Df.columns = voc2013Col
    voc2015Df.columns = voc2015Col

    #rearrange dataframe to be able to merge them successfully
    voc = voc2015Df.columns[1:]
    voc2015Df = pd.DataFrame(np.transpose(voc2015Df.values)[1:,:], columns =voc2015Df['Time'])
    voc2015Df['voc'] = voc
    voc = index=voc2013Df.columns[1:]
    voc2013Df = pd.DataFrame(np.transpose(voc2013Df.values)[1:,:], columns =voc2013Df['Time'])
    voc2013Df['voc'] = voc

    #join the two voc dataframes (join on the 2013 dataframe)
    vocDf = pd.merge(voc2013Df, voc2015Df, how='inner', on=['voc'])
    #drop voc column
    vocColumn = vocDf['voc']
    vocDf.drop("voc", axis=1, inplace=True)


    #reorientate the vocDf, note need to convert all vocs to float
    vocDf = pd.DataFrame(np.transpose(vocDf.values.astype(float)), columns=vocColumn)

    print('Create VOC Dataframe')

    resultsList = list()
    startIndex = 0
    endIndex = 1
    randomisationIterations = 100

    for vocIndex in range(startIndex,endIndex):
        for i in range(0,randomisationIterations):
            print('Iteration: ', str(i))

            voc = vocDf.columns[vocIndex]
            print(voc)
            vocData = vocDf[voc]

            print('Process Data')
            #generate normalised screenings
            screeningList, matchedMovies = generateNormalisedScreenings(sliceDict, vocData)

            #movie-based train test split
            #normal screenings
            testScreenings,testMovies,trainScreenings,trainMovies = movieTrainTestSplit(movieList,matchedMovies,screeningList)

            #normal input/output df
            testSet = inputOutputDf(testScreenings,testMovies,movieFeatureDict)
            trainSet = inputOutputDf(trainScreenings,trainMovies,movieFeatureDict)

            #extract labels and features
            #unrandomised
            featuresTrain = trainSet[:, 0:-1]
            labelsTrain = trainSet[:,-1]
            featuresTest = testSet[:, 0:-1]
            labelsTest = testSet[:,-1]

            print('Run regression')
            #regression
            #regressor - unrandomised
            RMSE,MAE,R2 = RegressionModel(featuresTrain,labelsTrain, labelsTest,featuresTest)
            resultsList.append([False, voc, RMSE,MAE,R2])

            print('Write results to file')
            #create results Df
            resultsDf = pd.DataFrame(resultsList,columns=resultsHeader)
            #write df to output file
            resultsPath = str(voc) + 'MovieFeaturesAndVOCs.csv'
            resultsDf.to_csv(resultsPath, sep=',', encoding='utf-8')
            print()
        
main()
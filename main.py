"""
WallScrape Main Driver

@author Victor Gong
@version 12/17/2024
"""

import csv
import Scraper
from concurrent.futures import ThreadPoolExecutor
import Visualizer
import Analyzer
import itertools
import AutoPrinter as AP

#INSTALL ALL LIBRARIES IN TERMINAL/COMMAND PROMPT WITH: pip install -r /path/to/requirements.txt

#Scrape Info
targetStock = "nvidia"
targetSubPosts = "https://www.reddit.com/r/wallstreetbets/search/?q="+targetStock+"&type=posts&sort=new"
targetSubComments = "https://www.reddit.com/r/wallstreetbets/search/?q="+targetStock+"&type=comments&sort=new"

#Data files
postsFileName = "data/post_"+targetStock+".csv" #Post URLs from subreddit

#Result files
catStatsFileName = "results/category_stats.csv" #Topic categories of articles with frequency and average political lean

#Dictionaries
postsDict = {} #Format: {url -> (title, description, ts, karma, comments, user)}
postsList = [] #Format: [(url, title, description, ts, karma, comments, user),...]



"""
=========================================================
			        REDDIT SCRAPING
=========================================================
"""

#Reads all content from the posts .csv and populates postDict (removes duplicates and updates existing post info)
def loadPosts():
    with open(postsFileName, "r") as csvF:
        csvReader = csv.reader(csvF)
        csvContent = [line for line in csvReader]
        for post in csvContent:
            url, title, description, ts, karma, comments, user = post
            postsDict[url] = (title, description, ts, karma, comments, user)
            postsList.append((url, title, description, ts, karma, comments, user))

#Scrapes all posts from target subreddit and records in posts .csv
def scrapePosts():
    for p in Scraper.extractPosts(targetSubPosts):
        url, title, description, ts, karma, comments, user = p
        postsDict[url] = (title, description, ts, karma, comments, user)

#Writes content in postDict to posts .csv
def writePosts():
    print("Writing posts to file",postsFileName,"...")
    with open(postsFileName, "w") as csvF:
        csvWriter = csv.writer(csvF)
        for url in postsDict.keys():
            title, description, ts, karma, comments, user = postsDict[url]
            csvWriter.writerow([url, title, description, ts, karma, comments, user])
            print("Wrote ",url)

"""
=========================================================
                     DATA ANALYSIS
=========================================================
**Note, 'send' methods append rather than overwrite to allow for several batches of processing
"""

#Sends a bulk request to Batch API for black-white political analysis of all articles
def sendRequest_ArticlesBWPolitics(startIndex=0, confirmMsg=True):
   AP.printLine(); print("Sending bulk request for BW analysis"); AP.printLine()
   print("Total post count:", len(postsList))
   #Send the request through Analyzer module
   Analyzer.createBatch_BWAnalysis(postsList, targetStock, startIndex, confirmMsg)


#Sends a bulk request to Batch API for full political evaluation of white (politically-marked) articles
def sendRequest_ArticlesEvalPolitics(startIndex=0, fileLineStart=1, confirmMsg=True):
   AP.printLine(); print("Sending bulk request for evaluation"); AP.printLine()

   #Read article information
   processList = []; postSet = set()
   with open(Analyzer.BWFileName, "r") as csvF:
      csvReader = csv.reader(csvF)
      csvContent = [line for line in csvReader]

      for articleInfo in csvContent[fileLineStart-1:]:
         url = articleInfo[0]
         isPolitical = "y" in articleInfo[1].lower()
         title, description, ts, karma, comments, user = postsDict[url]

         #Check if article related to politics (from BW analysis) and prevent repetitions
         if isPolitical and url not in postSet:
            processList.append((url, title, description, ts, karma, comments, user)) #Append to table
            postSet.add(url)
    
   print("Total article count:", len(processList))
   #Send the request through Analyzer module
   Analyzer.createBatch_Eval(processList, targetStock, startIndex, confirmMsg)

"""<<Control Center>>"""

#===Post scraping===#
#scrapePosts(); writePosts()

#===AI Analysis===#
loadPosts()
sendRequest_ArticlesBWPolitics()
#===Calculations/Visualization===#

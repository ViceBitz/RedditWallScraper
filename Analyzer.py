from openai import OpenAI
import nltk
import nltk
import ssl
import json, ujson, csv
from pathlib import Path
import time
import math
client = OpenAI(api_key = "do not steal my key")

#Download NLTK Punkt package (comment out if done)
"""
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context
nltk.download('punkt')
"""

"""
Analyzes a given article in the realm of politics and entertainment, utilizing the GPT model
to deduce factors like partisanship or general trends.

@author Victor Gong
@version 7/27/2024
"""

#Batch in/out filenames
batchBWInFileName = "requests_in/batch_bw_in.jsonl" #Black-white analysis batch IN file
batchEvalInFileName = "requests_in/batch_eval_in.jsonl" #Evaluation batch IN file

batchBWOutFileName = "requests_out/batch_bw_out.jsonl" #Black-white analysis batch OUT file
batchEvalOutFileName = "requests_out/batch_eval_out.jsonl" #Evaluation batch OUT file

#Result filenames
BWFileName = "results/post_bw.csv" #Black-white analysis for all posts
EvalFileName = "results/post_eval.csv" #Full evaluation for all posts

#Log filenames
logBWFileName = "log/bw_log.csv"
logEvalFileName = "log/eval_log.csv"

TEXT_MIN_CUTOFF = 500 #Articles under this limit won't be considered
TEXT_MAX_CUTOFF = 1000 #Articles over this limit will be trimmed to the limit

MAX_BATCH_TOKENS_BW = 200000 #Max tokens can send per batch for BW
MAX_BATCH_TOKENS_CAT = 20000000-50000 #20000000 Max tokens can send per batch for categorical
MAX_BATCH_TOKENS_EVAL = 90000 #Max tokens can send per batch for eval

"""
=========================================================
               ARTICLE PREPROCESSING / MISC
=========================================================
"""

#Helper functions to read and write to jsonl
def read_jsonl(file_path):
    with Path(file_path).open('r', encoding='utf8') as f:
        for line in f:
            try:  # hack to handle broken jsonl
                yield ujson.loads(line.strip())
            except ValueError:
                continue
def write_jsonl(file_path, lines):
   data = [ujson.dumps(line, escape_forward_slashes=False) for line in lines]
   Path(file_path).open('w', encoding='utf-8').write('\n'.join(data))

"""
=========================================================
                  PROMPT GENERATION
=========================================================
"""
#Generates the prompt table to ask GPT-3.5 for black-white analysis (if the article is related or not)
def generatePrompts_BW(title, description, stock):
   prompts = [{"role":"system", "content":"You are an intelligent stock market analyst."}]

   #Check if article is even remotely related or not
   prompts.append({"role":"user", "content":"Take into account this Reddit post with title '" + title + "' and description'" +description+"',"+
                   "Is this post related to " + stock + "'s stock or market behavior? Answer with strictly Y or N"})
   
   return prompts

#Generate the prompt table to ask GPT-4o for stock evaluation rating
def generatePrompts_Eval(title, description, stock):
   prompts = [{"role":"system", "content":"You are an intelligent stock market analyst."}]

   #Ask for political rating
   prompts.append({"role":"user","content":"Assign a optimism score on scale of -100 (negative) to 100 (positive) surrounding " + stock + " stock of this Reddit post with " + "TITLE:'"
               + title + "' and DESCRIPTION: '" + description + "' Try not 0.0, specific and precise, one sig. fig. Format: number | 1-word justification"})
   return prompts

"""
=========================================================
                        AI ANALYSIS
=========================================================
"""

#Finalizes and sends a batch request to ChatGPT API given requests file
def finalizeBatch(reqsFileName, desc, confirmMsg):
   #Send to Batch API
   confirmMsg = input("Double check "+reqsFileName+" for correct info: (1) Confirm, (2) Cancel\n") if confirmMsg else "1"
   if confirmMsg == "1":
      batch_input_file = client.files.create(
         file=open(reqsFileName, "rb"),
         purpose="batch"
      )
      file_id = batch_input_file.id

      batch = client.batches.create(
         input_file_id=file_id,
         endpoint="/v1/chat/completions",
         completion_window="24h",
         metadata={"description" : desc}
      )
      print("Successfully created batch, batch id:",batch.id)
      return batch
   return None

#Retrieves the output/results file of a specific batch and writes article info and response to json and csv files
def retrieveBatchResult(batch, jsonFileName, csvFileName):
   if batch.status == "completed":
      batchResult = client.files.content(batch.output_file_id).content
      with open(jsonFileName, "wb") as f: #Write to raw .jsonl file
         f.write(batchResult)

      results = []
      with open(jsonFileName, "r") as f: #Read results from raw .jsonl file
         for line in f:
            json_obj = json.loads(line.strip())
            results.append(json_obj)
      
      postCount = 0
      with open(csvFileName, "a") as csvF: #Append article info and responses to .csv file
         csvWriter = csv.writer(csvF)
         for res in results:
            postInfo = res["custom_id"].split("|") #Post URL
            response = res["response"]["body"]["choices"][0]["message"]["content"]
            csvWriter.writerow([postInfo[0], response])
            postCount+=1
      print(batch.id, "successfully processed:",postCount,"posts")
   else:
      print(batch.id, "|", batch.status)

#Analyzes a Reddit post given its title and description
#Deduces if the article is related to the target stock, and if so, how optimistic it is to the target stock and to what degree
#Returns a number on a scale of -100 (Extreme negative) to 100 (Extreme positive)), and if the article is related

#!!*For cost and efficiency, this method is deprecated: send bulk articles via GPT batch API system

def stockAnalyze(headline, bodyText):
   chat_comp = client.chat.completions.create(model="gpt-3.5-turbo-0125", messages=generatePrompts_BW(headline, bodyText))
   isPolitical = chat_comp.choices[0].message.content

   if "y" in isPolitical.lower():
      chat_comp = client.chat.completions.create(model="gpt-4o-2024-05-13", messages=generatePrompts_Eval(headline, bodyText), temperature=0.6, top_p=0.5)
      rating = chat_comp.choices[0].message.content.split(" | ")

      #Try to convert to number
      if len(rating) < 2: return 0.0, "Not related"
      try:
         return float(rating[0]), rating[1]
      except ValueError:
         return 0.0, "Error"
   else:
      return 0.0, "Not related"
   
"""
=========================================================
                        BATCH API
=========================================================
"""

#Writes article information to .json and sends batch request to GPT-3.5 for black white analysis (is/is not related)
#Takes in table in the format [(url, title, description, ts, karma, comments, user),...]
def createBatch_BWAnalysis(allPosts, stock, startIndex=0, confirmMsg=True):
   #Send in multiple batches to not exceed limit
   index = startIndex
   while (index < len(allPosts)):
      totalCharacters = 0
      previousIndex = index
      dataList = []
      #Create data table
      for i in range(index, len(allPosts)):
         url, title, description, ts, karma, comments, user = allPosts[i]
         prompts = generatePrompts_BW(title, description, stock) #Generate prompts

         for p in prompts: totalCharacters += len(p["content"])
         if totalCharacters > MAX_BATCH_TOKENS_BW*3.5: #If over limit, stop and send batch
            for p in prompts: totalCharacters -= len(p["content"])
            break
         index = i

         #Format request
         data = { 
            "custom_id" : url,
            "method" : "POST",
            "url" : "/v1/chat/completions", 
            "body" : {
               "model" : "gpt-4.1-nano",
               "messages" :  prompts,
               "max_tokens" : 8
            }
         }
         dataList.append(data)
      index+=1 #Advance to next start point

      #Write to .jsonl
      write_jsonl(batchBWInFileName, dataList)

      #Echo results
      print("Wrote",len(dataList),"articles ["+str(previousIndex),"-",str(index-1)+"] to",batchBWInFileName)
      print("Total characters:",totalCharacters,"| Average characters per article:",(totalCharacters/len(dataList)))
      print("Tokens used:",(totalCharacters/4),"| Predicted cost: ",(totalCharacters/4*0.1/1e6),"| GPT-4.1-nano")
      with open(logBWFileName, "a") as csvF: #Log end index to file
         csvWriter = csv.writer(csvF)
         csvWriter.writerow(["Last ended index: " + str(index)])

      #Create batch and wait for completion
      batch = finalizeBatch(batchBWInFileName, "Black-white analysis of articles", confirmMsg)
      if batch == None: return #Cancelled

      while (batch.status not in ["completed","failed","cancelled"]):
         time.sleep(3)
         batch = client.batches.retrieve(batch.id)

      retrieveBatchResult(batch, batchBWOutFileName, BWFileName)

#Writes article information .json and sends batch request to GPT-4.1-nano for optimism score evaluation
#Takes in table in the format [(url, title, description, ts, karma, comments, user),...]
def createBatch_Eval(allPosts, stock, startIndex=0, confirmMsg=True):
   #Send in multiple batches to not exceed limit
   index = startIndex
   while (index < len(allPosts)):
      totalCharacters = 0
      previousIndex = index
      dataList = []
      #Create data table
      for i in range(index, len(allPosts)):
         url, title, description, ts, karma, comments, user = allPosts[i]
         prompts = generatePrompts_Eval(title, description, stock) #Generate prompts

         for p in prompts: totalCharacters += len(p["content"])
         if totalCharacters > MAX_BATCH_TOKENS_EVAL*3.5: #If over limit, stop and send batch
            for p in prompts: totalCharacters -= len(p["content"])
            break
         index = i
         
         #Format request
         data = { 
            "custom_id" : url,
            "method" : "POST",
            "url" : "/v1/chat/completions", 
            "body" : {
               "model" : "gpt-4.1-nano",
               "messages" :  prompts,
               "max_tokens" : 8
            }
         }
         dataList.append(data)
      index+=1 #Advance to next start point

      #Write to .jsonl
      write_jsonl(batchEvalInFileName, dataList)

      #Echo results
      print("Wrote",len(dataList),"articles ["+str(previousIndex),"-",str(index-1)+"] to",batchEvalInFileName)
      print("Total characters:",totalCharacters,"| Average characters per article:",(totalCharacters/len(dataList)))
      print("Tokens used:",(totalCharacters/4),"| Predicted cost: ",(totalCharacters/4*0.1/1e6),"| GPT-4.1-nano")
      with open(logEvalFileName, "a") as csvF: #Log end index to file
         csvWriter = csv.writer(csvF)
         csvWriter.writerow(["Last ended index: " + str(index)])

      #Create batch and wait for completion
      batch = finalizeBatch(batchEvalInFileName, "Political evaluation of articles", confirmMsg)
      if batch == None: return #Cancelled

      while (batch.status not in ["completed","failed","cancelled"]):
         time.sleep(3)
         batch = client.batches.retrieve(batch.id)

      retrieveBatchResult(batch, batchEvalOutFileName, EvalFileName)

"""
=========================================================
                     CALCULATION
=========================================================
"""

#Calculates the overall political rating of a specific publication by taking the mean square of all article ratings
#Since squaring removes negatives, add it back by calculating in two parts: sqrt([ Σ(-[neg.]^2) + Σ([pos.]^2) ] / (n-1))
def calculatePublicationPolitics(ratings):
   neg_sum = 0.0; pos_sum = 0.0
   for x in ratings:
      if x < 0:
         neg_sum += x**2
      else:
         pos_sum += x**2
   
   sum = ((pos_sum - neg_sum) / len(ratings))
   if sum == 0: return 0 #Avoid divide by zero
   #Get the square root (avoid negative with sqrt(abs(S)) * (S/|S|)
   return math.sqrt(abs(sum)) * sum/abs(sum)

#Calculates the overall political rating of a city by taking the simple (arithmetic) mean
def calculateCityPolitics(ratings):
   sum = 0.0
   for x in ratings:
      sum += x
   return sum / len(ratings)


#Driver code for retrieving specific batch
"""
batchId = "batch_J5nE9rLKmiMEHMOKvakjFiU5"
batch = client.batches.retrieve(batchId)
while (batch.status not in ["completed","failed","cancelled"]):
   time.sleep(3)
   batch = client.batches.retrieve(batch.id)
   print("Pending...")
retrieveBatchResult(batch, batchBWOutFileName, BWFileName)
"""
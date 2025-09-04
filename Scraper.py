from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
import math

"""
Main webscraper for Reddit analysis. Extracts posts, comments, and content from subreddits,
extracting key information like user, name, text, karma, date. Handles all web-crawling and
data collection processes.

@author Victor Gong
@version 12/17/2024
"""


headers = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:102.0) Gecko/20100101 Firefox/102.0',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.5',
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
}



#Checks if a page/URL exists
def urlExists(url):
	url = url.replace("http://","https://")
	try:
		check = requests.head(url, headers=headers); requests.get(url, headers=headers)
		return check.status_code >= 200 and check.status_code < 400
	except Exception as e:
		return False
	
#Extracts page source HTML from URL and creates BeautifulSoup instance
def createSoup(url):
	html = requests.get(url, headers=headers).text
	soup = BeautifulSoup(html, features="html.parser")
	return soup

#Checks if HTML element has attribute that begins with a prefix
def elementHasLabelPrefix(ele, attr, prefix):
	if ele and ele.has_attr(attr):
		if isinstance(ele[attr], list): return ele[attr][0].startswith(prefix)
		return ele[attr].startswith(prefix)

#Checks if HTML element has attribute that includes a substring
def elementHasLabelSub(ele, attr, sub):
	if ele and ele.has_attr(attr):
		if isinstance(ele[attr], list): return sub in ele[attr][0]
		return sub in ele[attr]


"""
Scrape posts off subreddit search by targetting:
URL: data-testid="post-title-text"
Time: faceplate-timeago, ts property
Karma: faceplate-number and span with "votes"
# of Comments: faceplate-number and span with "comments"
*Description & user retrieved through further scraping

Returns list of (post URL, post title, description, timestamp, karma, # of comments, and user)
"""

def extractPosts(subURL, scroll=5, cap=30):
	browser = webdriver.Chrome(); browser.get(subURL)
	subBody = browser.find_element(By.TAG_NAME, "body")

	#Scroll down to load page content
	scrollAmt = scroll
	while scrollAmt:
		browser.execute_script("window.scrollTo(0, document.body.scrollHeight);")
		time.sleep(1.5)
		scrollAmt -= 1
	
	#Extract post URLs from source HTML
	subHTML = browser.page_source; browser.close()
	soup = BeautifulSoup(subHTML, features="html.parser")
	postEle = soup.find_all("a",{"data-testid":"post-title-text"})
	posts = []
	timeOrigin = time.time() #Time profiling (average)
	for p in postEle:
		if not cap: break
		mainEle = p.parent #<div> that contains all information for this search cell
		if elementHasLabelPrefix(p, "href", "/r/wallstreetbets/") and mainEle:
			url = "http://reddit.com" + p["href"]
			if urlExists(url):
				timeStart = time.time() #Time profiling (per post)

				#Title, description, user
				title, description, user = getPostExtraDetails(url)

				#Timestamp
				ts = ""
				tsEle = mainEle.find("faceplate-timeago")
				if tsEle and tsEle.has_attr("ts"): ts = tsEle["ts"]

				#Karma and # of comments
				karma = 0; comments = 0
				fpEle = mainEle.find_all("faceplate-number")
				for fp in fpEle:
					if fp and fp.has_attr("number") and fp.parent:
						labelIn = "" #Can either be in a <span> inside
						if fp.parent.find("span"): labelIn = fp.parent.find("span").text
						labelOut = fp.parent.text #Or in the <span> outside
						if "votes" in (labelIn+labelOut):
							karma = int(fp["number"]) 
						elif "comments" in (labelIn+labelOut):
							comments = int(fp["number"])
				
				posts.append((url, title, description, ts, karma, comments, user))
				print(url, title, ts, user, karma, comments, "| " + str(round((time.time()-timeStart)*1000)) + " ms")
			cap-=1
	print("PostScrape: extracted",len(posts),"posts from",subURL, "| Avg. " + str(round((time.time()-timeOrigin)*1000/len(posts), 1)) + " ms/post")
	return posts

#Retrieves and returns the title, description, and user
#**Potential point of improvement, use image-to-text on figures in posts for more content

def getPostExtraDetails(postURL):
	soup = createSoup(postURL)
	postId = "" #Every reddit post has a unique id used in the HTML labels (e.g. t3_1hgjsgd), can be found in post title element
	postEle = soup.find("shreddit-post")

	#Get title
	title = ""
	titleEle = postEle.find_all("h1", {"slot":"title"})
	
	for t in titleEle:
		if elementHasLabelPrefix(t, "id", "post-title"):
			title = t.text
			postId = t["id"].replace("post-title-","")

	#Get user
	user = ""
	userEle = postEle.find_all("a")
	for u in userEle:
		if elementHasLabelPrefix(u, "class", "author-name") and u.has_attr("href"):
			user = u["href"]
	
	#Get description
	desc = ""
	descEle = postEle.find_all("div")
	for d in descEle:
		if elementHasLabelPrefix(d, "id", postId+"-post-rtjson-content"):
			for text in d.find_all("p"):
				desc += text.text + " "
	return title, desc, user

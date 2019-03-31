import requests, queue, threading, _thread, argparse, sys
from pathlib import Path
from bs4 import BeautifulSoup
from time import sleep
from random import randint
from datetime import datetime
from threading import Lock

parser = argparse.ArgumentParser(usage=sys.argv[0] + " <website> [options] <folder>",
	description="Recursively crawl a website and download every file with the selected extension in the href tag (Example: pdf)",
	epilog='''
...				Have fun! 	....	
''')

parser.add_argument('website', type=str, action='store', help='website to crawl in form "http(s)://domain"')
parser.add_argument('-s', '--silent', action='store_true',default=False, help='silent mode - turn off downloading output')
parser.add_argument('-so','--search-only' , action='store_true',default=False, help='just output a list of the files found')
requiredNamed = parser.add_argument_group('required named arguments')
requiredNamed.add_argument('-e', '--extension', type=str, action='store',required=True, help='extension (3 char) to download (dot-less) ex: "pdf"')
requiredNamed.add_argument('-o', '--output-dir', type=str, action='store', required=True, help='directory to save files')

# set of links already scanned
SCANNED_LINKS = set()
# set of links match found
TARGET_LINKS = set()

FILE_EXTENSION = ""

workers = []
N_THREADS = 10

n_requests = 0
n_requests_lock = Lock()

def main():
	global workers
	global n_requests
	global FILE_EXTENSION

	args = parser.parse_args()
	
	FILE_EXTENSION = args.extension
	URL = args.website
	OUTPUT_DIR = args.output_dir

	print("\nCrawling {} in search of {} files to download into {}".format(URL,FILE_EXTENSION,OUTPUT_DIR))
	print("\nNumber of N_THREADS: {}".format(N_THREADS))
	print("\nSearch_only: {}\n".format(args.search_only))

	elapsed = datetime.now()

	for i in range(N_THREADS):
		workers.append(worker(i, URL, FILE_EXTENSION, OUTPUT_DIR, args.search_only, args.silent))

	for i in workers:
		i.start()

	# Add first URL to start the scanning
	add_link_to_worker_queue(0, URL)

	for w in workers:
		try:
			w.join()
		except KeyboardInterrupt:
			for t in workers:
				t.stop()

	elapsed = datetime.now() - elapsed

	print("\n\n\nFINISHED IN {}.{} seconds.".format(elapsed.seconds, str(elapsed.microseconds/1000)[:3]) )
	print("\t{} TOTAL LINKS SCANNED\n\t{} TOTAL {} FOUND".format(len(SCANNED_LINKS), len(TARGET_LINKS),FILE_EXTENSION) )
	for pdf in TARGET_LINKS:
		print("\t\t{}: {}".format(FILE_EXTENSION, pdf))
	print("\t{} total web requests.".format(n_requests))

# randomly distribute work along the workers
def add_link_to_queues(link):
	global workers
	workers[randint(0, len(workers)-1 )].add_work(link)

# add work for one specific worker
def add_link_to_worker_queue(index,link):
	global workers
	workers[index].add_work(link)

# save file to disk
def save_file(file_url, output_dir):
	pdf_name = file_url[file_url.rfind("/")+1:]
	#check if already exists
	if not Path(output_dir + pdf_name).is_file():
		r = requests.get(file_url)
		with open(output_dir + pdf_name, "wb") as f:
			f.write(r.content)
		print("[SAVE] {}: {} saved".format(FILE_EXTENSION, pdf_name))
	else:
		print("[INFO] {}: {} already exists!".format(FILE_EXTENSION, pdf_name))	

class worker(threading.Thread):
	def __init__(self, threadID, URL, extension, output_dir, search_only, silent):
		super(worker, self).__init__()
		self._stop_event = threading.Event()
		self.URL = URL
		self.queue = queue.Queue()
		self.threadID = threadID
		self.terminate = False
		self.fextension = extension
		self.output_dir = output_dir
		self.silent = silent
		self.search_only = search_only
		self.req_ses = requests.session()

	def getID(self):
		return self.threadID

	def get_queue_length(self):
		return self.queue.qsize()

	def add_work(self, link):
		self.queue.put(link)

	def stop(self):
		self.terminate = True
		self._stop_event.set()

	def check_url(self, link):
		# if link is target, skip it
		if link[-3:] == self.fextension:
			return False
		return self.URL in link

	def check_if_scanned(self, link):
		global n_requests_lock
		with n_requests_lock:
			present = link in SCANNED_LINKS
			SCANNED_LINKS.add(link)
			return present

	# get all the href links from the "link" page
	def get_all_links(self, link):
		global SCANNED_LINKS
		global n_requests
		global n_requests_lock

		try:
			req = self.req_ses.get(link)
			with n_requests_lock: 
				n_requests += 1
				if not self.silent:
					print("[%s] T-ID: %s scanning -> %s" % (str(len(SCANNED_LINKS)), str(self.threadID), link))
		except requests.exceptions.MissingSchema:
			#print('invalid url %s' % link)
			return None

		html_soup = BeautifulSoup(req.text, 'html.parser')

		links = [ i.get("href") for i in html_soup.find_all('a') ]
		links = [ e for e in links if e not in SCANNED_LINKS and e is not None and len(e) > 5]
		# file in list? search it and remove from crawling list (if present)
		html_soup.decompose() 	#THIS MADE THE TRICK, NO MORE RAM WASTED!

		# add the schema and base URL to links like "/something"
		for i in range(len(links)):
			if links[i][0] == "/":
				links[i] = self.URL + links[i]

		return links

	def run(self):
		global TARGET_LINKS

		while not self.terminate:
			try:
				link = self.queue.get(timeout=1)
			except queue.Empty:
				self.stop()
				continue
			
			if link[0] == "/":
				link = self.URL + link

			if not self.check_url(link):
				#link is not under the same domain
				#print("[*SKIP] {} is not under the specified DOMAIN.".format(link))
				continue

			# add link to scanned links
			if self.check_if_scanned(link):
				#link already scanned
				#print("T-ID: {} [*SKIP] {} already scanned.".format(self.threadID,link))
				continue

			# get all links from the page
			links = self.get_all_links(link)
			if links == None:
				continue

			# check for extensions
			for i in links:
				if i[-3:] == self.fextension:
					if i not in TARGET_LINKS:
						links.remove(i)
						TARGET_LINKS.add(i)
						print("[FOUND] {} n. {} FOUND: {}".format(self.fextension,str(len(TARGET_LINKS)), i )) if not self.silent else None
						
						if not self.search_only:
							try:
								_thread.start_new_thread( save_file, (i, self.output_dir, ) )
							except:
								print("[ERROR!] error saving {}".format(self.fextension))
						continue
			#then crawl each site
			for link in links:
				add_link_to_queues(link)

if __name__ == '__main__':
	main()

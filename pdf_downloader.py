import requests, queue, threading, _thread, argparse, sys
from pathlib import Path
from bs4 import BeautifulSoup
from time import sleep


parser = argparse.ArgumentParser(usage=sys.argv[0] + " <website> [options] <folder>",
	description="Recursively crawl a website and download every file with the selected extension in the href tag (Example: pdf)",
	epilog='''
...				Have fun! 	....	
''')

parser.add_argument('website', type=str, action='store', help='website to crawl in form "http(s)://domain"')
#parser.add_argument('-e', '--extension', type=str, action='store', help='extension (3 char) to download (dot-less) ex: "pdf"')
parser.add_argument('-s', '--silent', action='store_true',default=False, help='silent mode - turn off downloading output')
parser.add_argument('-so','--search-only' , action='store_true',default=False, help='just output a list of the files found')
requiredNamed = parser.add_argument_group('required named arguments')
requiredNamed.add_argument('-e', '--extension', type=str, action='store',required=True, help='extension (3 char) to download (dot-less) ex: "pdf"')
requiredNamed.add_argument('-o', '--output-dir', type=str, action='store', required=True, help='directory to save files')


SCANNED_LINKS = set()
PDF_LINKS = set()

workers = []
N_THREADS = 1

n_requests = 0

def main():
	global workers
	global n_requests

	args = parser.parse_args()
	
	URL = args.website
	FILE_EXTENSION = args.extension
	OUTPUT_DIR = args.output_dir
	print("Crawling {} in search of {} files to download into {}".format(URL,FILE_EXTENSION,OUTPUT_DIR))

	print("search_only: {}".format(args.search_only))

	for i in range(N_THREADS):
		workers.append(worker(i, URL, FILE_EXTENSION, OUTPUT_DIR, args.search_only, args.silent))

	for i in workers:
		i.start()

	add_link_to_worker_queue(0, URL)

	#while len(workers) > 0:
	#	try:
	#		workers = [t.join(1) for t in workers if t is not None and t.isAlive()]
	#	except KeyboardInterrupt:
	#		for t in workers:
	#			t.stop()
	for w in workers:
		try:
			w.join()
		except KeyboardInterrupt:
			for t in workers:
				t.stop()

	print("\n\n\nFINISHED")
	print("\t{} TOTAL LINKS\n\t{} TOTAL PDF FOUND".format(len(SCANNED_LINKS), len(PDF_LINKS)))
	for pdf in PDF_LINKS:
		print("\t\tPDF: {}".format(pdf))
	print("\t{} total web requests.".format(n_requests))

'''
def add_link_to_queue(link):
	global workers
	index = 0
	lazy_worker = 10000
	for i in workers:
		if i.get_queue_length() < lazy_worker:
			lazy_worker = i.get_queue_length()
			index = i.getID()
	workers[index].add_work(link)

'''

def add_link_to_worker_queue(index,link):
	global workers
	workers[index].add_work(link)


def save_pdf(pdf_url, output_dir):
	pdf_name = pdf_url[pdf_url.rfind("/")+1:]
	#check if already exists
	if not Path(output_dir + pdf_name).is_file():
		r = requests.get(pdf_url)
		with open(output_dir + pdf_name, "wb") as f:
			f.write(r.content)
		print("[SAVE] PDF: " + pdf_name + " saved!")
	else:
		print("[INFO] PDF: " + pdf_name + " already exists!")	

class worker(threading.Thread):
	def __init__(self, threadID, URL, extension, output_dir, search_only, silent):
		threading.Thread.__init__(self)
		self.URL = URL
		self.queue = queue.Queue()
		self.threadID = threadID
		self.terminate = False
		self.fextension = extension
		self.output_dir = output_dir
		self.silent = silent
		self.search_only = search_only

	def getID(self):
		return self.threadID

	def get_queue_length(self):
		return self.queue.qsize()

	def add_work(self, link):
		self.queue.put(link)

	def stop(self):
		self.terminate = True

	def check_url(self, link):
		return self.URL in link

	def check_if_scanned(self, link):
		return link in SCANNED_LINKS

	def get_all_links(self, link):
		global SCANNED_LINKS
		global n_requests

		try:
				req = requests.get(link)
				n_requests += 1
				SCANNED_LINKS.add(link)
		except requests.exceptions.MissingSchema:
			#print('invalid url %s' % link)
			return None

		html_soup = BeautifulSoup(req.text, 'html.parser')
		#crawl(soup,link)

		links = [ i.get("href") for i in html_soup.find_all('a') ]
		links = [ e for e in links if e not in SCANNED_LINKS and e is not None and len(e) > 5]
		#pdf in list? search it and remove from crawling list (if present)
		html_soup.decompose() 	#THIS MADE THE TRICK, NO MORE RAM WASTED!

		# add the schema and base URL to links like "/something"
		for i in range(len(links)):
			if links[i][0] == "/":
				links[i] = self.URL + links[i]

		return links

	def run(self):
		while not self.terminate:
			try:
				link = self.queue.get(timeout=5)
			except queue.Empty:
				self.stop()
				continue
			
			if link[0] == "/":
				link = self.URL + link

			if not self.check_url(link):
				#Link is not under the same domain
				#print("[*SKIP] {} is not under the specified DOMAIN.".format(link))
				continue

			if self.check_if_scanned(link):
				#link already scanned
				#print("[*SKIP] {} already scanned.".format(link))
				continue

			if not self.silent:
				print("[%s] T-ID: %s scanning -> %s" % (str(len(SCANNED_LINKS)), str(self.threadID), link))
			
			# get all links from the page
			links = self.get_all_links(link)
			if links == None:
				continue

			# check for extensions
			for i in links:
				if i[-3:] == self.fextension:
					if i not in PDF_LINKS:
						links.remove(i)
						PDF_LINKS.add(i)

						print("[FOUND] PDF n. {} FOUND: {}".format(str(len(PDF_LINKS)), i )) if not self.silent else None
						
						if not self.search_only:
							try:
								_thread.start_new_thread( save_pdf, (i, self.output_dir, ) )
							except:
								print("[ERROR!] error saving pdf")
						continue
			#then crawl each site
			for link in links:
				#add_link_to_worker_queue(0,link)
				self.add_work(link)

if __name__ == '__main__':
	main()

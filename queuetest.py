# 
# queue producer/consumer/consumer for json queue
# 
#
import httplib, urllib
import time
import simplejson
from threading import Thread
import signal

class ProducerThread(Thread):
	def run(self):
		print "Producer started"
		packet = {}
		packet["cmd"]="add"
		packet["queue"]="test"
		
		while(1):
			packet["value"]=time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
			self.sendqueue(simplejson.dumps(packet))
			time.sleep(2)

	def sendqueue(self, packet):
		params = urllib.urlencode({"body": packet})
		headers = {"Content-type":"application/x-www-form-urlencoded"}
		#conn = httplib.HTTPConnection("jsonqueue.appspot.com")
		conn = httplib.HTTPConnection("127.0.0.1", 8080)
		conn.request("POST",  "/queue", params, headers)
		res = conn.getresponse()
                print "Producer: %s" % res.reason
		st = res.status
		conn.close()
		return st

class ConsumerThread(Thread):
	def run(self):
		print "Consumer started"
		packet = {}
		packet["cmd"]="take"
		packet["queue"]="test"
		
		while(1):
			resp=self.takefromqueue(simplejson.dumps(packet))
			if resp != "": 
                            print "Consumer data: %s" % resp
			time.sleep(2)

	def takefromqueue(self, packet):
		params = urllib.urlencode({"body": packet})
		headers = {"Content-type":"application/x-www-form-urlencoded"}
		#conn = httplib.HTTPConnection("jsonqueue.appspot.com")
                conn = httplib.HTTPConnection("127.0.0.1", 8080)
		conn.request("POST",  "/queue", params, headers)
		res = conn.getresponse()
		data = res.read()
		st = res.status
		print "Consumer status: "  + str(st)
		conn.close()
		return data


if __name__ == "__main__":
	signal.signal(signal.SIGINT, signal.SIG_DFL)
	
	print "Starting date consumer"
	consumer = ConsumerThread()
	consumer.start()

	print "Starting date producer"
	producer = ProducerThread()
	producer.start()

